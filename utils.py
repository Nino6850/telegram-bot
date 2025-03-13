import os
import asyncio
import time
from telegram.ext import Application
from logger import BotLogger
from config import BASE_DIR as CONFIG_BASE_DIR, CACHE_LIFETIME, MAX_CACHE_SIZE, CACHE_CHECK_INTERVAL, TELEGRAM_LIMITS

logger = BotLogger(__name__)
BASE_DIR = CONFIG_BASE_DIR
CACHE_DIR = os.path.join(BASE_DIR, "cache")

async def clean_cache(app: Application):
    app.bot_data.setdefault('cache_stop_event', asyncio.Event())
    logger.info("Очистка кэша запущена")
    
    while not app.bot_data['cache_stop_event'].is_set():
        total_size = 0
        files_to_check = []
        
        # Собираем файлы и считаем общий размер
        for root, _, files in os.walk(CACHE_DIR):
            for file in files:
                file_path = os.path.join(root, file)
                file_size = os.path.getsize(file_path)
                total_size += file_size
                files_to_check.append((file_path, file_size, time.time() - os.path.getmtime(file_path)))
        
        # Удаляем устаревшие файлы
        for file_path, file_size, age in files_to_check:
            if age > CACHE_LIFETIME:
                os.remove(file_path)
                total_size -= file_size
                logger.debug(f"Удалён устаревший файл: {file_path}, возраст: {age:.2f} сек")
        
        # Уменьшаем размер кэша, если превышен лимит
        if total_size > MAX_CACHE_SIZE:
            files_to_check = [(f, s, m) for f, s, a in files_to_check if os.path.exists(f) for m in [os.path.getmtime(f)]]
            files_to_check.sort(key=lambda x: x[2])  # Сортировка по времени изменения
            for file_path, file_size, _ in files_to_check:
                if total_size <= MAX_CACHE_SIZE * 0.8:
                    break
                os.remove(file_path)
                total_size -= file_size
                logger.debug(f"Удалён файл для освобождения места: {file_path}, новый размер: {total_size}")
        
        await asyncio.sleep(CACHE_CHECK_INTERVAL)
    logger.info("Очистка кэша остановлена")