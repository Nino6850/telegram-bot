# 📥 Telegram Media Downloader Bot

Этот бот позволяет скачивать медиа (видео, фото, аудио) с популярных платформ и конвертировать видео в голосовые сообщения. Поддерживаются YouTube, Instagram, TikTok, Pinterest, VK и Twitter.

---

## 🚀 Возможности

- 🔹 Скачивание видео и аудио с **YouTube**.
- 🔹 Скачивание фото и видео с **Instagram** (требуются cookies).
- 🔹 Скачивание видео с **TikTok**.
- 🔹 Скачивание фото и видео с **Pinterest**.
- 🔹 Скачивание видео и фото с **VK** (требуются cookies для закрытого контента).
- 🔹 Скачивание видео с **Twitter**.
- 🔹 Конвертация видео в голосовые сообщения Telegram.
- 🔹 Кэширование файлов для ускорения повторных запросов.
- 🔹 Требование подписки на канал Telegram для доступа.

---

## 📌 Требования

Перед установкой убедитесь, что у вас есть:

- ✅ **Python 3.8+** (проверьте версию командой `python --version`).
- ✅ **Git** для клонирования репозитория (`git --version`).
- ✅ **FFmpeg** для обработки видео и аудио (инструкции ниже).
- ✅ **Telegram API токен** от [@BotFather](https://t.me/BotFather).
- ✅ (Опционально) Файлы **cookies** для авторизации на платформах вроде Instagram или VK.

---

## 🛠 Установка

Следуйте этим шагам, чтобы настроить и запустить бота:

### 📂 1. Клонирование репозитория

Скачайте код с GitHub:

```bash
git clone https://github.com/Nino6850/telegram-bot.git
cd telegram-bot
```

### 📦 2. Установка зависимостей

Создайте виртуальное окружение и установите необходимые зависимости:

```bash
python -m venv venv
source venv/bin/activate  # Для Linux/macOS
venv\Scripts\activate  # Для Windows
pip install -r requirements.txt
```

### 🎞 3. Установка FFmpeg

FFmpeg необходим для обработки видео и аудио. Установите его следующим образом:

- **Linux (Debian/Ubuntu)**:
  ```bash
  sudo apt update && sudo apt install ffmpeg
  ```
- **Windows**:
  1. Скачайте сборку с [официального сайта](https://ffmpeg.org/download.html).
  2. Добавьте путь к `ffmpeg.exe` в переменную окружения `PATH`.
- **macOS**:
  ```bash
  brew install ffmpeg
  ```

### 🔑 4. Настройка переменных окружения

Создайте файл `.env` в корневой папке проекта и добавьте туда ваши данные:

```ini
BOT_TOKEN=your-telegram-bot-token
OWNER_ID=your-telegram-id
```

Если требуется авторизация на платформах, добавьте cookies:

```ini
INSTAGRAM_COOKIES=your-instagram-cookies
VK_COOKIES=your-vk-cookies
```

### ▶️ 5. Запуск бота

После настройки запустите бота командой:

```bash
python bootstrap.py
```

---

## 👨‍💻 Разработка и вклад

Хотите помочь в развитии проекта? Сделайте форк репозитория, внесите изменения и отправьте **Pull Request**! Любые предложения и улучшения приветствуются.

---

## 📜 Лицензия

Этот проект распространяется под **MIT License**.
