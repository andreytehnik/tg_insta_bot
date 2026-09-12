import asyncio
import os
import re
import shutil
import urllib.request
from pathlib import Path
from datetime import datetime
import instaloader
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Filter, CommandStart, Command
from aiogram.types import FSInputFile
from dotenv import load_dotenv

# Загружаем настройки из .env
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(uid.strip()) for uid in os.getenv("ADMIN_IDS", "").split(",") if uid.strip()]
CHANNEL_ID = os.getenv("CHANNEL_ID")
DOWNLOAD_FOLDER = os.getenv("DOWNLOAD_FOLDER", "downloads")
DOWNLOAD_TIMEOUT = int(os.getenv("DOWNLOAD_TIMEOUT", 900))


def log(message: str):
    """Простой логгер с таймстампом — чтобы видеть, что происходит в консоли."""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{current_time}] {message}")


# Настраиваем Instaloader: качаем только медиа, без лишнего мусора
L = instaloader.Instaloader(
    download_pictures=False,
    download_videos=False,
    download_video_thumbnails=False,
    download_geotags=False,
    download_comments=False,
    save_metadata=False,
    compress_json=False
)

# Притворяемся обычным Chrome на Windows — Instagram режет запросы от скриптов
L.context._session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
})

# Подсовываем Instaloader'у куку sessionid из браузера — это единственный способ
# качать без логина/пароля и избегать чекпоинтов
INSTA_SESSIONID = os.getenv("INSTA_SESSIONID")
if INSTA_SESSIONID:
    L.context._session.cookies.set("sessionid", INSTA_SESSIONID, domain=".instagram.com")
    log("✅ Сессия Instagram (sessionid) успешно загружена")
else:
    log("⚠️ INSTA_SESSIONID не найден в .env — скачивание не сработает!")


# Инициализируем бота и диспетчер
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


class IsAdmin(Filter):
    """Фильтр: пропускаем сообщения только от админов из .env"""
    async def __call__(self, message: types.Message) -> bool:
        return message.from_user.id in ADMIN_IDS


# /start — приветствие и краткая справка
@dp.message(CommandStart(), IsAdmin())
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я готов к работе. Пришли ссылку на пост/Reels в Instagram.\n\n"
        "**Команды:**\n"
        "`/queue` — сколько ссылок в очереди\n"
        "`/error` — список файлов с ошибками\n"
        "`/error_reboot файл.txt` — вернуть ссылки из файла ошибок в очередь",
        parse_mode="Markdown"
    )


# /queue — показать размер очереди
@dp.message(Command("queue"), IsAdmin())
async def cmd_queue(message: types.Message):
    try:
        with open("links.txt", "r", encoding="utf-8") as file:
            lines = [line for line in file if line.strip()]
        count = len(lines)
        await message.answer(f"📊 В очереди: **{count}** ссылок.", parse_mode="Markdown")
    except FileNotFoundError:
        await message.answer("📊 Очередь пуста (файл links.txt ещё не создан).")


# /error — показать список файлов с ошибками и сколько в каждом ссылок
@dp.message(Command("error"), IsAdmin())
async def cmd_error(message: types.Message):
    # Ищем все .txt файлы, кроме links.txt — это файлы ошибок
    txt_files = [f for f in os.listdir(".") if f.endswith(".txt") and f != "links.txt"]

    if not txt_files:
        await message.answer("✅ Файлов с ошибками нет. Всё чисто!")
        return

    response = "⚠️ **Файлы с ошибками:**\n\n"
    for file in txt_files:
        try:
            with open(file, "r", encoding="utf-8") as f:
                count = len([line for line in f if line.strip()])
            response += f"📄 `{file}` — ссылок: {count}\n"
        except Exception:
            response += f"📄 `{file}` — ошибка чтения\n"

    response += "\nЧтобы вернуть в очередь: `/error_reboot ИМЯ_ФАЙЛА.txt`"
    await message.answer(response, parse_mode="Markdown")


# /error_reboot — вернуть ссылки из файла ошибок обратно в очередь
@dp.message(Command("error_reboot"), IsAdmin())
async def cmd_error_reboot(message: types.Message):
    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.answer("❌ Укажи имя файла. Пример:\n`/error_reboot InvalidLinkFormat.txt`", parse_mode="Markdown")
        return

    filename = args[1].strip()

    # Защита от путь-траверсии
    if "/" in filename or "\\" in filename:
        await message.answer("❌ Недопустимое имя файла.")
        return

    if not os.path.exists(filename):
        await message.answer(f"❌ Файл `{filename}` не найден.", parse_mode="Markdown")
        return

    try:
        with open(filename, "r", encoding="utf-8") as f:
            error_links = [line for line in f if line.strip()]

        if not error_links:
            await message.answer(f"⚠️ Файл `{filename}` пуст.")
            os.remove(filename)
            return

        # Дописываем ссылки в конец очереди
        with open("links.txt", "a", encoding="utf-8") as f:
            for link in error_links:
                f.write(link if link.endswith("\n") else link + "\n")

        os.remove(filename)  # файл ошибок больше не нужен

        await message.answer(f"✅ Готово! **{len(error_links)}** ссылок из `{filename}` вернулись в очередь.", parse_mode="Markdown")
        log(f"♻️ Ссылки из {filename} ({len(error_links)} шт.) возвращены в очередь админом.")

    except Exception as e:
        await message.answer(f"❌ Ошибка при обработке: {e}")
        log(f"❌ Ошибка в error_reboot: {e}")


# Ловим ссылки на Instagram в сообщениях админов
@dp.message(F.text.contains("instagram.com"), IsAdmin())
async def handle_instagram_link(message: types.Message):
    link = message.text.strip()
    try:
        with open("links.txt", "a", encoding="utf-8") as file:
            file.write(link + "\n")
        await message.answer("✅ Ссылка добавлена в очередь!")
        log(f"📥 Добавлена ссылка: {link}")
    except Exception as e:
        await message.answer(f"❌ Ошибка записи: {e}")
        log(f"❌ Ошибка записи в links.txt: {e}")


# Всё остальное — просим прислать правильную ссылку
@dp.message(F.text, IsAdmin())
async def handle_other_messages(message: types.Message):
    await message.answer("Это не ссылка на Instagram. Пришли корректную ссылку на пост или Reels.")


async def notify_and_save_error(link: str, error_name: str, error_desc: str):
    """
    Сохраняем проблемную ссылку в отдельный файл (по типу ошибки)
    и шлём уведомление всем админам.
    """
    error_file = f"{error_name}.txt"
    log(f"⚠️ Сохраняем битую ссылку в {error_file}")

    try:
        with open(error_file, "a", encoding="utf-8") as f:
            f.write(link + "\n")
    except Exception as e:
        log(f"❌ Не удалось записать в {error_file}: {e}")

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=(
                    f"❌ **Не удалось скачать публикацию!**\n\n"
                    f"🔗 **Ссылка:** {link}\n"
                    f"⚠️ **Ошибка:** {error_name}\n"
                    f"📝 **Детали:** {error_desc}"
                ),
                parse_mode="Markdown"
            )
        except Exception:
            pass  # админ мог заблокировать бота — игнорируем


async def download_and_publish(link: str):
    """
    Основная логика: достаёт пост по shortcode, качает медиа,
    публикует в канал, чистит временные файлы.
    """
    log(f"🔄 Обрабатываю: {link}")

    # Вытаскиваем shortcode из URL (p/..., reel/..., tv/...)
    match = re.search(r"(?:p|reel|reels|tv)/([^/?#&]+)", link)
    if not match:
        log(f"❌ Не удалось вытащить shortcode из: {link}")
        await notify_and_save_error(link, "InvalidLinkFormat", "Не удалось распознать ID поста в ссылке")
        return

    shortcode = match.group(1)
    post_folder = os.path.join(DOWNLOAD_FOLDER, shortcode)

    try:
        # Получаем метаданные поста в отдельном потоке (Instaloader синхронный)
        def fetch_post():
            return instaloader.Post.from_shortcode(L.context, shortcode)

        post = await asyncio.to_thread(fetch_post)
        os.makedirs(post_folder, exist_ok=True)

        # Качаем медиа вручную через urllib — быстрее и надёжнее, чем встроенные методы
        def download_manual():
            files = []
            if post.typename == 'GraphSidecar':
                # Карусель — несколько фото/видео
                for i, node in enumerate(post.get_sidecar_nodes()):
                    url = node.video_url if node.is_video else node.display_url
                    ext = ".mp4" if node.is_video else ".jpg"
                    file_path = os.path.join(post_folder, f"{shortcode}_{i}{ext}")
                    urllib.request.urlretrieve(url, file_path)
                    files.append({"type": "video" if node.is_video else "photo", "path": file_path})
            else:
                # Одиночный пост или Reels
                url = post.video_url if post.is_video else post.url
                ext = ".mp4" if post.is_video else ".jpg"
                file_path = os.path.join(post_folder, f"{shortcode}_0{ext}")
                urllib.request.urlretrieve(url, file_path)
                files.append({"type": "video" if post.is_video else "photo", "path": file_path})
            return files

        media_files = await asyncio.to_thread(download_manual)

        if not media_files:
            log("❌ Медиафайлы не найдены после скачивания.")
            await notify_and_save_error(link, "NoMediaFound", "Пост скачался, но файлы не обнаружены")
            return

        # Публикуем в канал
        for media in media_files:
            media_file = FSInputFile(media["path"])
            if media["type"] == "photo":
                await bot.send_photo(chat_id=CHANNEL_ID, photo=media_file)
            elif media["type"] == "video":
                await bot.send_video(chat_id=CHANNEL_ID, video=media_file)
            await asyncio.sleep(2)  # небольшая пауза между файлами

        # Уведомляем админов об успехе
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=f"✅ Пост опубликован в канал!\nИсходная ссылка: {link}"
                )
            except Exception:
                pass

        log(f"✅ Пост {shortcode} успешно опубликован.")

    except Exception as e:
        error_name = type(e).__name__
        log(f"❌ Ошибка при скачивании {shortcode}: {error_name} - {e}")
        await notify_and_save_error(link, error_name, str(e))

    finally:
        # Всегда чистим временную папку с медиа
        if 'post_folder' in locals() and os.path.exists(post_folder):
            shutil.rmtree(post_folder)


async def process_queue():
    """
    Фоновый воркер: бесконечно проверяет links.txt,
    забирает первую ссылку, обрабатывает, ждёт таймаут.
    """
    while True:
        link_to_process = None
        try:
            with open("links.txt", "r", encoding="utf-8") as file:
                lines = file.readlines()

            if lines:
                # Забираем первую ссылку и переписываем файл без неё
                link_to_process = lines[0].strip()
                with open("links.txt", "w", encoding="utf-8") as file:
                    file.writelines(lines[1:])
        except FileNotFoundError:
            pass  # файла ещё нет — очередь пуста
        except Exception as e:
            log(f"❌ Ошибка чтения очереди: {e}")

        if link_to_process:
            await download_and_publish(link_to_process)
            log(f"⏳ Пауза {DOWNLOAD_TIMEOUT} сек. перед следующим...")
            await asyncio.sleep(DOWNLOAD_TIMEOUT)
        else:
            await asyncio.sleep(5)  # очередь пуста — спим 5 сек и проверяем снова


async def main():
    log("🚀 Бот запущен и ждёт ссылки...")
    asyncio.create_task(process_queue())  # фоновый воркер очереди
    await dp.start_polling(bot)  # поллинг обновлений от Telegram


if __name__ == "__main__":
    asyncio.run(main())