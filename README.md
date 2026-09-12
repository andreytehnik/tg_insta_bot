# Instagram Downloader Bot For Telegram

Бот для автоматического скачивания постов, Reels и каруселей из Instagram с публикацией в ваш Telegram-канал. Работает в фоне через очередь с настраиваемыми задержками, чтобы Instagram не заблокировал.

## Стек

- **Python 3** + **aiogram 3** — асинхронный фреймворк для Telegram Bot API
- **Instaloader** — парсинг медиа из Instagram
- **Systemd User Service** — фоновый запуск без `sudo`

## Быстрый старт

### 1. Клонируйте репозиторий

```bash
git clone https://github.com/andreytehnik/tg_insta_bot.git
cd tg_insta_bot
```

### 2. Настройте `.env`

Создайте файл `.env` в корне проекта:

```env
BOT_TOKEN=ваш_токен_от_BotFather
CHANNEL_ID=@ваш_телеграм_канал
ADMIN_IDS=ваш_telegram_id
INSTA_SESSIONID=ваш_cookie_sessionid
DOWNLOAD_FOLDER=downloads
DOWNLOAD_TIMEOUT=1800
```

**Откуда взять значения:**

| Переменная | Как получить |
|------------|--------------|
| `BOT_TOKEN` | Создайте бота через [@BotFather](https://t.me/BotFather) |
| `CHANNEL_ID`, `ADMIN_IDS` | Узнайте через [@userinfobot](https://t.me/userinfobot) |
| `INSTA_SESSIONID` | Авторизуйтесь в Instagram в браузере → F12 → Application → Cookies → `sessionid` |
| `DOWNLOAD_FOLDER` | Папка для временных файлов (по умолчанию `downloads`) |
| `DOWNLOAD_TIMEOUT` | Пауза между скачиваниями в секундах (1800 = 30 мин) |

### 3. Запустите

```bash
chmod +x bot-systemd.sh
./bot-systemd.sh
```

Скрипт сам создаст виртуальное окружение, поставит зависимости, настроит systemd-сервис и запустит бота в фоне.

## Управление

```bash
# Статус
systemctl --user status tg_insta_bot.service

# Логи в реальном времени
journalctl --user -u tg_insta_bot.service -f

# Перезапуск
systemctl --user restart tg_insta_bot.service

# Остановка
systemctl --user stop tg_insta_bot.service
```

## Команды бота (для админов из `.env`)

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие и справка |
| `/queue` | Сколько ссылок в очереди |
| `/error` | Список файлов с ошибками |
| `/error_reboot файл.txt` | Вернуть ссылки из файла ошибок обратно в очередь |

## Как это работает

1. Присылаете боту ссылку на Instagram-пост/Reels — она попадает в `links.txt`
2. Фоновый воркер забирает ссылки по одной, скачивает медиа через Instaloader (с вашей сессией)
3. Медиа публикуются в канал, временные файлы удаляются
4. Между скачиваниями — пауза `DOWNLOAD_TIMEOUT` (защита от банов)
5. Если что-то пошло не так — ссылка сохраняется в отдельный `*Exception.txt`, админы получают уведомление

## Важные нюансы

- **Instagram требует авторизацию** — без валидного `INSTA_SESSIONID` ничего не скачается
- **Сессия может протухнуть** — если бот перестал качать, обновите `sessionid` в `.env` и перезапустите
- **Бот не качает сторис и профили** — только посты, Reels и карусели
- **Файлы очереди и ошибок в `.gitignore`** — они создаются в рантайме

## Лицензия

[MIT](LICENSE) — делайте что хотите.