import logging
import os

def setup_logger(name, level=logging.INFO):
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(level)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        file_handler = logging.FileHandler(os.path.join(os.path.dirname(__file__), "bot.log"))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    return logger

class BotLogger:
    def __init__(self, name, level=logging.DEBUG):
        self.logger = setup_logger(name, level)

    def download_start(self, url, filename):
        self.logger.info(f"Скачиваю файл: {url.split('?')[0]} -> {os.path.basename(filename)}")

    def download_attempt(self, url, attempt):
        self.logger.debug(f"Попытка {attempt} скачать {url}")

    def download_success(self, filename, size):
        self.logger.debug(f"Файл скачан, размер: {size} байт")

    def network_error(self, url, error):
        self.logger.error(f"Ошибка сети: {url.split('?')[0]}: {error}", exc_info=True)

    def ffmpeg_command(self, cmd):
        self.logger.debug(f"Выполняю команду ffmpeg: {' '.join(cmd)}")

    def ffmpeg_error(self, error):
        self.logger.error(f"Ошибка FFmpeg: {error}", exc_info=True)

    def conversion_success(self, filename, size, format_type):
        self.logger.debug(f"Конвертация в {format_type} завершена, размер: {size} байт")

    def info(self, msg):
        self.logger.info(msg)

    def debug(self, msg):
        self.logger.debug(msg)

    def error(self, msg, exc_info=False):
        self.logger.error(msg, exc_info=exc_info)

    def warning(self, msg):
        self.logger.warning(msg)