import asyncio
from telegram import Update
from telegram.ext import Application
from telegram.request import HTTPXRequest
from telegram_handlers import setup_handlers, request_queue, process_queue
from utils import clean_cache
from downloader import shutdown
from logger import BotLogger
from config import TOKEN, NUM_QUEUE_WORKERS

logger = BotLogger(__name__)
stop_event = asyncio.Event()

async def shutdown_bot(app):
    logger.info("Остановка бота")
    stop_event.set()
    for worker in app.bot_data.get('queue_workers', []):
        if not worker.done():
            worker.cancel()
    if 'cache_stop_event' in app.bot_data:
        app.bot_data['cache_stop_event'].set()
    while not request_queue.empty():
        await request_queue.get()
        request_queue.task_done()
    tasks = [t for t in asyncio.all_tasks() if not t.done()]
    if tasks:
        for task in tasks:
            task.cancel()
        await asyncio.wait(tasks, timeout=5)
    if app.updater and app.updater.running:
        await app.updater.stop()
    await app.stop()
    await app.shutdown()
    await shutdown()
    logger.info("Бот полностью остановлен")

async def main_async(app):
    logger.info("Запуск бота")
    setup_handlers(app)
    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Бот запущен")
    asyncio.create_task(clean_cache(app))
    await stop_event.wait()
    await shutdown_bot(app)

async def main():
    request = HTTPXRequest(connect_timeout=30, read_timeout=300, write_timeout=600)  # Увеличен write_timeout
    app = Application.builder().token(TOKEN).request(request).build()
    try:
        await main_async(app)
    except Exception as e:
        logger.error(f"Ошибка: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())