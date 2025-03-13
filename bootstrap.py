import asyncio
import os
from logger import BotLogger
from config import BASE_DIR, TEMP_FILE_PATTERNS

logger = BotLogger("BOOTSTRAP")

async def cleanup_temp_files():
    logger.debug(f"Начало очистки временных файлов в {BASE_DIR}")
    if not os.path.exists(BASE_DIR):
        logger.warning(f"Директория {BASE_DIR} не существует")
        return
    for root, _, files in os.walk(BASE_DIR):
        for file in files:
            if any(file.startswith(p.lstrip('*')) or file.endswith(p.lstrip('*')) for p in TEMP_FILE_PATTERNS):
                file_path = os.path.join(root, file)
                try:
                    os.remove(file_path)
                    logger.debug(f"Удалён временный файл: {file_path}")
                except Exception as e:
                    logger.error(f"Ошибка удаления {file_path}: {e}", exc_info=True)

async def run_bot():
    await cleanup_temp_files()
    logger.info("Запуск основного модуля")
    from main import main
    await main()

if __name__ == "__main__":
    try:
        logger.debug("Запуск bootstrap.py")
        asyncio.run(run_bot())
    except Exception as e:
        logger.error(f"Ошибка в main.py: {e}", exc_info=True)