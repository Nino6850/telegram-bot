import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN = "7618256957:AAHp72gVw-oEtQ51XtChKI94dz3Bv3UdsGc"
NUM_QUEUE_WORKERS = 3
TELEGRAM_LIMITS = {
    'video': 50 * 1024 * 1024,
    'photo': 10 * 1024 * 1024,
    'audio': 50 * 1024 * 1024,
    'voice': 50 * 1024 * 1024
}
MAX_FILE_SIZE = 50 * 1024 * 1024
FFMPEG_AUDIO_BITRATE = "192k"
FFMPEG_VOICE_BITRATE = "64k"
LOG_FILE = "bot.log"
TEMP_FILE_PATTERNS = ("*.tmp", "*.part", "*_temp.*", "*.download")
CACHE_LIFETIME = 24 * 60 * 60
MAX_CACHE_SIZE = 1024 * 1024 * 1024
CACHE_CHECK_INTERVAL = 60 * 60

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124',
    'Accept': '*/*',
}
DEFAULT_COOKIES = {'tstc': 'p'}