import os
import re
import sys
from collections import UserDict


def get_base_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_resource_path(filename):
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
        path = os.path.join(base, filename)
        if os.path.exists(path):
            return path
    return os.path.join(get_base_path(), filename)


# ============================================
# ПУТИ
# ============================================
BASE_PATH = get_base_path()
DOWNLOADS_PATH = os.path.join(BASE_PATH, "Downloads")
ARTISTS_FILE = os.path.join(BASE_PATH, "artists.txt")
ARCHIVE_FILE = os.path.join(BASE_PATH, "downloaded.txt")
OAUTH_FILE = os.path.join(BASE_PATH, "oauth.txt")

FFMPEG_PATH = get_resource_path("ffmpeg.exe")
ARIA2_PATH = get_resource_path("aria2c.exe")

# Файл для сохранения геометрии окна между запусками
GEOMETRY_FILE = os.path.join(BASE_PATH, "window.json")


# ============================================
# НАСТРОЙКИ МОНИТОРА (явное хранилище, без monkey-patching)
# ============================================
_monitor_settings = {
    "days_back": 7,
    "max_tracks": 15,
}


def get_monitor_settings():
    return dict(_monitor_settings)


def set_monitor_settings(days_back=None, max_tracks=None):
    if days_back is not None:
        _monitor_settings["days_back"] = int(days_back)
    if max_tracks is not None:
        _monitor_settings["max_tracks"] = int(max_tracks)


# ============================================
# OAUTH ТОКЕН (читается из файла)
# ============================================
def load_oauth_token():
    """Загружает токен из oauth.txt"""
    if not os.path.exists(OAUTH_FILE):
        return ""
    try:
        with open(OAUTH_FILE, 'r', encoding='utf-8') as f:
            token = f.read().strip()
        return token
    except Exception:
        return ""


def save_oauth_token(token):
    """Сохраняет токен в oauth.txt и сбрасывает кэш опций"""
    try:
        with open(OAUTH_FILE, 'w', encoding='utf-8') as f:
            f.write(token.strip())
        # Сбросить кэш чтобы новый токен подхватился при следующем скачивании
        _invalidate_options_cache()
        return True
    except Exception:
        return False


def _invalidate_options_cache():
    """Инвалидирует кэш YTDLP_OPTIONS если он уже создан"""
    obj = globals().get('YTDLP_OPTIONS')
    if obj is not None and hasattr(obj, 'invalidate'):
        obj.invalidate()


def is_valid_token(token):
    """Проверка что токен похож на настоящий (формат: 2-XXXXXX-XXXXXXXXX-XXXXXXXXXXXXXXXX)"""
    if not token:
        return False
    token = token.strip()
    if len(token) < 10:
        return False
    if "ВСТАВЬ" in token.upper() or "YOUR" in token.upper() or "TOKEN" in token.upper():
        return False
    # SoundCloud OAuth token format
    if re.match(r'^\d+-\d+-\d+-\w+$', token):
        return True
    # Fallback: длинная строка без пробелов тоже принимаем
    if len(token) >= 20 and ' ' not in token:
        return True
    return False


# ============================================
# БАЗОВЫЕ ОПЦИИ YT-DLP
# ============================================
def get_ytdlp_options():
    """Возвращает актуальные опции yt-dlp с учётом текущего токена"""
    options = {
        'format': 'http_mp3_128/http_aac/hls_mp3_128/hls_aac/bestaudio/best',
        'extractaudio': True,
        'audioformat': 'mp3',
        'audioquality': 0,
        'embed_thumbnail': True,
        'add_metadata': True,
        'no_playlist': True,
        'socket_timeout': 30,
        'retries': 10,
        'fragment_retries': 30,
        'quiet': True,
        'no_warnings': True,
        'windows_filenames': True,
        'ffmpeg_location': FFMPEG_PATH,

        # Антитроттлинг
        'concurrent_fragment_downloads': 8,
        'http_chunk_size': 10485760,
        'buffersize': 1024 * 32,

        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Origin': 'https://soundcloud.com',
            'Referer': 'https://soundcloud.com/',
        },

        'extractor_args': {
            'soundcloud': {
                'formats': ['hls_aac', 'http_aac', 'hls_mp3', 'http_mp3', 'hls_opus'],
            }
        },
    }

    # Добавить OAuth если есть
    token = load_oauth_token()
    if is_valid_token(token):
        options['http_headers']['Authorization'] = f'OAuth {token}'

    # Добавить aria2c если есть
    if os.path.exists(ARIA2_PATH):
        options['external_downloader'] = 'aria2c'
        options['external_downloader_args'] = {
            'aria2c': [
                '--max-connection-per-server=16',
                '--split=16',
                '--min-split-size=1M',
                '--max-tries=10',
                '--retry-wait=2',
                '--continue=true',
                '--summary-interval=0',
                '--console-log-level=warn',
                '--allow-overwrite=true',
            ],
        }

    return options


# Для обратной совместимости — динамические свойства
class _LazyOptions(UserDict):
    """
    Ленивый словарь опций yt-dlp на базе UserDict.
    Пересчитывается только при явном вызове invalidate().
    UserDict гарантирует полный dict-интерфейс (pop, update,
    setdefault, __len__, **unpack и т.д.) — все они проходят
    через self.data, которое обновляется в _ensure_fresh().
    """
    def __init__(self, getter):
        # Не вызываем super().__init__() чтобы не трогать self.data раньше времени
        self.data = {}
        self._getter = getter
        self._dirty = True  # первый доступ всегда загружает

    def _ensure_fresh(self):
        if self._dirty:
            self.data = self._getter()
            self._dirty = False

    def invalidate(self):
        """Пометить кэш устаревшим (вызывать после изменения токена)"""
        self._dirty = True

    # Перехватываем все точки входа UserDict
    def __getitem__(self, key):
        self._ensure_fresh()
        return self.data[key]

    def __iter__(self):
        self._ensure_fresh()
        return iter(self.data)

    def __len__(self):
        self._ensure_fresh()
        return len(self.data)

    def __contains__(self, key):
        self._ensure_fresh()
        return key in self.data

    def copy(self):
        self._ensure_fresh()
        return dict(self.data)


YTDLP_OPTIONS = _LazyOptions(get_ytdlp_options)

# ============================================
# ПОСТПРОЦЕССОРЫ (общие для downloader и monitor)
# ============================================
POSTPROCESSORS = [
    {
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '0',
    },
    {
        'key': 'FFmpegMetadata',
        'add_metadata': True,
    },
    {
        'key': 'EmbedThumbnail',
    },
]


# ============================================
# НАСТРОЙКИ МОНИТОРА (совместимость с импортами)
# ============================================
MONITOR_MAX_TRACKS = 15
MONITOR_DATE_AFTER = "today-7days"