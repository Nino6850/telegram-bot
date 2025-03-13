import os
import subprocess
import yt_dlp
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from utils import CACHE_DIR, TELEGRAM_LIMITS
from logger import BotLogger
from config import BASE_DIR as CONFIG_BASE_DIR, FFMPEG_AUDIO_BITRATE, FFMPEG_VOICE_BITRATE, DEFAULT_HEADERS, DEFAULT_COOKIES

logger = BotLogger(__name__)

VIDEO_CACHE_DIR = os.path.join(CACHE_DIR, "videos")
PHOTO_CACHE_DIR = os.path.join(CACHE_DIR, "photos")
AUDIO_CACHE_DIR = os.path.join(CACHE_DIR, "audio")
VOICE_CACHE_DIR = os.path.join(CACHE_DIR, "voice")

for dir_path in (VIDEO_CACHE_DIR, PHOTO_CACHE_DIR, AUDIO_CACHE_DIR, VOICE_CACHE_DIR):
    os.makedirs(dir_path, exist_ok=True)
    logger.debug(f"Создана директория кэша: {dir_path}")

SESSION = aiohttp.ClientSession(headers=DEFAULT_HEADERS, cookies=DEFAULT_COOKIES)

YDL_BASE_OPTS = {
    'merge_output_format': 'mp4',
    'quiet': True,
    'no_warnings': True,
    'format': 'bestvideo+bestaudio/best',
    'noplaylist': True,
    'http_headers': DEFAULT_HEADERS,
}

def get_cookie_file(url):
    platforms = {
        'tiktok.com': ("tiktok_cookies.txt", "TikTok"),
        'instagram.com': ("instagram_cookies.txt", "Instagram"),
        'twitter.com': ("twitter_cookies.txt", "Twitter"),
        'x.com': ("twitter_cookies.txt", "Twitter"),
        'vk.com': ("vk_cookies.txt", "VK"),
    }
    for domain, (file, name) in platforms.items():
        if domain in url:
            return os.path.join(CONFIG_BASE_DIR, file), name
    return None, None

async def download_file(url, filename, retries=3):
    logger.download_start(url, filename)
    for attempt in range(1, retries + 1):
        logger.download_attempt(url, attempt)
        try:
            async with SESSION.get(url) as response:
                response.raise_for_status()
                with open(filename, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)
                size = os.path.getsize(filename)
                logger.download_success(filename, size)
                return size > 0
        except aiohttp.ClientError as e:
            logger.network_error(url, e)
            if attempt < retries:
                await asyncio.sleep(2)
    return False

async def run_ffmpeg(cmd, error_msg="Ошибка FFmpeg"):
    logger.ffmpeg_command(cmd)
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.ffmpeg_error(e.stderr)
        raise Exception(error_msg)

async def get_pinterest_media(url):
    logger.download_start(url, "Pinterest media")
    if 'pin.it' in url:
        async with SESSION.get(url, allow_redirects=True) as response:
            url = str(response.url)
    async with SESSION.get(url) as response:
        soup = BeautifulSoup(await response.text(), 'html.parser')
        video = soup.find('video', {'src': True})
        if video:
            return 'video', [video.get('src')]
        image = soup.find('img', {'src': True, 'alt': True})
        if image:
            return 'photo', [image['src'].replace('236x', 'originals')]
        logger.debug("Медиа не найдено на Pinterest")
        return None, None

async def get_instagram_media(url):
    logger.download_start(url, "Instagram media")
    cookies_path = os.path.join(CONFIG_BASE_DIR, "instagram_cookies.txt")
    if not os.path.exists(cookies_path):
        logger.error("Отсутствует instagram_cookies.txt")
        return None, None
    temp_dir = os.path.join(CONFIG_BASE_DIR, "temp_gallery_dl")
    os.makedirs(temp_dir, exist_ok=True)
    cmd = ["gallery-dl", "--cookies", cookies_path, "-D", temp_dir, "--no-download", "--get-urls", url]
    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        logger.error(f"Ошибка gallery-dl: {stderr.decode()}")
        return None, None
    urls = stdout.decode().strip().splitlines()
    if not urls:
        return None, None
    media_urls = [('photo' if u.split('?')[0].endswith(('.jpg', '.jpeg', '.png')) else 'video', u) for u in urls]
    return media_urls[0][0], [u for _, u in media_urls]

async def get_vk_media(url):
    logger.download_start(url, "VK media")
    ydl_opts = YDL_BASE_OPTS.copy()
    cookie_file, platform = get_cookie_file(url)
    if cookie_file and os.path.exists(cookie_file):
        ydl_opts['cookiefile'] = cookie_file
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'requested_formats' in info:
                urls = [fmt['url'] for fmt in info['requested_formats'] if 'url' in fmt]
                return 'video' if len(urls) > 1 else 'audio', urls
            elif 'formats' in info:
                video = max((f for f in info['formats'] if f.get('vcodec', 'none') != 'none'), key=lambda x: x.get('height', 0), default=None)
                audio = max((f for f in info['formats'] if f.get('acodec', 'none') != 'none'), key=lambda x: x.get('tbr', 0), default=None)
                return 'video' if video else 'audio', [video['url']] if video and not audio else [video['url'], audio['url']] if video and audio else [audio['url']]
            return None, None
    except Exception as e:
        logger.error(f"Ошибка извлечения VK: {e}", exc_info=True)
        return None, None

async def download_video(url, filename, chat_id=None, status_message=None, bot=None):
    main_url = url if isinstance(url, str) else url[0]
    logger.download_start(main_url, filename)
    cookie_file, platform = get_cookie_file(main_url)
    ydl_opts = YDL_BASE_OPTS.copy()
    ydl_opts['outtmpl'] = filename
    if cookie_file and os.path.exists(cookie_file):
        ydl_opts['cookiefile'] = cookie_file

    try:
        if isinstance(url, list) and len(url) == 2:
            temp_video, temp_audio = f"{filename}.video.temp", f"{filename}.audio.temp"
            if not (await download_file(url[0], temp_video) and await download_file(url[1], temp_audio)):
                raise Exception("Не удалось скачать потоки")
            cmd = ["ffmpeg", "-i", temp_video, "-i", temp_audio, "-c:v", "copy", "-c:a", "aac", "-y", filename]
            await run_ffmpeg(cmd, "Ошибка объединения видео и аудио")
            for temp in (temp_video, temp_audio):
                if os.path.exists(temp):
                    os.remove(temp)
        else:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([main_url])

        size = os.path.getsize(filename)
        logger.download_success(filename, size)
        if size > TELEGRAM_LIMITS["video"]:
            os.remove(filename)
            logger.warning(f"Файл превышает лимит Telegram: {size} > {TELEGRAM_LIMITS['video']}")
            return False
        return True
    except Exception as e:
        logger.error(f"Ошибка скачивания: {e}", exc_info=True)
        if chat_id and status_message and bot:
            await bot.edit_message_text(f"Ошибка: проверьте URL или cookies для {platform}", chat_id=chat_id, message_id=status_message.message_id)
        return False

async def convert_to_mp3(video_filename, mp3_filename):
    cmd = ["ffmpeg", "-i", video_filename, "-acodec", "mp3", "-b:a", FFMPEG_AUDIO_BITRATE, "-y", mp3_filename]
    await run_ffmpeg(cmd, "Ошибка конвертации в MP3")
    size = os.path.getsize(mp3_filename)
    logger.conversion_success(mp3_filename, size, "MP3")
    return size > 0 and size <= TELEGRAM_LIMITS["audio"]

async def convert_to_ogg(mp3_filename, ogg_filename):
    cmd = ["ffmpeg", "-i", mp3_filename, "-acodec", "libopus", "-b:a", FFMPEG_VOICE_BITRATE, "-y", ogg_filename]
    await run_ffmpeg(cmd, "Ошибка конвертации в OGG")
    size = os.path.getsize(ogg_filename)
    logger.conversion_success(ogg_filename, size, "OGG")
    return size > 0 and size <= TELEGRAM_LIMITS["voice"]

async def shutdown():
    await SESSION.close()
    logger.debug("Сессия aiohttp закрыта")

if __name__ == "__main__":
    async def test():
        url = "https://vk.com/clip-225794223_456240048?c=1"
        media_type, urls = await get_vk_media(url)
        if media_type == 'video':
            await download_video(urls, "test_video.mp4")
        await shutdown()
    asyncio.run(test())