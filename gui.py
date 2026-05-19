import os
import re
import json
import config
import tkinter as tk
import customtkinter as ctk
from datetime import datetime
from utils import is_valid_url, open_downloads_folder
from downloader import Downloader
from monitor import Monitor
from config import (
    DOWNLOADS_PATH,
    ARTISTS_FILE,
    OAUTH_FILE,
    MONITOR_MAX_TRACKS,
    GEOMETRY_FILE,
    load_oauth_token,
    save_oauth_token,
    is_valid_token,
    set_monitor_settings,
)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        # ============================================
        # НАСТРОЙКИ ОКНА
        # ============================================
        self.title("SoundCloud MP3 Downloader")
        w, h = 740, 650
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(600, 500)

        ctk.set_appearance_mode("dark")
        self.configure(fg_color="#000000")

        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)

        # Восстановить геометрию из прошлого запуска
        self._restore_geometry()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # ============================================
        # ОТСЛЕЖИВАНИЕ БУФЕРА ОБМЕНА
        # ============================================
        self._last_clipboard = ""
        self._clipboard_enabled = True

        # ============================================
        # ВКЛАДКИ
        # ============================================
        self.tabview = ctk.CTkTabview(
            self,
            anchor="nw",
            fg_color="#000000",
            segmented_button_fg_color="#000000",
            segmented_button_selected_color="#151515",
            segmented_button_selected_hover_color="#1a1a1a",
            segmented_button_unselected_color="#000000",
            segmented_button_unselected_hover_color="#0a0a0a",
            text_color="#ffffff",
            text_color_disabled="#444444",
            border_width=0,
        )
        self.tabview.pack(fill="both", expand=True, padx=12, pady=12)

        self.tab_download = self.tabview.add("Download")
        self.tab_monitor = self.tabview.add("Monitor")
        self.tab_settings = self.tabview.add("Settings")

        self.tab_download.configure(fg_color="#000000")
        self.tab_monitor.configure(fg_color="#000000")
        self.tab_settings.configure(fg_color="#000000")

        self._style_tabs()

        # ============================================
        # МОДУЛИ — создаём с колбэками сразу.
        # Колбэки используют self.after() — безопасно до создания виджетов,
        # т.к. реально вызовутся только после запуска mainloop().
        # _build_monitor_tab → _refresh_artists читает self.monitor.get_artists()
        # (не логирует), поэтому log_callback не нужен до построения вкладки.
        # ============================================
        self.downloader = Downloader(
            log_callback=lambda text: self.after(0, self._smart_log, self.download_log, text),
            progress_callback=lambda val: self.after(0, self._update_download_progress, val),
            done_callback=lambda ok: self.after(0, self._on_download_done, ok),
        )
        self.monitor = Monitor(
            log_callback=lambda text: self.after(0, self._smart_log, self.monitor_log, text),
            progress_callback=lambda val: self.after(0, self._update_monitor_progress, val),
            done_callback=lambda ok: self.after(0, self._on_monitor_done, ok),
        )

        self._build_download_tab()
        self._build_monitor_tab()
        self._build_settings_tab()

        self._setup_log_tags(self.download_log)
        self._setup_log_tags(self.monitor_log)

        self._setup_global_clipboard()
        self._start_clipboard_watcher()

    def _style_tabs(self):
        try:
            seg_button = self.tabview._segmented_button
            seg_button.configure(
                font=("Segoe UI", 13),
                corner_radius=6,
                border_width=2,
            )
        except Exception:
            pass

    # ============================================
    # ГЕОМЕТРИЯ — сохранение / восстановление
    # ============================================
    def _restore_geometry(self):
        try:
            with open(GEOMETRY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            geom = data.get("geometry", "")
            if geom:
                self.geometry(geom)
                # Убедиться что окно в пределах экрана
                self.update_idletasks()
                sw = self.winfo_screenwidth()
                sh = self.winfo_screenheight()
                x = self.winfo_x()
                y = self.winfo_y()
                w = self.winfo_width()
                h = self.winfo_height()
                nx = max(0, min(x, sw - 100))
                ny = max(0, min(y, sh - 100))
                if nx != x or ny != y:
                    self.geometry(f"{w}x{h}+{nx}+{ny}")
        except Exception:
            pass  # файла нет или повреждён — используем дефолт

    def _save_geometry(self):
        try:
            geom = self.geometry()
            with open(GEOMETRY_FILE, 'w', encoding='utf-8') as f:
                json.dump({"geometry": geom}, f)
        except Exception:
            pass

    def _on_close(self):
        self._save_geometry()
        self.destroy()

    # ============================================
    # АВТОВСТАВКА ИЗ БУФЕРА ОБМЕНА
    # ============================================
    def _is_soundcloud_url(self, text):
        if not text or len(text) > 500:
            return False
        text = text.strip()
        pattern = r'^https?://(www\.)?(soundcloud\.com|on\.soundcloud\.com|m\.soundcloud\.com|youtube\.com|youtu\.be|music\.youtube\.com)/.+'
        return bool(re.match(pattern, text))

    def _start_clipboard_watcher(self):
        try:
            current = self.clipboard_get()
        except tk.TclError:
            current = ""
        self._last_clipboard = current
        self._check_clipboard()

    def _check_clipboard(self):
        if not self._clipboard_enabled:
            self.after(500, self._check_clipboard)
            return

        try:
            current = self.clipboard_get()
        except tk.TclError:
            current = ""

        if current != self._last_clipboard:
            self._last_clipboard = current

            if self._is_soundcloud_url(current):
                active_tab = self.tabview.get()

                if active_tab == "Download":
                    current_text = self.url_entry.get().strip()
                    if current_text != current.strip():
                        self.url_entry.delete(0, "end")
                        self.url_entry.insert(0, current.strip())
                        self._flash_entry(self.url_entry)

                elif active_tab == "Monitor":
                    current_text = self.artist_entry.get().strip()
                    if current_text != current.strip():
                        self.artist_entry.delete(0, "end")
                        self.artist_entry.insert(0, current.strip())
                        self._flash_entry(self.artist_entry)

        self.after(500, self._check_clipboard)

    def _flash_entry(self, entry):
        try:
            original_color = entry.cget("border_color")
            entry.configure(border_color="#5cdb5c")
            self.after(400, lambda: entry.configure(border_color=original_color))
        except Exception:
            pass

    # ============================================
    # ГЛОБАЛЬНЫЙ БУФЕР ОБМЕНА
    # ============================================
    def _setup_global_clipboard(self):
        # Для всех Entry виджетов
        self.bind_class("Entry", "<Control-v>", self._global_paste)
        self.bind_class("Entry", "<Control-V>", self._global_paste)
        self.bind_class("Entry", "<Control-c>", self._global_copy)
        self.bind_class("Entry", "<Control-C>", self._global_copy)
        self.bind_class("Entry", "<Control-x>", self._global_cut)
        self.bind_class("Entry", "<Control-X>", self._global_cut)
        self.bind_class("Entry", "<Control-a>", self._global_select_all)
        self.bind_class("Entry", "<Control-A>", self._global_select_all)
        # Для всех Text виджетов (логи)
        self.bind_class("Text", "<Control-c>", self._global_copy)
        self.bind_class("Text", "<Control-C>", self._global_copy)
        self.bind_class("Text", "<Control-a>", self._global_select_all)
        self.bind_class("Text", "<Control-A>", self._global_select_all)

    def _global_paste(self, event):
        widget = event.widget
        try:
            text = self.clipboard_get()
            if not text:
                return "break"

            if isinstance(widget, tk.Entry):
                # Если есть выделение — удалить его
                if widget.selection_present():
                    widget.delete("sel.first", "sel.last")
                # Вставить в позицию курсора
                widget.insert("insert", text.strip())
            elif isinstance(widget, tk.Text):
                try:
                    widget.delete("sel.first", "sel.last")
                except tk.TclError:
                    pass
                widget.insert("insert", text.strip())
        except tk.TclError:
            pass
        return "break"

    def _global_copy(self, event):
        widget = event.widget
        try:
            if isinstance(widget, tk.Entry):
                if widget.selection_present():
                    self.clipboard_clear()
                    self.clipboard_append(widget.selection_get())
                return "break"
            elif isinstance(widget, tk.Text):
                try:
                    selected = widget.get("sel.first", "sel.last")
                    if selected:
                        self.clipboard_clear()
                        self.clipboard_append(selected)
                except tk.TclError:
                    pass
                return "break"
        except tk.TclError:
            pass
        return None

    def _global_select_all(self, event):
        widget = event.widget
        try:
            if isinstance(widget, tk.Entry):
                widget.select_range(0, "end")
                widget.icursor("end")
                return "break"
            elif isinstance(widget, tk.Text):
                widget.tag_add("sel", "1.0", "end")
                return "break"
        except tk.TclError:
            pass
        return None

    def _global_cut(self, event):
        widget = event.widget
        if isinstance(widget, tk.Entry):
            try:
                if widget.selection_present():
                    selected = widget.selection_get()
                    self.clipboard_clear()
                    self.clipboard_append(selected)
                    widget.delete("sel.first", "sel.last")
            except tk.TclError:
                pass
            return "break"
        return None

    # ============================================
    # ЦВЕТОВЫЕ ТЕГИ ДЛЯ ЛОГОВ
    # ============================================
    def _setup_log_tags(self, textbox):
        widget = textbox._textbox if hasattr(textbox, '_textbox') else textbox

        widget.tag_configure("header", foreground="#ffffff", font=("Consolas", 12, "bold"))
        widget.tag_configure("subheader", foreground="#aaaaaa", font=("Consolas", 11, "bold"))
        widget.tag_configure("divider", foreground="#333333")
        widget.tag_configure("time", foreground="#555555", font=("Consolas", 11))

        widget.tag_configure("success", foreground="#5cdb5c", font=("Consolas", 12, "bold"))
        widget.tag_configure("error", foreground="#ff5555", font=("Consolas", 12, "bold"))
        widget.tag_configure("warning", foreground="#ffaa00", font=("Consolas", 12, "bold"))
        widget.tag_configure("info", foreground="#5cb8ff", font=("Consolas", 12))

        widget.tag_configure("icon_new", foreground="#5cdb5c", font=("Consolas", 12, "bold"))
        widget.tag_configure("icon_skip", foreground="#888888", font=("Consolas", 12))
        widget.tag_configure("icon_old", foreground="#666666", font=("Consolas", 12))
        widget.tag_configure("icon_arrow", foreground="#5cb8ff", font=("Consolas", 12, "bold"))

        widget.tag_configure("meta", foreground="#777777", font=("Consolas", 11))
        widget.tag_configure("artist", foreground="#ffffff", font=("Consolas", 12, "bold"))
        widget.tag_configure("track", foreground="#dddddd", font=("Consolas", 12))
        widget.tag_configure("count", foreground="#5cb8ff", font=("Consolas", 12, "bold"))
        widget.tag_configure("normal", foreground="#cccccc", font=("Consolas", 12))
        widget.tag_configure("progress", foreground="#5cb8ff", font=("Consolas", 12))

    def _log_separator(self, textbox, char="─", width=58):
        widget = textbox._textbox if hasattr(textbox, '_textbox') else textbox
        widget.configure(state="normal")
        widget.insert("end", "  " + char * width + "\n", "divider")
        widget.see("end")

    def _log_header(self, textbox, title):
        widget = textbox._textbox if hasattr(textbox, '_textbox') else textbox
        time = datetime.now().strftime("%H:%M:%S")

        widget.configure(state="normal")
        widget.insert("end", "\n")
        widget.insert("end", "  ╔" + "═" * 58 + "╗\n", "divider")
        widget.insert("end", "  ║ ", "divider")
        widget.insert("end", f"{title:<46}", "header")
        widget.insert("end", f"  {time}", "time")
        widget.insert("end", " ║\n", "divider")
        widget.insert("end", "  ╚" + "═" * 58 + "╝\n", "divider")
        widget.see("end")

    # ============================================
    # ПАРСЕР СТРОК
    # ============================================

    # Таблица правил: (подстрока, иконка, тег_иконки, тег_текста)
    # Порядок важен — первое совпадение побеждает
    _LOG_RULES = [
        ("🆕",  "🆕 ",  "icon_new",   "track"),
        ("✅",  "✅ ",  "success",    "success"),
        ("❌",  "❌ ",  "error",      "error"),
        ("⚠",   "⚠  ",  "warning",    "warning"),
        ("⏭",  "⏭  ",  "icon_old",   "icon_old"),
        ("⏩",  "⏩ ",  "icon_skip",  "icon_skip"),
        ("⬇",  "⬇  ",  "icon_arrow", "info"),    # скачивание (не прогресс)
        ("🎵",  "🎵 ",  "icon_new",   "track"),
        ("📁",  "📁 ",  "info",       "meta"),
        ("⏰",  "⏰ ",  "info",       "meta"),
        ("🔍",  None,   None,         "info"),
        ("📋",  None,   None,         "info"),
    ]

    def _smart_log(self, textbox, text):
        widget = textbox._textbox if hasattr(textbox, '_textbox') else textbox
        widget.configure(state="normal")

        # Разделители
        if text.startswith("═") or text.startswith("══"):
            return
        if text.startswith("─") or text.startswith("──"):
            self._log_separator(textbox)
            self._trim_log(textbox)
            return

        # Прогресс скачивания — обновляем текущую строку
        if "⬇ Downloading..." in text:
            self._update_progress_line(textbox, text)
            return

        # Конвертация завершена — убираем прогресс-строку
        if "Converting" in text or "Download complete" in text:
            self._clear_progress_line(textbox)
            content = text.replace("✅", "").strip()
            widget.insert("end", "    ⚙  ", "info")
            widget.insert("end", f"{content}\n", "info")
            widget.see("end")
            self._trim_log(textbox)
            return

        if "🔗" in text:
            return

        # Заголовки
        if "MONITOR REPORT" in text or "REPORT" in text:
            self._log_header(textbox, "📊 MONITOR REPORT")
            self._trim_log(textbox)
            return
        if "SoundCloud Monitor" in text:
            self._log_header(textbox, "🔍 SOUNDCLOUD MONITOR")
            self._trim_log(textbox)
            return

        stripped = text.strip()

        # Строка артиста: [N/M] 👤 name
        if "👤" in text and "[" in text and "]" in text:
            bracket_end = text.index("]") + 1
            bracket_part = text[text.index("["):bracket_end]
            rest = text[bracket_end:].replace("👤", "").strip()
            widget.insert("end", "\n  ", "normal")
            widget.insert("end", f"{bracket_part} ", "count")
            widget.insert("end", "👤 ", "icon_new")
            widget.insert("end", f"{rest}\n", "artist")
            self._log_separator(textbox, "·", 56)
            self._trim_log(textbox)
            return

        # Метаданные трека (дата, длительность)
        if stripped.startswith("📅") or stripped.startswith("⏱"):
            widget.insert("end", "       ", "normal")
            widget.insert("end", f"{stripped}\n", "meta")
            self._trim_log(textbox)
            return

        # Пустая строка
        if stripped == "":
            widget.insert("end", "\n")
            widget.see("end")
            return

        # Универсальные правила из таблицы
        for marker, icon, icon_tag, text_tag in self._LOG_RULES:
            if marker in text:
                content = text.replace(marker, "").strip()
                if icon and icon_tag:
                    widget.insert("end", f"    {icon}", icon_tag)
                    widget.insert("end", f"{content}\n", text_tag)
                else:
                    widget.insert("end", f"    {text}\n", text_tag)
                widget.see("end")
                self._trim_log(textbox)
                return

        widget.insert("end", f"  {text}\n", "normal")
        widget.see("end")
        self._trim_log(textbox)

    def _update_progress_line(self, textbox, text):
        widget = textbox._textbox if hasattr(textbox, '_textbox') else textbox
        widget.configure(state="normal")

        speed = ""
        if "..." in text:
            parts = text.split("...")
            if len(parts) > 1:
                speed = parts[1].strip()

        last_line_start = widget.index("end-2l linestart")
        last_line_end = widget.index("end-1c")
        last_line = widget.get(last_line_start, last_line_end)

        if "[PROGRESS]" in last_line:
            widget.delete(last_line_start, last_line_end + "+1c")

        widget.insert("end", "    ⏬ ", "icon_arrow")
        widget.insert("end", f"[PROGRESS] Downloading... ", "progress")
        if speed:
            widget.insert("end", f"{speed}", "info")
        widget.insert("end", "\n")
        widget.see("end")

    def _clear_progress_line(self, textbox):
        widget = textbox._textbox if hasattr(textbox, '_textbox') else textbox
        widget.configure(state="normal")

        last_line_start = widget.index("end-2l linestart")
        last_line_end = widget.index("end-1c")
        last_line = widget.get(last_line_start, last_line_end)

        if "[PROGRESS]" in last_line:
            widget.delete(last_line_start, last_line_end + "+1c")

    # ============================================
    # БУФЕР ОБМЕНА
    # ============================================
    def _paste_to_entry(self, entry):
        try:
            text = self.clipboard_get()
            if text:
                entry.delete(0, "end")
                entry.insert(0, text.strip())
        except tk.TclError:
            pass

    def _copy_from_entry(self, entry):
        try:
            widget = entry._entry if hasattr(entry, '_entry') else entry
            if widget.selection_present():
                self.clipboard_clear()
                self.clipboard_append(widget.selection_get())
        except (tk.TclError, AttributeError):
            pass

    def _select_all_entry(self, entry):
        try:
            widget = entry._entry if hasattr(entry, '_entry') else entry
            widget.select_range(0, "end")
            widget.icursor("end")
        except (tk.TclError, AttributeError):
            pass

    def _cut_from_entry(self, entry):
        self._copy_from_entry(entry)
        try:
            widget = entry._entry if hasattr(entry, '_entry') else entry
            if widget.selection_present():
                widget.delete("sel.first", "sel.last")
        except (tk.TclError, AttributeError):
            pass

    def _clear_entry(self, entry):
        entry.delete(0, "end")
        try:
            self._last_clipboard = self.clipboard_get()
        except tk.TclError:
            self._last_clipboard = ""

    def _show_context_menu(self, event, entry):
        menu = tk.Menu(
            self, tearoff=0, bg="#151515", fg="#dddddd",
            activebackground="#ffffff", activeforeground="#000000",
            borderwidth=1, font=("Segoe UI", 10),
        )
        menu.add_command(label="  📋 Paste", command=lambda: self._paste_to_entry(entry))
        menu.add_command(label="  📄 Copy", command=lambda: self._copy_from_entry(entry))
        menu.add_command(label="  ✂ Cut", command=lambda: self._cut_from_entry(entry))
        menu.add_separator()
        menu.add_command(label="  🗑 Clear", command=lambda: self._clear_entry(entry))
        menu.add_separator()
        menu.add_command(label="  🔘 Select All", command=lambda: self._select_all_entry(entry))
        menu.tk_popup(event.x_root, event.y_root)

    def _block_log_input(self, textbox):
        widget = textbox._textbox if hasattr(textbox, '_textbox') else textbox

        def block_input(e):
            if e.state in (4, 12):
                if e.keysym.lower() in ['c', 'a']:
                    return None
            return "break"

        widget.bind("<Key>", block_input)

    # ============================================
    # ВКЛАДКА: DOWNLOAD
    # ============================================
    def _build_download_tab(self):
        tab = self.tab_download

        url_frame = ctk.CTkFrame(tab, fg_color="transparent")
        url_frame.pack(fill="x", padx=12, pady=(15, 6))

        self.url_entry = ctk.CTkEntry(
            url_frame, placeholder_text="Auto-pastes SoundCloud URLs from clipboard...", height=44,
            font=("Segoe UI", 14), fg_color="#0a0a0a", border_color="#333333",
            border_width=2, text_color="#ffffff", placeholder_text_color="#555555",
            corner_radius=8,
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.url_entry.bind("<Button-3>", lambda e: self._show_context_menu(e, self.url_entry))
        self.url_entry.bind("<Return>", lambda e: self._start_download())

        ctk.CTkButton(
            url_frame, text="📋", width=44, height=44,
            fg_color="#151515", hover_color="#252525", text_color="#bbbbbb",
            font=("Segoe UI", 14), corner_radius=8, border_width=2, border_color="#333333",
            command=lambda: self._paste_to_entry(self.url_entry),
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            url_frame, text="🗑", width=44, height=44,
            fg_color="#151515", hover_color="#3a1515", text_color="#bbbbbb",
            font=("Segoe UI", 14), corner_radius=8, border_width=2, border_color="#333333",
            command=lambda: self._clear_entry(self.url_entry),
        ).pack(side="left")

        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.pack(fill="x", padx=12, pady=6)

        self.download_btn = ctk.CTkButton(
            btn_frame, text="Download", height=48,
            font=("Segoe UI", 15, "bold"), fg_color="#ffffff", hover_color="#cccccc",
            text_color="#000000", corner_radius=8, command=self._start_download,
        )
        self.download_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.cancel_btn = ctk.CTkButton(
            btn_frame, text="⏹ Stop", height=48, width=100,
            fg_color="#cc0000", hover_color="#990000", text_color="#bbbbbb",
            font=("Segoe UI", 12, "bold"), corner_radius=8,
            command=self._cancel_download, state="disabled",
        )
        self.cancel_btn.pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            btn_frame, text="📁 Open Folder", height=48, width=140,
            fg_color="#151515", hover_color="#252525", text_color="#bbbbbb",
            font=("Segoe UI", 12), corner_radius=8, border_width=2, border_color="#333333",
            command=open_downloads_folder,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            btn_frame, text="🗑 Clear log", height=48, width=100,
            fg_color="#151515", hover_color="#252525", text_color="#bbbbbb",
            font=("Segoe UI", 11), corner_radius=8, border_width=2, border_color="#333333",
            command=lambda: self._clear_log(self.download_log),
        ).pack(side="right")

        # Чекбокс: скачать весь плейлист/сет
        playlist_frame = ctk.CTkFrame(tab, fg_color="transparent")
        playlist_frame.pack(fill="x", padx=14, pady=(0, 4))

        self._playlist_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            playlist_frame,
            text="Download full playlist / set",
            variable=self._playlist_var,
            font=("Segoe UI", 11),
            text_color="#888888",
            fg_color="#ffffff",
            hover_color="#cccccc",
            checkmark_color="#000000",
            border_color="#444444",
            corner_radius=4,
        ).pack(side="left")

        ctk.CTkFrame(tab, fg_color="#222222", height=2).pack(fill="x", padx=12, pady=(12, 6))

        progress_frame = ctk.CTkFrame(tab, fg_color="transparent")
        progress_frame.pack(fill="x", padx=12, pady=(4, 2))

        self.download_progress = ctk.CTkProgressBar(
            progress_frame, height=8, fg_color="#111111",
            progress_color="#ffffff", corner_radius=4,
        )
        self.download_progress.pack(side="left", fill="x", expand=True, padx=(0, 12))
        self.download_progress.set(0)

        self.download_status = ctk.CTkLabel(
            progress_frame, text="Ready", font=("Segoe UI", 12),
            text_color="#555555", width=70,
        )
        self.download_status.pack(side="right")

        self.download_log = ctk.CTkTextbox(
            tab, font=("Consolas", 12), fg_color="#080808",
            text_color="#cccccc", border_color="#252525", border_width=2,
            corner_radius=8, height=250,
        )
        self.download_log.pack(fill="both", expand=True, padx=12, pady=(8, 12))
        self._block_log_input(self.download_log)

    def _start_download(self):
        url = self.url_entry.get().strip()
        if not url:
            self._smart_log(self.download_log, "⚠ Please paste a URL first")
            return
        if not is_valid_url(url):
            self._smart_log(self.download_log, "⚠ Invalid URL — supported: SoundCloud, YouTube")
            return

        playlist = getattr(self, '_playlist_var', None)
        playlist_mode = bool(playlist.get()) if playlist else False

        self._log_header(self.download_log, "NEW DOWNLOAD")
        self.download_btn.configure(state="disabled", text="⏳ Downloading...")
        self.cancel_btn.configure(state="normal")
        self.download_progress.set(0)
        self.downloader.download(url, playlist=playlist_mode)

    def _cancel_download(self):
        self.downloader.cancel()
        self.cancel_btn.configure(state="disabled")

    def _log_download(self, text):
        self._smart_log(self.download_log, text)

    def _update_download_progress(self, value):
        self.download_progress.set(value)
        self.download_status.configure(text=f"{int(value * 100)}%", text_color="#ffffff")

    def _on_download_done(self, success):
        self.download_btn.configure(state="normal", text="Download MP3")
        self.cancel_btn.configure(state="disabled")
        if success:
            self.download_status.configure(text="✅ Done", text_color="#5cdb5c")
        else:
            self.download_status.configure(text="❌ Failed", text_color="#ff5555")
            self.download_progress.set(0)
        self._log_separator(self.download_log)

    # ============================================
    # ВКЛАДКА: MONITOR
    # ============================================
    def _build_monitor_tab(self):
        tab = self.tab_monitor

        add_frame = ctk.CTkFrame(tab, fg_color="transparent")
        add_frame.pack(fill="x", padx=12, pady=(15, 6))

        self.artist_entry = ctk.CTkEntry(
            add_frame, placeholder_text="Auto-pastes SoundCloud artist URLs...", height=40,
            font=("Segoe UI", 13), fg_color="#0a0a0a", border_color="#333333",
            border_width=2, text_color="#ffffff", placeholder_text_color="#555555",
            corner_radius=8,
        )
        self.artist_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.artist_entry.bind("<Button-3>", lambda e: self._show_context_menu(e, self.artist_entry))
        self.artist_entry.bind("<Return>", lambda e: self._add_artist())

        ctk.CTkButton(
            add_frame, text="🗑", width=40, height=40,
            fg_color="#151515", hover_color="#3a1515", text_color="#bbbbbb",
            font=("Segoe UI", 14), corner_radius=8, border_width=2, border_color="#333333",
            command=lambda: self._clear_entry(self.artist_entry),
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            add_frame, text="➕ Add", width=85, height=40,
            fg_color="#151515", hover_color="#252525", text_color="#bbbbbb",
            font=("Segoe UI", 12), corner_radius=8, border_width=2, border_color="#333333",
            command=self._add_artist,
        ).pack(side="right")

        list_label_frame = ctk.CTkFrame(tab, fg_color="transparent")
        list_label_frame.pack(fill="x", padx=14, pady=(8, 2))

        ctk.CTkLabel(
            list_label_frame, text="  ▸ ARTIST LIST", font=("Segoe UI", 11, "bold"),
            text_color="#888888", anchor="w",
        ).pack(side="left")

        self._remove_btn = ctk.CTkButton(
            list_label_frame, text="🗑 Remove selected", height=24, width=130,
            fg_color="transparent", hover_color="#3a1515", text_color="#666666",
            font=("Segoe UI", 10), corner_radius=6, border_width=1, border_color="#333333",
            command=self._remove_selected_artist,
        )
        self._remove_btn.pack(side="right")

        self.artist_listbox = ctk.CTkTextbox(
            tab, height=90, font=("Consolas", 12), fg_color="#080808",
            text_color="#cccccc", border_color="#252525", border_width=2, corner_radius=8,
        )
        self.artist_listbox.pack(fill="x", padx=12, pady=(0, 5))
        self._block_log_input(self.artist_listbox)
        self._setup_artist_tags()
        self._refresh_artists()

        # Правый клик по списку артистов
        self.artist_listbox._textbox.bind(
            "<Button-3>", self._show_artist_context_menu
        )
        self.artist_listbox._textbox.bind(
            "<Button-1>", self._on_artist_click
        )

        ctk.CTkFrame(tab, fg_color="#222222", height=2).pack(fill="x", padx=12, pady=(8, 6))

        monitor_btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        monitor_btn_frame.pack(fill="x", padx=12, pady=6)

        self.check_btn = ctk.CTkButton(
            monitor_btn_frame, text="Check All Artists", height=48,
            font=("Segoe UI", 14, "bold"), fg_color="#ffffff", hover_color="#cccccc",
            text_color="#000000", corner_radius=8, command=self._start_monitor,
        )
        self.check_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.stop_btn = ctk.CTkButton(
            monitor_btn_frame, text="⏹ Stop", height=48, width=90,
            fg_color="#cc0000", hover_color="#990000", text_color="#bbbbbb",
            font=("Segoe UI", 12, "bold"), corner_radius=8,
            command=self._stop_monitor, state="disabled",
        )
        self.stop_btn.pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            monitor_btn_frame, text="🗑 Clear log", height=48, width=100,
            fg_color="#151515", hover_color="#252525", text_color="#bbbbbb",
            font=("Segoe UI", 11), corner_radius=8, border_width=2, border_color="#333333",
            command=lambda: self._clear_log(self.monitor_log),
        ).pack(side="right")

        self.monitor_progress = ctk.CTkProgressBar(
            tab, height=8, fg_color="#111111", progress_color="#ffffff", corner_radius=4,
        )
        self.monitor_progress.pack(fill="x", padx=12, pady=(8, 4))
        self.monitor_progress.set(0)

        self.monitor_log = ctk.CTkTextbox(
            tab, font=("Consolas", 12), fg_color="#080808",
            text_color="#cccccc", border_color="#252525", border_width=2,
            corner_radius=8, height=250,
        )
        self.monitor_log.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self._block_log_input(self.monitor_log)

    def _setup_artist_tags(self):
        widget = self.artist_listbox._textbox
        widget.tag_configure("artist_name", foreground="#ffffff", font=("Consolas", 12, "bold"))
        widget.tag_configure("artist_icon", foreground="#5cb8ff", font=("Consolas", 12, "bold"))
        widget.tag_configure("empty", foreground="#555555", font=("Consolas", 12, "italic"))
        widget.tag_configure("number", foreground="#666666", font=("Consolas", 11))
        widget.tag_configure("selected_line", background="#1a1a2e")

    def _add_artist(self):
        url = self.artist_entry.get().strip()
        if not url:
            return
        if self.monitor.add_artist(url):
            self.artist_entry.delete(0, "end")
            self._refresh_artists()

    def _on_artist_click(self, event):
        """Запомнить строку на которую кликнули"""
        widget = self.artist_listbox._textbox
        index = widget.index(f"@{event.x},{event.y}")
        line_num = int(index.split('.')[0])
        widget.tag_remove("selected_line", "1.0", "end")
        widget.tag_add("selected_line", f"{line_num}.0", f"{line_num}.end")
        self._selected_artist_line = line_num

    def _get_selected_artist_url(self):
        """Получить URL артиста по выбранной строке"""
        line = getattr(self, '_selected_artist_line', None)
        if line is None:
            return None
        artists = self.monitor.get_artists()
        # Строки нумеруются с 1, но первая строка пустая если нет артистов
        idx = line - 1
        if 0 <= idx < len(artists):
            return artists[idx]
        return None

    def _remove_selected_artist(self):
        url = self._get_selected_artist_url()
        if not url:
            self.after(0, self._smart_log, self.monitor_log, "⚠ Select an artist first (click on the line)")
            return
        self.monitor.remove_artist(url)
        self._selected_artist_line = None
        self._refresh_artists()

    def _show_artist_context_menu(self, event):
        widget = self.artist_listbox._textbox
        index = widget.index(f"@{event.x},{event.y}")
        line_num = int(index.split('.')[0])
        widget.tag_remove("selected_line", "1.0", "end")
        widget.tag_add("selected_line", f"{line_num}.0", f"{line_num}.end")
        self._selected_artist_line = line_num

        artists = self.monitor.get_artists()
        idx = line_num - 1
        if not (0 <= idx < len(artists)):
            return

        artist_name = artists[idx].rstrip('/').split('/')[-1]
        menu = tk.Menu(
            self, tearoff=0, bg="#151515", fg="#dddddd",
            activebackground="#ffffff", activeforeground="#000000",
            borderwidth=1, font=("Segoe UI", 10),
        )
        menu.add_command(
            label=f"  🗑 Remove {artist_name}",
            command=self._remove_selected_artist,
        )
        menu.add_separator()
        menu.add_command(
            label="  📋 Copy URL",
            command=lambda: (self.clipboard_clear(), self.clipboard_append(artists[idx])),
        )
        menu.tk_popup(event.x_root, event.y_root)

    def _refresh_artists(self):
        artists = self.monitor.get_artists()
        widget = self.artist_listbox._textbox
        widget.configure(state="normal")
        widget.delete("1.0", "end")

        if artists:
            for i, artist in enumerate(artists, 1):
                name = artist.rstrip('/').split('/')[-1]
                widget.insert("end", f"  {i:>2}. ", "number")
                widget.insert("end", "👤  ", "artist_icon")
                widget.insert("end", f"{name}\n", "artist_name")
        else:
            widget.insert("end", "\n", "empty")
            widget.insert("end", "       No artists added yet — paste a URL above\n", "empty")

    def _start_monitor(self):
        self._log_header(self.monitor_log, "MONITOR SCAN STARTED")
        self.check_btn.configure(state="disabled", text="⏳ Checking...")
        self.stop_btn.configure(state="normal")
        self.monitor_progress.set(0)
        self.monitor.check_all()

    def _stop_monitor(self):
        self.monitor.stop()
        self.stop_btn.configure(state="disabled")

    def _update_monitor_progress(self, value):
        self.monitor_progress.set(value)

    def _on_monitor_done(self, success):
        self.check_btn.configure(state="normal", text="🔍 Check All Artists")
        self.stop_btn.configure(state="disabled")
        self._refresh_artists()
        # Уведомление: звуковой сигнал + мигание заголовка (п.13)
        self.bell()
        self._flash_title("✅ Monitor done!" if success else "⚠ Monitor finished")

    def _flash_title(self, message, times=6):
        """Мигание заголовка окна для уведомления о завершении"""
        original = self.title()

        def _blink(n):
            if n <= 0:
                self.title(original)
                return
            current = self.title()
            self.title(message if current == original else original)
            self.after(600, _blink, n - 1)

        _blink(times)

    def _clear_log(self, textbox):
        widget = textbox._textbox if hasattr(textbox, '_textbox') else textbox
        widget.configure(state="normal")
        widget.delete("1.0", "end")

    def _trim_log(self, textbox, max_lines=2000):
        """Обрезать лог если строк больше max_lines (п.9)"""
        widget = textbox._textbox if hasattr(textbox, '_textbox') else textbox
        widget.configure(state="normal")
        line_count = int(widget.index("end-1c").split(".")[0])
        if line_count > max_lines:
            widget.delete("1.0", f"{line_count - max_lines}.0")

    def _apply_monitor_settings(self):
        try:
            max_tracks = int(self._max_tracks_var.get())
            days_back = int(self._days_back_var.get())
            if max_tracks < 1 or days_back < 1:
                raise ValueError
        except (ValueError, AttributeError):
            self._smart_log(self.monitor_log, "⚠ Invalid values — enter positive integers")
            return

        set_monitor_settings(days_back=days_back, max_tracks=max_tracks)
        # Обновляем совместимые константы для старых импортов
        config.MONITOR_MAX_TRACKS = max_tracks
        config.MONITOR_DATE_AFTER = f"today-{days_back}days"
        self._smart_log(
            self.monitor_log,
            f"✅ Monitor settings applied: max {max_tracks} tracks, last {days_back} days",
        )

    # ============================================
    # ВКЛАДКА: SETTINGS
    # ============================================
    def _build_settings_tab(self):
        tab = self.tab_settings

        # Скроллируемый контейнер
        scroll = ctk.CTkScrollableFrame(
            tab, fg_color="#000000",
            scrollbar_button_color="#333333",
            scrollbar_button_hover_color="#555555",
        )
        scroll.pack(fill="both", expand=True, padx=0, pady=0)

        # ============================================
        # КАРТОЧКА: ПАПКА
        # ============================================
        path_frame = ctk.CTkFrame(
            scroll, fg_color="#080808", corner_radius=10,
            border_width=2, border_color="#252525",
        )
        path_frame.pack(fill="x", padx=12, pady=(15, 6))

        path_header = ctk.CTkFrame(path_frame, fg_color="transparent")
        path_header.pack(fill="x", padx=15, pady=(12, 0))

        ctk.CTkLabel(path_header, text="📁  ", font=("Segoe UI", 14)).pack(side="left")
        ctk.CTkLabel(
            path_header, text="DOWNLOADS FOLDER", font=("Segoe UI", 11, "bold"),
            text_color="#888888",
        ).pack(side="left")

        ctk.CTkLabel(
            path_frame, text=DOWNLOADS_PATH, font=("Consolas", 11),
            text_color="#dddddd", anchor="w", justify="left", wraplength=620,
        ).pack(anchor="w", padx=15, pady=(4, 12))

        # ============================================
        # КАРТОЧКА: OAUTH ТОКЕН
        # ============================================
        oauth_frame = ctk.CTkFrame(
            scroll, fg_color="#080808", corner_radius=10,
            border_width=2, border_color="#252525",
        )
        oauth_frame.pack(fill="x", padx=12, pady=8)

        oauth_header = ctk.CTkFrame(oauth_frame, fg_color="transparent")
        oauth_header.pack(fill="x", padx=15, pady=(12, 0))

        ctk.CTkLabel(oauth_header, text="🔑  ", font=("Segoe UI", 14)).pack(side="left")
        ctk.CTkLabel(
            oauth_header, text="SOUNDCLOUD OAUTH TOKEN", font=("Segoe UI", 11, "bold"),
            text_color="#888888",
        ).pack(side="left")

        self.oauth_status = ctk.CTkLabel(
            oauth_header, text="", font=("Segoe UI", 11, "bold"),
        )
        self.oauth_status.pack(side="right")

        ctk.CTkLabel(
            oauth_frame,
            text="Bypasses speed limits",
            font=("Segoe UI", 10), text_color="#555555",
            anchor="w", justify="left",
        ).pack(anchor="w", padx=15, pady=(2, 8))

        # Поле ввода + кнопки
        oauth_input_frame = ctk.CTkFrame(oauth_frame, fg_color="transparent")
        oauth_input_frame.pack(fill="x", padx=15, pady=(0, 8))

        self.oauth_entry = ctk.CTkEntry(
            oauth_input_frame,
            placeholder_text="Paste OAuth token here...",
            height=38, font=("Consolas", 11),
            fg_color="#0a0a0a", border_color="#333333", border_width=2,
            text_color="#ffffff", placeholder_text_color="#444444",
            corner_radius=8, show="•",
        )
        self.oauth_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.oauth_entry.bind("<Button-3>", lambda e: self._show_context_menu(e, self.oauth_entry))
        self.oauth_entry.bind("<KeyRelease>", lambda e: self._update_oauth_status())

        self.oauth_show_btn = ctk.CTkButton(
            oauth_input_frame, text="👁", width=38, height=38,
            fg_color="#151515", hover_color="#252525", text_color="#bbbbbb",
            font=("Segoe UI", 14), corner_radius=8, border_width=2, border_color="#333333",
            command=self._toggle_oauth_visibility,
        )
        self.oauth_show_btn.pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            oauth_input_frame, text="🗑", width=38, height=38,
            fg_color="#151515", hover_color="#3a1515", text_color="#bbbbbb",
            font=("Segoe UI", 14), corner_radius=8, border_width=2, border_color="#333333",
            command=self._clear_oauth,
        ).pack(side="left")

        # Кнопки действий
        oauth_actions = ctk.CTkFrame(oauth_frame, fg_color="transparent")
        oauth_actions.pack(fill="x", padx=15, pady=(0, 12))

        ctk.CTkButton(
            oauth_actions, text="💾 Save Token", height=36,
            fg_color="#ffffff", hover_color="#cccccc", text_color="#000000",
            font=("Segoe UI", 12, "bold"), corner_radius=8,
            command=self._save_oauth,
        ).pack(side="left", padx=(0, 6), fill="x", expand=True)

        ctk.CTkButton(
            oauth_actions, text="❓ How to get?", height=36,
            fg_color="#151515", hover_color="#252525", text_color="#bbbbbb",
            font=("Segoe UI", 11), corner_radius=8,
            border_width=2, border_color="#333333",
            command=self._show_oauth_help,
        ).pack(side="left", fill="x", expand=True)

        self._load_oauth_to_field()

        # ============================================
        # КАРТОЧКА: MONITOR SETTINGS
        # ============================================
        monitor_cfg_frame = ctk.CTkFrame(
            scroll, fg_color="#080808", corner_radius=10,
            border_width=2, border_color="#252525",
        )
        monitor_cfg_frame.pack(fill="x", padx=12, pady=8)

        mon_header = ctk.CTkFrame(monitor_cfg_frame, fg_color="transparent")
        mon_header.pack(fill="x", padx=15, pady=(12, 0))

        ctk.CTkLabel(mon_header, text="🔍  ", font=("Segoe UI", 14)).pack(side="left")
        ctk.CTkLabel(
            mon_header, text="MONITOR SETTINGS", font=("Segoe UI", 11, "bold"),
            text_color="#888888",
        ).pack(side="left")

        mon_grid = ctk.CTkFrame(monitor_cfg_frame, fg_color="transparent")
        mon_grid.pack(fill="x", padx=15, pady=(10, 12))

        # Max tracks per artist
        tracks_row = ctk.CTkFrame(mon_grid, fg_color="transparent")
        tracks_row.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            tracks_row, text="Max tracks per artist:", font=("Segoe UI", 11),
            text_color="#aaaaaa", anchor="w", width=180,
        ).pack(side="left")

        self._max_tracks_var = ctk.StringVar(value=str(MONITOR_MAX_TRACKS))
        tracks_entry = ctk.CTkEntry(
            tracks_row, textvariable=self._max_tracks_var,
            width=70, height=30, font=("Consolas", 12),
            fg_color="#0a0a0a", border_color="#333333", border_width=2,
            text_color="#ffffff", corner_radius=6,
        )
        tracks_entry.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            tracks_row, text="(how many recent tracks to scan)",
            font=("Segoe UI", 10), text_color="#555555",
        ).pack(side="left")

        # Days back
        days_row = ctk.CTkFrame(mon_grid, fg_color="transparent")
        days_row.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            days_row, text="Look back, days:", font=("Segoe UI", 11),
            text_color="#aaaaaa", anchor="w", width=180,
        ).pack(side="left")

        self._days_back_var = ctk.StringVar(value="7")
        days_entry = ctk.CTkEntry(
            days_row, textvariable=self._days_back_var,
            width=70, height=30, font=("Consolas", 12),
            fg_color="#0a0a0a", border_color="#333333", border_width=2,
            text_color="#ffffff", corner_radius=6,
        )
        days_entry.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(
            days_row, text="(skip tracks older than N days)",
            font=("Segoe UI", 10), text_color="#555555",
        ).pack(side="left")

        ctk.CTkButton(
            mon_grid, text="💾 Apply", height=30, width=100,
            fg_color="#ffffff", hover_color="#cccccc", text_color="#000000",
            font=("Segoe UI", 11, "bold"), corner_radius=6,
            command=self._apply_monitor_settings,
        ).pack(anchor="w", pady=(4, 0))

        # ============================================
        # КАРТОЧКА: AUTO-PASTE
        # ============================================
        auto_frame = ctk.CTkFrame(
            scroll, fg_color="#080808", corner_radius=10,
            border_width=2, border_color="#252525",
        )
        auto_frame.pack(fill="x", padx=12, pady=8)

        auto_header = ctk.CTkFrame(auto_frame, fg_color="transparent")
        auto_header.pack(fill="x", padx=15, pady=(12, 0))

        ctk.CTkLabel(auto_header, text="🔄  ", font=("Segoe UI", 14)).pack(side="left")
        ctk.CTkLabel(
            auto_header, text="AUTO-PASTE", font=("Segoe UI", 11, "bold"),
            text_color="#888888",
        ).pack(side="left")

        auto_inner = ctk.CTkFrame(auto_frame, fg_color="transparent")
        auto_inner.pack(fill="x", padx=15, pady=(8, 12))

        self.auto_paste_switch = ctk.CTkSwitch(
            auto_inner, text="Auto-paste SoundCloud links from clipboard",
            font=("Segoe UI", 11), text_color="#cccccc",
            progress_color="#5cdb5c", button_color="#ffffff",
            command=self._toggle_auto_paste,
        )
        self.auto_paste_switch.pack(anchor="w")
        self.auto_paste_switch.select()

        # ============================================
        # КАРТОЧКА: ABOUT
        # ============================================
        info_frame = ctk.CTkFrame(
            scroll, fg_color="#080808", corner_radius=10,
            border_width=2, border_color="#252525",
        )
        info_frame.pack(fill="x", padx=12, pady=8)

        info_header = ctk.CTkFrame(info_frame, fg_color="transparent")
        info_header.pack(fill="x", padx=15, pady=(12, 0))

        ctk.CTkLabel(info_header, text="ℹ️  ", font=("Segoe UI", 14)).pack(side="left")
        ctk.CTkLabel(
            info_header, text="ABOUT", font=("Segoe UI", 11, "bold"),
            text_color="#888888",
        ).pack(side="left")

        info_grid = ctk.CTkFrame(info_frame, fg_color="transparent")
        info_grid.pack(fill="x", padx=15, pady=(8, 12))

        info_items = [
            ("Version", "1.0"),
            ("Engine", "yt-dlp + ffmpeg"),
            ("Platforms", "SoundCloud"),
        ]

        for key, value in info_items:
            row = ctk.CTkFrame(info_grid, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(
                row, text=f"{key:>12}", font=("Consolas", 11),
                text_color="#666666", width=100, anchor="e",
            ).pack(side="left", padx=(0, 10))
            ctk.CTkLabel(
                row, text=value, font=("Consolas", 11),
                text_color="#dddddd", anchor="w",
            ).pack(side="left")

        # ============================================
        # КНОПКИ ВНИЗУ
        # ============================================
        open_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        open_frame.pack(fill="x", padx=12, pady=(8, 12))

        ctk.CTkButton(
            open_frame, text="📁 Open Downloads", fg_color="#151515",
            hover_color="#252525", text_color="#bbbbbb",
            font=("Segoe UI", 12), corner_radius=8, height=42,
            border_width=2, border_color="#333333", command=open_downloads_folder,
        ).pack(side="left", padx=(0, 6), fill="x", expand=True)

        ctk.CTkButton(
            open_frame, text="📝 Open artists.txt", fg_color="#151515",
            hover_color="#252525", text_color="#bbbbbb",
            font=("Segoe UI", 12), corner_radius=8, height=42,
            border_width=2, border_color="#333333",
            command=lambda: self._open_file(ARTISTS_FILE),
        ).pack(side="left", fill="x", expand=True)

    def _toggle_auto_paste(self):
        self._clipboard_enabled = bool(self.auto_paste_switch.get())

    def _open_file(self, path):
        import subprocess, sys
        if not os.path.exists(path):
            return
        if sys.platform == 'win32':
            os.startfile(path)
        elif sys.platform == 'darwin':
            subprocess.run(['open', path])
        else:
            subprocess.run(['xdg-open', path])

    # ============================================
    # OAUTH МЕТОДЫ
    # ============================================
    def _load_oauth_to_field(self):
        token = load_oauth_token()
        if token:
            self.oauth_entry.delete(0, "end")
            self.oauth_entry.insert(0, token)
        self._update_oauth_status()

    def _update_oauth_status(self):
        token = self.oauth_entry.get().strip()
        if not token:
            self.oauth_status.configure(text="● Not set", text_color="#555555")
        elif is_valid_token(token):
            self.oauth_status.configure(text="● Active", text_color="#5cdb5c")
        else:
            self.oauth_status.configure(text="● Invalid", text_color="#ff5555")

    def _toggle_oauth_visibility(self):
        current = self.oauth_entry.cget("show")
        if current == "•":
            self.oauth_entry.configure(show="")
            self.oauth_show_btn.configure(text="🙈")
        else:
            self.oauth_entry.configure(show="•")
            self.oauth_show_btn.configure(text="👁")

    def _clear_oauth(self):
        self.oauth_entry.delete(0, "end")
        self._update_oauth_status()

    def _save_oauth(self):
        token = self.oauth_entry.get().strip()

        if not token:
            if os.path.exists(OAUTH_FILE):
                try:
                    os.remove(OAUTH_FILE)
                    self._show_oauth_message("✅ Token cleared", "#5cdb5c")
                except Exception:
                    self._show_oauth_message("❌ Failed to clear", "#ff5555")
            else:
                self._show_oauth_message("⚠ Field is empty", "#ffaa00")
            self._update_oauth_status()
            return

        if not is_valid_token(token):
            self._show_oauth_message("❌ Invalid token format", "#ff5555")
            return

        if save_oauth_token(token):
            self._show_oauth_message("✅ Token saved", "#5cdb5c")
        else:
            self._show_oauth_message("❌ Failed to save", "#ff5555")

        self._update_oauth_status()

    def _show_oauth_message(self, text, color):
        self.oauth_status.configure(text=text, text_color=color)
        self.after(2500, self._update_oauth_status)

    def _show_oauth_help(self):
        help_window = ctk.CTkToplevel(self)
        help_window.title("How to get OAuth token")
        help_window.geometry("560x540")
        help_window.configure(fg_color="#000000")
        help_window.transient(self)
        help_window.grab_set()

        help_window.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 560) // 2
        y = self.winfo_y() + (self.winfo_height() - 540) // 2
        help_window.geometry(f"+{x}+{y}")

        ctk.CTkLabel(
            help_window, text="🔑 How to get OAuth Token",
            font=("Segoe UI", 16, "bold"), text_color="#ffffff",
        ).pack(pady=(20, 5))

        ctk.CTkLabel(
            help_window, text="Follow these steps in your browser",
            font=("Segoe UI", 11), text_color="#888888",
        ).pack(pady=(0, 15))

        steps_frame = ctk.CTkScrollableFrame(
            help_window, fg_color="#080808",
            border_width=2, border_color="#252525", corner_radius=10,
        )
        steps_frame.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        steps = [
            ("1", "Login to SoundCloud", "Open soundcloud.com and sign in to your account"),
            ("2", "Open DevTools", "Press F12 (or Ctrl + Shift + I)"),
            ("3", "Go to Network tab", "Click 'Network' in DevTools panel"),
            ("4", "Filter by API", "Type 'api-v2' in the filter box"),
            ("5", "Play any track", "Click play on any SoundCloud track"),
            ("6", "Click on a request", "Find any request to api-v2.soundcloud.com"),
            ("7", "Find Authorization", "In Headers tab → Request Headers → look for:\nAuthorization: OAuth XXXXXXXXX"),
            ("8", "Copy the token", "Copy ONLY the part after 'OAuth ' (without the word)"),
            ("9", "Paste & Save", "Paste it in the field and click 'Save Token'"),
        ]

        for num, title, desc in steps:
            step = ctk.CTkFrame(steps_frame, fg_color="transparent")
            step.pack(fill="x", pady=8, padx=10)

            num_label = ctk.CTkLabel(
                step, text=num, font=("Segoe UI", 14, "bold"),
                text_color="#000000", fg_color="#ffffff",
                corner_radius=15, width=30, height=30,
            )
            num_label.pack(side="left", padx=(0, 12), anchor="n")

            text_frame = ctk.CTkFrame(step, fg_color="transparent")
            text_frame.pack(side="left", fill="x", expand=True)

            ctk.CTkLabel(
                text_frame, text=title, font=("Segoe UI", 12, "bold"),
                text_color="#ffffff", anchor="w",
            ).pack(fill="x")

            ctk.CTkLabel(
                text_frame, text=desc, font=("Segoe UI", 10),
                text_color="#aaaaaa", anchor="w", justify="left",
                wraplength=400,
            ).pack(fill="x", pady=(2, 0))

        example_frame = ctk.CTkFrame(
            help_window, fg_color="#0a0a0a",
            border_width=1, border_color="#333333", corner_radius=8,
        )
        example_frame.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkLabel(
            example_frame, text="Example:", font=("Segoe UI", 10, "bold"),
            text_color="#888888", anchor="w",
        ).pack(anchor="w", padx=12, pady=(8, 2))

        ctk.CTkLabel(
            example_frame,
            text="2-294412-987654321-AbCdEfGhIjKlMn",
            font=("Consolas", 11), text_color="#5cdb5c", anchor="w",
        ).pack(anchor="w", padx=12, pady=(0, 8))

        ctk.CTkButton(
            help_window, text="Got it", height=40,
            fg_color="#ffffff", hover_color="#cccccc", text_color="#000000",
            font=("Segoe UI", 13, "bold"), corner_radius=8,
            command=help_window.destroy,
        ).pack(fill="x", padx=20, pady=(0, 20))