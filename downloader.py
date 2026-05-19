import os
import threading
import yt_dlp
from config import (
    DOWNLOADS_PATH,
    FFMPEG_PATH,
    YTDLP_OPTIONS,
    POSTPROCESSORS,
)
from utils import ensure_downloads_folder


class Downloader:
    def __init__(self, log_callback=None, progress_callback=None, done_callback=None):
        """
        log_callback(text)        — вывод текста в лог
        progress_callback(float)  — прогресс 0.0 - 1.0
        done_callback(success)    — завершение
        """
        self.log = log_callback or print
        self.progress = progress_callback or (lambda x: None)
        self.done = done_callback or (lambda x: None)
        self._is_running = False
        self._cancel_flag = False

    @property
    def is_running(self):
        return self._is_running

    def cancel(self):
        """Отменить текущее скачивание"""
        self._cancel_flag = True

    def _progress_hook(self, d):
        """Хук прогресса yt-dlp"""
        if self._cancel_flag:
            raise yt_dlp.utils.DownloadCancelled("Cancelled by user")

        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded = d.get('downloaded_bytes', 0)
            if total > 0:
                self.progress(downloaded / total)

            speed = d.get('speed')
            speed_str = f"{speed / 1024:.0f} KB/s" if speed else "..."
            self.log(f"⬇ Downloading... {speed_str}")

        elif d['status'] == 'finished':
            self.progress(1.0)
            self.log("✅ Download complete, converting...")

    def download(self, url, playlist=False):
        """Запуск скачивания в отдельном потоке.
        playlist=True — скачать весь плейлист/сет целиком.
        """
        if self._is_running:
            self.log("⚠ Already downloading...")
            return

        self._cancel_flag = False
        self._playlist_mode = playlist
        thread = threading.Thread(target=self._download_thread, args=(url,), daemon=True)
        thread.start()

    def _download_thread(self, url):
        """Основная логика скачивания"""
        self._is_running = True
        self.progress(0.0)

        if not os.path.exists(FFMPEG_PATH):
            self.log(f"❌ ffmpeg.exe not found at: {FFMPEG_PATH}")
            self.done(False)
            self._is_running = False
            return

        ensure_downloads_folder()

        output_template = os.path.join(DOWNLOADS_PATH, "%(title)s.%(ext)s")

        opts = {
            **YTDLP_OPTIONS,
            'outtmpl': output_template,
            'progress_hooks': [self._progress_hook],
            'postprocessors': POSTPROCESSORS,
        }

        # В режиме плейлиста разрешаем скачать все треки сета
        if getattr(self, '_playlist_mode', False):
            opts.pop('no_playlist', None)
            opts['yes_playlist'] = True
            self.log("📋 Playlist mode: downloading all tracks in set")
        else:
            opts['no_playlist'] = True

        self.log(f"🔗 URL: {url}")
        self.log("🔍 Fetching track info...")

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                playlist_mode = getattr(self, '_playlist_mode', False)

                if playlist_mode and info.get('_type') == 'playlist':
                    entries = info.get('entries') or []
                    count = len(list(entries))
                    title = info.get('title', 'Unknown playlist')
                    self.log(f"📋 Playlist: {title}")
                    self.log(f"🎵 Tracks: {count}")
                else:
                    title = info.get('title', 'Unknown')
                    artist = info.get('uploader', 'Unknown')
                    duration = info.get('duration', 0)
                    minutes = int(duration // 60)
                    seconds = int(duration % 60)
                    self.log(f"🎵 {artist} — {title}")
                    self.log(f"⏱ Duration: {minutes}:{seconds:02d}")

                self.log("⬇ Starting download...")
                ydl.download([url])

            self.log("✅ Done!")
            self.log(f"📁 Saved to: {DOWNLOADS_PATH}")
            self.progress(1.0)
            self.done(True)

        except yt_dlp.utils.DownloadCancelled:
            self.log("⚠ Download cancelled")
            self.progress(0.0)
            self.done(False)

        except yt_dlp.utils.DownloadError as e:
            self.log(f"❌ Download error: {e}")
            self.progress(0.0)
            self.done(False)

        except Exception as e:
            self.log(f"❌ Error: {e}")
            self.progress(0.0)
            self.done(False)

        finally:
            self._is_running = False
            self._cancel_flag = False
