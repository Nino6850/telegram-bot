import os
import asyncio
import hashlib
import re
import time
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import TelegramError, BadRequest
from downloader import download_video, convert_to_mp3, convert_to_ogg, download_file, get_pinterest_media, get_instagram_media, get_vk_media, VIDEO_CACHE_DIR, PHOTO_CACHE_DIR, AUDIO_CACHE_DIR, VOICE_CACHE_DIR
from utils import BASE_DIR
from logger import BotLogger
from config import NUM_QUEUE_WORKERS, TELEGRAM_LIMITS

logger = BotLogger(__name__)
request_queue = asyncio.Queue()

PLATFORMS = {
    ('youtube.com', 'youtu.be'): "YouTube",
    ('instagram.com',): "Instagram",
    ('tiktok.com',): "TikTok",
    ('pinterest.com', 'pin.it'): "Pinterest",
    ('vk.com',): "VK",
    ('twitter.com', 'x.com'): "Twitter"
}

PLATFORM_HANDLERS = {
    "Pinterest": {"media_func": get_pinterest_media, "supports": ["photo", "video"]},
    "Instagram": {"media_func": get_instagram_media, "supports": ["photo", "video"]},
    "VK": {"media_func": get_vk_media, "supports": ["video", "photo"]},
    "YouTube": {"media_func": None, "supports": ["video"]},
    "TikTok": {"media_func": None, "supports": ["video"]},
    "Twitter": {"media_func": None, "supports": ["video"]}
}

URL_PATTERN = re.compile(r'https?://[^\s]+')
CACHE_DIRS = {'video': VIDEO_CACHE_DIR, 'photo': PHOTO_CACHE_DIR, 'audio': AUDIO_CACHE_DIR, 'voice': VOICE_CACHE_DIR}
MAX_MEDIA_PER_MESSAGE = 10
CHANNEL_ID = "-1002410852307"  # ID канала t.me/isflingreal

def generate_filename(chat_id, media_type, url=None, index=None, cache=False):
    suffix = f"_{index}" if index is not None else ""
    ext = {'video': 'mp4', 'photo': 'jpg', 'audio': 'mp3', 'voice': 'ogg'}[media_type]
    if cache and url:
        url_hash = hashlib.md5(f"{chat_id}_{media_type}_{url}".encode()).hexdigest()
    else:
        url_hash = str(int(time.time()))
    dir_path = CACHE_DIRS[media_type] if cache else BASE_DIR
    filename = os.path.join(dir_path, f"{media_type}_{chat_id}_{url_hash}{suffix}.{ext}")
    logger.debug(f"Сгенерировано имя файла: {filename} (cache={cache})")
    return filename

async def resolve_redirected_url(url):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.head(url, allow_redirects=True) as response:
                final_url = str(response.url)
                logger.debug(f"Перенаправленный URL: {final_url}")
                return final_url
        except Exception as e:
            logger.error(f"Ошибка при получении перенаправленного URL: {e}")
            return url

async def update_status(context, chat_id, message_id, text, reply_markup=None):
    try:
        await context.bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=reply_markup)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            pass
        else:
            logger.error(f"Ошибка обновления статуса: {e}")
    except TelegramError as e:
        logger.error(f"Ошибка обновления статуса: {e}")

async def send_media(context, chat_id, filename, media_type, status_message):
    if not os.path.exists(filename) or os.path.getsize(filename) == 0:
        logger.debug(f"Файл {filename} не существует или пуст")
        return False
    logger.info(f"Отправляю {media_type} из {filename}")
    send_func = {
        'photo': context.bot.send_photo,
        'video': context.bot.send_video,
        'audio': context.bot.send_audio,
        'voice': context.bot.send_voice
    }[media_type]
    try:
        start_time = time.time()
        with open(filename, 'rb') as f:
            logger.debug(f"Начало передачи файла {filename}")
            result = await send_func(chat_id=chat_id, **{media_type: f})
        logger.debug(f"Передача завершена за {time.time() - start_time:.2f} сек")
        await context.bot.delete_message(chat_id=chat_id, message_id=status_message.message_id)
        return True
    except telegram.error.TimedOut as e:
        logger.warning(f"Тайм-аут при отправке {filename}: {e}")
        try:
            messages = await context.bot.get_chat_history(chat_id=chat_id, limit=1)
            if messages and getattr(messages[0], media_type) and os.path.basename(filename) in getattr(messages[0], media_type).file_name:
                logger.info(f"{media_type.capitalize()} {filename} всё же отправлено несмотря на тайм-аут")
                await context.bot.delete_message(chat_id=chat_id, message_id=status_message.message_id)
                return True
        except Exception as check_error:
            logger.error(f"Ошибка проверки отправки: {check_error}")
        return False
    except Exception as e:
        logger.error(f"Ошибка отправки {filename}: {e}", exc_info=True)
        return False

async def send_media_group(context, chat_id, media_files, status_message):
    if not media_files:
        await update_status(context, chat_id, status_message.message_id, "Ошибка: не удалось скачать")
        return
    for i in range(0, len(media_files), MAX_MEDIA_PER_MESSAGE):
        batch = media_files[i:i + MAX_MEDIA_PER_MESSAGE]
        media_group = [InputMediaPhoto(media=open(f, 'rb')) if t == 'photo' else InputMediaVideo(media=open(f, 'rb')) 
                       for t, f in batch if os.path.exists(f)]
        if media_group:
            logger.debug(f"Отправляю группу из {len(media_group)} медиа")
            await context.bot.send_media_group(chat_id=chat_id, media=media_group)
    await context.bot.delete_message(chat_id=chat_id, message_id=status_message.message_id)

async def check_subscription(context, user_id, chat_id):
    try:
        member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except TelegramError as e:
        logger.error(f"Ошибка проверки подписки: {e}")
        return False

async def require_subscription(context, chat_id, message_id):
    keyboard = [[InlineKeyboardButton("Проверить подписку", callback_data=f"check_sub_{chat_id}_{message_id}")]]
    await update_status(context, chat_id, message_id, 
                        "Пожалуйста, подпишись на канал t.me/isflingreal, чтобы пользоваться ботом!", 
                        reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_video_to_voice(update: Update, context: ContextTypes):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    video = update.message.video

    if not await check_subscription(context, user_id, chat_id):
        keyboard = [[InlineKeyboardButton("Проверить подписку", callback_data=f"check_sub_{chat_id}_{update.message.message_id}")]]
        await update.message.reply_text("Пожалуйста, подпишись на канал t.me/isflingreal, чтобы пользоваться ботом!", 
                                        reply_markup=InlineKeyboardMarkup(keyboard))
        return

    status_message = await update.message.reply_text("Конвертирую видео в голосовое сообщение...")
    video_file = await video.get_file()
    video_path = generate_filename(chat_id, "video")
    await video_file.download_to_drive(video_path)
    logger.debug(f"Видео скачано в {video_path}, размер: {os.path.getsize(video_path)} байт")

    if not os.path.exists(video_path) or os.path.getsize(video_path) == 0:
        await update_status(context, chat_id, status_message.message_id, "Ошибка: не удалось скачать видео")
        if os.path.exists(video_path):
            os.remove(video_path)
        return

    audio_path = generate_filename(chat_id, "audio")
    if not await convert_to_mp3(video_path, audio_path):
        await update_status(context, chat_id, status_message.message_id, "Ошибка: не удалось извлечь аудио из видео")
        if os.path.exists(video_path):
            os.remove(video_path)
        if os.path.exists(audio_path):
            os.remove(audio_path)
        return

    voice_path = generate_filename(chat_id, "voice")
    if not await convert_to_ogg(audio_path, voice_path):
        await update_status(context, chat_id, status_message.message_id, "Ошибка: не удалось конвертировать аудио в голосовое")
        for path in (video_path, audio_path, voice_path):
            if os.path.exists(path):
                os.remove(path)
        return

    if await send_media(context, chat_id, voice_path, "voice", status_message):
        for path in (video_path, audio_path, voice_path):
            if os.path.exists(path):
                os.remove(path)
    else:
        await update_status(context, chat_id, status_message.message_id, "Ошибка: не удалось отправить голосовое сообщение")
        for path in (video_path, audio_path, voice_path):
            if os.path.exists(path):
                os.remove(path)

async def process_queue(app):
    app.bot_data.setdefault('url_cache', {})
    while True:
        try:
            update, context, chat_id, url, status_message = await request_queue.get()
            user_id = update.effective_user.id
            if not await check_subscription(context, user_id, chat_id):
                await require_subscription(context, chat_id, status_message.message_id)
                request_queue.task_done()
                continue
            logger.info(f"Обрабатываю запрос для чата {chat_id}: {url.split('?')[0]}")
            platform = next((name for domains, name in PLATFORMS.items() if any(d in url for d in domains)), None)
            if not await process_platform(context, chat_id, url, status_message, platform):
                await update_status(context, chat_id, status_message.message_id, "Внутренняя ошибка, свяжись с @shzored")
            request_queue.task_done()
        except Exception as e:
            logger.error(f"Ошибка обработки: {e}", exc_info=True)
            await update_status(context, chat_id, status_message.message_id, "Внутренняя ошибка, свяжись с @shzored")
            request_queue.task_done()

async def process_platform(context, chat_id, url, status_message, platform):
    handler = PLATFORM_HANDLERS.get(platform)
    if not handler:
        await update_status(context, chat_id, status_message.message_id, "Ошибка: платформа не поддерживается")
        return False
    
    if platform == "Instagram" and "share" in url:
        await update_status(context, chat_id, status_message.message_id, "Преобразую ссылку...")
        resolved_url = await resolve_redirected_url(url)
        if "share" in resolved_url or resolved_url == url:
            await update_status(context, chat_id, status_message.message_id, "Ошибка: не удалось преобразовать ссылку")
            return False
        url = resolved_url
    
    if handler["media_func"]:
        media_type, media_urls = await handler["media_func"](url)
        if not media_urls:
            await update_status(context, chat_id, status_message.message_id, "Ошибка: медиа не найдено")
            return False
        await process_social_media(context, chat_id, url, status_message, media_type, media_urls)
        return True
    return await process_video_platform(context, chat_id, url, status_message)

async def process_social_media(context, chat_id, url, status_message, media_type, media_urls):
    await update_status(context, chat_id, status_message.message_id, "Скачиваю медиа...")
    media_files = []
    url_cache = context.bot_data['url_cache']

    if not media_urls:
        await update_status(context, chat_id, status_message.message_id, "Ошибка: неверная ссылка или медиа не найдено")
        return

    if media_type == 'video' and len(media_urls) == 2 and 'vk.com' in url:
        temp_filename = generate_filename(chat_id, 'video')
        cache_filename = generate_filename(chat_id, 'video', url, cache=True)
        if url in url_cache and os.path.exists(url_cache[url]):
            media_files.append(('video', url_cache[url]))
        elif os.path.exists(cache_filename) and url in url_cache and url_cache[url] == cache_filename:
            media_files.append(('video', cache_filename))
        elif await download_video(media_urls, temp_filename, chat_id, status_message, context.bot):
            os.rename(temp_filename, cache_filename)
            media_files.append(('video', cache_filename))
            url_cache[url] = cache_filename
        else:
            await update_status(context, chat_id, status_message.message_id, "Ошибка: не удалось скачать")
            return
    else:
        for i, media_url in enumerate(media_urls):
            media_type_detected = 'photo' if media_url.split('?')[0].endswith(('.jpg', '.jpeg', '.png')) else 'video'
            temp_filename = generate_filename(chat_id, media_type_detected, index=i)
            cache_filename = generate_filename(chat_id, media_type_detected, media_url, i, cache=True)
            if media_url in url_cache and os.path.exists(url_cache[media_url]):
                media_files.append((media_type_detected, url_cache[media_url]))
                continue
            if os.path.exists(cache_filename) and media_url in url_cache and url_cache[media_url] == cache_filename:
                media_files.append((media_type_detected, cache_filename))
                continue
            if media_type_detected == 'video':
                if await download_video(media_url, temp_filename, chat_id, status_message, context.bot):
                    os.rename(temp_filename, cache_filename)
                    media_files.append((media_type_detected, cache_filename))
                    url_cache[media_url] = cache_filename
            else:
                if await download_file(media_url, temp_filename):
                    os.rename(temp_filename, cache_filename)
                    media_files.append((media_type_detected, cache_filename))
                    url_cache[media_url] = cache_filename
            if os.path.exists(temp_filename):
                os.remove(temp_filename)
    await send_media_group(context, chat_id, media_files, status_message)

async def process_video_platform(context, chat_id, url, status_message):
    context.chat_data.update({
        'original_url': url,
        'video_filename': generate_filename(chat_id, "video"),
        'video_cache_filename': generate_filename(chat_id, "video", url, cache=True),
        'audio_filename': generate_filename(chat_id, "audio"),
        'audio_cache_filename': generate_filename(chat_id, "audio", url, cache=True),
        'voice_filename': generate_filename(chat_id, "voice"),
        'voice_cache_filename': generate_filename(chat_id, "voice", url, cache=True)
    })
    keyboard = [[InlineKeyboardButton("Видео", callback_data=f"video_{chat_id}_{status_message.message_id}"),
                 InlineKeyboardButton("Аудио", callback_data=f"audio_{chat_id}_{status_message.message_id}")]]
    await update_status(context, chat_id, status_message.message_id, "Выбери формат:", reply_markup=InlineKeyboardMarkup(keyboard))
    return True

async def handle_media_request(update: Update, context: ContextTypes):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    text = update.message.text.strip()
    status_message = await update.message.reply_text("Проверяю ссылку...")

    if not await check_subscription(context, user_id, chat_id):
        await require_subscription(context, chat_id, status_message.message_id)
        return

    match = URL_PATTERN.search(text)
    if not match:
        await update_status(context, chat_id, status_message.message_id, "Ошибка: неверная ссылка")
        return
    url = match.group(0)
    if not any(domain in url for domains in PLATFORMS.keys() for domain in domains):
        await update_status(context, chat_id, status_message.message_id, "Ошибка: платформа не поддерживается")
        return
    await update_status(context, chat_id, status_message.message_id, "Обрабатываю запрос...")
    await request_queue.put((update, context, chat_id, url, status_message))

async def handle_media_format(update: Update, context: ContextTypes):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    data = query.data.split('_')
    mode, format_type = data[0], data[1] if len(data) > 3 else None
    message_id = int(data[-1])
    status_message = query.message
    user_data = context.chat_data

    if not await check_subscription(context, user_id, chat_id):
        await require_subscription(context, chat_id, message_id)
        return

    if not user_data.get('original_url'):
        await update_status(context, chat_id, message_id, "Ошибка: нет URL")
        return
    try:
        if mode == "video":
            await update_status(context, chat_id, message_id, "Скачиваю медиа...")
            await handle_video(context, chat_id, user_data, status_message)
        elif mode == "audio":
            if format_type:
                await update_status(context, chat_id, message_id, "Конвертирую медиа...")
                await handle_audio(context, chat_id, user_data, status_message, format_type)
            else:
                await handle_audio(context, chat_id, user_data, status_message)
    except Exception as e:
        logger.error(f"Ошибка формата: {e}", exc_info=True)
        await update_status(context, chat_id, message_id, "Внутренняя ошибка, свяжись с @shzored")
    finally:
        await cleanup_temp_files(user_data)

async def handle_check_subscription(update: Update, context: ContextTypes):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    data = query.data.split('_')
    message_id = int(data[-1])

    if await check_subscription(context, user_id, chat_id):
        await update_status(context, chat_id, message_id, "Теперь можно пользоваться ботом")
    else:
        await update_status(context, chat_id, message_id, 
                           "Ты всё ещё не подписан на t.me/isflingreal. Подпишись и попробуй снова!",
                           reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Проверить подписку", callback_data=f"check_sub_{chat_id}_{message_id}")]]))

async def handle_video(context, chat_id, user_data, status_message):
    url_cache = context.bot_data['url_cache']
    url = user_data['original_url']
    if url in url_cache and os.path.exists(url_cache[url]):
        success = await send_media(context, chat_id, url_cache[url], "video", status_message)
        if success:
            return
    elif await send_media(context, chat_id, user_data['video_cache_filename'], "video", status_message):
        return
    elif await download_video(user_data['original_url'], user_data['video_filename'], chat_id, status_message, context.bot):
        success = await send_media(context, chat_id, user_data['video_filename'], "video", status_message)
        if success:
            os.rename(user_data['video_filename'], user_data['video_cache_filename'])
            url_cache[url] = user_data['video_cache_filename']
            return
    await update_status(context, chat_id, status_message.message_id, "Ошибка: не удалось отправить видео")

async def handle_audio(context, chat_id, user_data, status_message, format_type=None):
    url_cache = context.bot_data['url_cache']
    url = user_data['original_url']
    if not format_type:
        if not os.path.exists(user_data['video_cache_filename']) or os.path.getsize(user_data['video_cache_filename']) == 0:
            await update_status(context, chat_id, status_message.message_id, "Скачиваю медиа...")
            if not await download_video(url, user_data['video_filename'], chat_id, status_message, context.bot):
                await update_status(context, chat_id, status_message.message_id, "Ошибка: не удалось скачать")
                return
            os.rename(user_data['video_filename'], user_data['video_cache_filename'])
            url_cache[url] = user_data['video_cache_filename']
        keyboard = [[InlineKeyboardButton("Как файл", callback_data=f"audio_file_{chat_id}_{status_message.message_id}"),
                     InlineKeyboardButton("Как голосовое", callback_data=f"audio_voice_{chat_id}_{status_message.message_id}")]]
        await update_status(context, chat_id, status_message.message_id, "Выбери формат аудио:", reply_markup=InlineKeyboardMarkup(keyboard))
        return True
    if format_type == "file":
        if not os.path.exists(user_data['audio_cache_filename']) or os.path.getsize(user_data['audio_cache_filename']) == 0:
            if not await convert_to_mp3(user_data['video_cache_filename'], user_data['audio_filename']):
                await update_status(context, chat_id, status_message.message_id, "Ошибка: не удалось конвертировать")
                return
            os.rename(user_data['audio_filename'], user_data['audio_cache_filename'])
        await send_media(context, chat_id, user_data['audio_cache_filename'], "audio", status_message)
    elif format_type == "voice":
        if not os.path.exists(user_data['voice_cache_filename']) or os.path.getsize(user_data['voice_cache_filename']) == 0:
            if not os.path.exists(user_data['audio_cache_filename']) or os.path.getsize(user_data['audio_cache_filename']) == 0:
                if not await convert_to_mp3(user_data['video_cache_filename'], user_data['audio_filename']):
                    await update_status(context, chat_id, status_message.message_id, "Ошибка: не удалось конвертировать")
                    return
                os.rename(user_data['audio_filename'], user_data['audio_cache_filename'])
            if not await convert_to_ogg(user_data['audio_cache_filename'], user_data['voice_filename']):
                await update_status(context, chat_id, status_message.message_id, "Ошибка: не удалось конвертировать")
                return
            os.rename(user_data['voice_filename'], user_data['voice_cache_filename'])
        await send_media(context, chat_id, user_data['voice_cache_filename'], "voice", status_message)

async def cleanup_temp_files(user_data):
    for key in ('video_filename', 'audio_filename', 'voice_filename'):
        file = user_data.get(key)
        cache_file = user_data.get(f"{key.split('_')[0]}_cache_filename")
        if file and os.path.exists(file) and file != cache_file:
            logger.debug(f"Удаляю временный файл: {file}")
            os.remove(file)

def setup_handlers(app):
    app.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text(
        "Привет! Я умею скачивать медиа. Вот что пока что я умею:\n"
        "- Видео и аудио с YouTube\n"
        "- Фото и видео с Instagram\n"
        "- Видео с TikTok\n"
        "- Фото и видео с Pinterest\n"
        "- Видео и фото с VK\n"
        "- Видео с Twitter\n"
        "- Конвертация видео в голосовое сообщение\n"
        "Чтобы начать, просто пришли мне ссылку или видео!"
    )))
    app.add_handler(CommandHandler("get_chat_id", lambda u, c: u.message.reply_text(f"Chat ID: {u.effective_chat.id}")))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_media_request))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video_to_voice))
    app.add_handler(CallbackQueryHandler(handle_media_format, pattern=r'(video|audio)_\d+_\d+'))
    app.add_handler(CallbackQueryHandler(handle_media_format, pattern=r'audio_(file|voice)_\d+_\d+'))
    app.add_handler(CallbackQueryHandler(handle_check_subscription, pattern=r'check_sub_\d+_\d+'))
    app.bot_data['queue_workers'] = [asyncio.create_task(process_queue(app)) for _ in range(NUM_QUEUE_WORKERS)]
    logger.info("Обработчики настроены")