import os
import time
import threading
from datetime import datetime, timedelta
from config import (
    DOWNLOADS_PATH,
    ARTISTS_FILE,
    ARCHIVE_FILE,
    FFMPEG_PATH,
    YTDLP_OPTIONS as YTDLP_OPTIONS,
    POSTPROCESSORS,
    get_monitor_settings,
)
from utils import ensure_downloads_folder


class Monitor:
    def __init__(self, log_callback=None, progress_callback=None, done_callback=None):
        self.log = log_callback or print
        self.progress = progress_callback or (lambda x: None)
        self.done = done_callback or (lambda x: None)
        self._is_running = False
        self._stop_flag = False

    @property
    def is_running(self):
        return self._is_running

    def stop(self):
        self._stop_flag = True

    def get_artists(self):
        if not os.path.exists(ARTISTS_FILE):
            return []
        with open(ARTISTS_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        artists = []
        seen = set()
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                if line.endswith('/tracks'):
                    line = line[:-7]
                if line.endswith('/'):
                    line = line[:-1]
                if line not in seen:
                    seen.add(line)
                    artists.append(line)
        # Если были дубликаты — перезаписать файл без них
        if len(artists) < sum(1 for l in lines if l.strip() and not l.strip().startswith('#')):
            self.save_artists(artists)
        return artists

    def save_artists(self, artists):
        with open(ARTISTS_FILE, 'w', encoding='utf-8') as f:
            for artist in artists:
                f.write(artist + '\n')

    def add_artist(self, url):
        url = url.strip()
        if url.endswith('/tracks'):
            url = url[:-7]
        if url.endswith('/'):
            url = url[:-1]

        # Валидация: должна быть ссылка на SoundCloud
        import re
        pattern = r'^https?://(www\.)?(soundcloud\.com|on\.soundcloud\.com|m\.soundcloud\.com)/.+'
        if not re.match(pattern, url):
            self.log(f"⚠ Invalid URL — must be a SoundCloud artist link")
            return False

        artists = self.get_artists()
        if url in artists:
            self.log(f"⚠ Already in list: {url}")
            return False
        artists.append(url)
        self.save_artists(artists)
        self.log(f"✅ Added: {url}")
        return True

    def remove_artist(self, url):
        artists = self.get_artists()
        if url in artists:
            artists.remove(url)
            self.save_artists(artists)
            self.log(f"🗑 Removed: {url}")
            return True
        return False

    def check_all(self, days_back=None, max_tracks=None):
        if self._is_running:
            self.log("⚠ Monitor is already running...")
            return
        # Читаем из явного хранилища если не переданы напрямую
        settings = get_monitor_settings()
        self._run_days_back = days_back if days_back is not None else settings["days_back"]
        self._run_max_tracks = max_tracks if max_tracks is not None else settings["max_tracks"]
        self._stop_flag = False
        thread = threading.Thread(target=self._check_all_thread, daemon=True)
        thread.start()

    def _load_archive_set(self):
        """Загрузить архив в set для O(1) проверки"""
        if not os.path.exists(ARCHIVE_FILE):
            return set()
        try:
            with open(ARCHIVE_FILE, 'r', encoding='utf-8') as f:
                return set(line.strip() for line in f if line.strip())
        except Exception:
            return set()

    def _check_all_thread(self):
        self._is_running = True
        start_time = datetime.now()

        try:
            import yt_dlp
        except ImportError:
            self.log("❌ yt-dlp not installed!")
            self.done(False)
            self._is_running = False
            return

        if not os.path.exists(FFMPEG_PATH):
            self.log("❌ ffmpeg.exe not found!")
            self.done(False)
            self._is_running = False
            return

        artists = self.get_artists()
        if not artists:
            self.log("⚠ No artists in artists.txt")
            self.done(False)
            self._is_running = False
            return

        ensure_downloads_folder()

        # Загружаем архив один раз в set для быстрой проверки (п.6)
        archive_set = self._load_archive_set()

        total = len(artists)
        new_count = 0
        no_new_count = 0
        error_count = 0
        total_new_tracks = 0

        # Используем параметры, переданные в check_all()
        days_back = getattr(self, '_run_days_back', 7)
        max_tracks = getattr(self, '_run_max_tracks', 15)
        cutoff_date = datetime.now() - timedelta(days=days_back)
        cutoff_str = cutoff_date.strftime("%Y%m%d")

        self.log("═" * 50)
        self.log("🔍 SoundCloud Monitor")
        self.log(f"📅 Looking for tracks after: {cutoff_date.strftime('%d.%m.%Y')}")
        self.log(f"👤 Artists to check: {total}")
        self.log(f"🔢 Max tracks per artist: {max_tracks}")
        self.log(f"⏰ Started at: {start_time.strftime('%H:%M:%S')}")
        self.log("═" * 50)

        artists_with_new = []
        artists_without_new = []
        artists_with_errors = []

        for i, artist_url in enumerate(artists):
            if self._stop_flag:
                self.log("\n⏹ Stopped by user")
                break

            # Пауза между артистами чтобы не получить 403 от SoundCloud
            if i > 0:
                time.sleep(2)

            self.progress(i / total)

            artist_name = artist_url.rstrip('/').split('/')[-1]
            tracks_url = artist_url + "/tracks"

            self.log(f"\n{'─' * 50}")
            self.log(f"[{i + 1}/{total}] 👤 {artist_name}")
            self.log(f"  🔗 {tracks_url}")

            try:
                artist_result = self._check_artist(yt_dlp, tracks_url, artist_name, cutoff_str, archive_set, max_tracks)

                if artist_result['downloaded'] > 0:
                    new_count += 1
                    total_new_tracks += artist_result['downloaded']
                    artists_with_new.append({
                        'name': artist_name,
                        'tracks': artist_result['track_names'],
                        'count': artist_result['downloaded'],
                    })
                    self.log(f"  ✅ New tracks downloaded: {artist_result['downloaded']}")
                else:
                    no_new_count += 1
                    artists_without_new.append(artist_name)
                    checked = artist_result['checked']
                    skipped = artist_result['skipped']
                    already = artist_result['already_downloaded']
                    self.log(f"  — No new tracks (checked: {checked}, skipped old: {skipped}, already downloaded: {already})")

            except Exception as e:
                self.log(f"  ❌ Error: {e}")
                artists_with_errors.append(artist_name)
                error_count += 1

        # ============================================
        # ИТОГОВЫЙ ОТЧЁТ
        # ============================================
        end_time = datetime.now()
        elapsed = end_time - start_time
        minutes = int(elapsed.total_seconds() // 60)
        seconds = int(elapsed.total_seconds() % 60)

        self.log(f"\n{'═' * 50}")
        self.log("📊 MONITOR REPORT")
        self.log(f"{'═' * 50}")
        self.log(f"⏰ Time: {minutes}m {seconds}s")
        self.log(f"👤 Checked: {new_count + no_new_count + error_count}/{total} artists")

        if artists_with_new:
            self.log(f"\n🆕 Artists with new tracks [{len(artists_with_new)}]:")
            self.log(f"{'─' * 40}")
            for info in artists_with_new:
                self.log(f"  ✅ {info['name']} ({info['count']} tracks)")
                for track in info['tracks']:
                    self.log(f"     🎵 {track}")

        if artists_without_new:
            self.log(f"\n— No new tracks [{len(artists_without_new)}]:")
            self.log(f"{'─' * 40}")
            for name in artists_without_new:
                self.log(f"  — {name}")

        if artists_with_errors:
            self.log(f"\n❌ Errors [{len(artists_with_errors)}]:")
            self.log(f"{'─' * 40}")
            for name in artists_with_errors:
                self.log(f"  ❌ {name}")

        self.log(f"\n{'═' * 50}")
        self.log(f"🎵 Total new tracks downloaded: {total_new_tracks}")
        self.log(f"📁 Saved to: {DOWNLOADS_PATH}")
        self.log(f"{'═' * 50}")

        self.progress(1.0)
        self.done(True)
        self._is_running = False

    def _check_artist(self, yt_dlp, tracks_url, artist_name, cutoff_str, archive_set, max_tracks=15):
        """
        Двухэтапная проверка артиста:
        1. Получить список треков (extract_flat='in_playlist' — быстро, без доп. запросов)
        2. Отфильтровать по дате
        3. Скачать только новые
        """
        result = {
            'downloaded': 0,
            'checked': 0,
            'skipped': 0,
            'already_downloaded': 0,
            'track_names': [],
        }

        # ============================================
        # ЭТАП 1: Получить список треков (плоско, без лишних запросов)
        # ============================================
        self.log("  📋 Fetching track list...")

        extract_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': 'in_playlist',
            'playlistend': max_tracks,
            'socket_timeout': 30,
            'retries': 5,
            'sleep_interval': 1,
            'sleep_interval_requests': 1,
        }

        # Retry при 403 — ждём и повторяем
        for attempt in range(3):
            try:
                with yt_dlp.YoutubeDL(extract_opts) as ydl:
                    playlist_info = ydl.extract_info(tracks_url, download=False)
                break  # успех
            except Exception as e:
                err_str = str(e)
                if '403' in err_str and attempt < 2:
                    wait = (attempt + 1) * 10
                    self.log(f"  ⚠ 403 rate limit, waiting {wait}s...")
                    time.sleep(wait)
                    continue
                self.log(f"  ❌ Failed to fetch track list: {e}")
                raise

        if not playlist_info:
            self.log("  ⚠ No playlist info returned")
            return result

        entries = playlist_info.get('entries', [])
        if not entries:
            self.log("  ⚠ No tracks found")
            return result

        # Преобразуем генератор в список
        track_list = []
        for entry in entries:
            if entry is not None:
                track_list.append(entry)

        self.log(f"  📋 Found {len(track_list)} tracks, checking dates...")

        # ============================================
        # ЭТАП 2: Фильтрация по дате
        # ============================================
        tracks_to_download = []

        # Опции для точечного запроса метаданных одного трека
        single_track_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'socket_timeout': 20,
            'retries': 3,
            'sleep_interval': 1,
        }

        for track in track_list:
            if self._stop_flag:
                break

            result['checked'] += 1

            title = track.get('title', 'Unknown')
            upload_date = track.get('upload_date')
            track_id = track.get('id', '')
            track_url = track.get('webpage_url') or track.get('url', '')
            duration = track.get('duration', 0)

            # Попытка 1: вывести upload_date из timestamp (unix epoch)
            # SoundCloud всегда кладёт 'timestamp' даже в flat-режиме
            if not upload_date:
                ts = track.get('timestamp')
                if ts:
                    try:
                        upload_date = datetime.utcfromtimestamp(int(ts)).strftime("%Y%m%d")
                    except (ValueError, OSError, OverflowError):
                        pass

            # Попытка 2: парсинг строковых дат (created_at, release_date и т.п.)
            # SoundCloud иногда отдаёт "2024-03-15T12:00:00Z" или "2024-03-15"
            if not upload_date:
                for date_key in ('created_at', 'release_date', 'display_date', 'modified_date'):
                    raw = track.get(date_key)
                    if raw and isinstance(raw, str):
                        # Убираем время, берём только дату
                        date_part = raw[:10].replace('-', '')
                        if len(date_part) == 8 and date_part.isdigit():
                            upload_date = date_part
                            break

            # Попытка 3: точечный запрос метаданных (крайний случай)
            if not upload_date and track_url:
                time.sleep(1)
                try:
                    with yt_dlp.YoutubeDL(single_track_opts) as ydl:
                        info = ydl.extract_info(track_url, download=False)
                    if info:
                        upload_date = info.get('upload_date') or upload_date
                        if not upload_date:
                            ts = info.get('timestamp')
                            if ts:
                                try:
                                    upload_date = datetime.utcfromtimestamp(int(ts)).strftime("%Y%m%d")
                                except (ValueError, OSError, OverflowError):
                                    pass
                        if not upload_date:
                            for date_key in ('created_at', 'release_date', 'display_date'):
                                raw = info.get(date_key)
                                if raw and isinstance(raw, str):
                                    date_part = raw[:10].replace('-', '')
                                    if len(date_part) == 8 and date_part.isdigit():
                                        upload_date = date_part
                                        break
                        duration = info.get('duration') or duration
                        track_id = info.get('id') or track_id
                except Exception:
                    pass  # не удалось — продолжаем без даты

            # Форматируем длительность
            if duration:
                dur_min = int(duration // 60)
                dur_sec = int(duration % 60)
                dur_str = f"{dur_min}:{dur_sec:02d}"
            else:
                dur_str = "?:??"

            # Проверяем дату
            if not upload_date:
                self.log(f"  ⚠ {title} — no date, skipping")
                result['skipped'] += 1
                continue

            try:
                track_date = datetime.strptime(upload_date, "%Y%m%d")
                date_str = track_date.strftime("%d.%m.%Y")
                days_ago = (datetime.now() - track_date).days
            except ValueError:
                self.log(f"  ⚠ {title} — invalid date: {upload_date}")
                result['skipped'] += 1
                continue

            # Трек старше N дней — СТОП
            if upload_date < cutoff_str:
                self.log(f"  ⏭ {title}")
                self.log(f"     📅 {date_str} ({days_ago}d ago) — too old, stopping")
                result['skipped'] += 1
                break

            # Проверяем архив (O(1) поиск в set)
            archive_id = f"soundcloud {track_id}"
            if archive_id in archive_set:
                self.log(f"  ⏩ {title}")
                self.log(f"     📅 {date_str} ({days_ago}d ago) ⏱ {dur_str} — already downloaded")
                result['already_downloaded'] += 1
                continue

            # Трек новый и свежий
            self.log(f"  🆕 {title}")
            self.log(f"     📅 {date_str} ({days_ago}d ago) ⏱ {dur_str} — queued for download")

            tracks_to_download.append({
                'url': track_url,
                'title': title,
                'date': date_str,
                'days_ago': days_ago,
            })

        # ============================================
        # ЭТАП 3: Скачивание новых треков
        # ============================================
        if not tracks_to_download:
            return result

        self.log(f"\n  ⬇ Downloading {len(tracks_to_download)} new tracks...")

        output_template = os.path.join(
            DOWNLOADS_PATH,
            "%(uploader)s",
            "%(upload_date)s - %(title)s.%(ext)s"
        )

        download_opts = {
            **YTDLP_OPTIONS,
            'outtmpl': output_template,
            'download_archive': ARCHIVE_FILE,
            'no_overwrites': True,
            'postprocessors': POSTPROCESSORS,
        }

        # Убрать лишние ключи если есть
        for key in ['dateafter', 'break_on_reject', 'match_filter', 'playlistend']:
            download_opts.pop(key, None)

        for track_info in tracks_to_download:
            if self._stop_flag:
                break

            url = track_info['url']
            title = track_info['title']

            self.log(f"  ⬇ Downloading: {title}...")

            try:
                with yt_dlp.YoutubeDL(download_opts) as ydl:
                    ydl.download([url])

                result['downloaded'] += 1
                result['track_names'].append(title)
                self.log(f"  ✅ Saved: {title}")

            except Exception as e:
                self.log(f"  ❌ Failed: {title} — {e}")

        return result

