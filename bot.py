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

# --- 1. Загрузка настроек ---
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(uid.strip()) for uid in os.getenv("ADMIN_IDS", "").split(",") if uid.strip()]
CHANNEL_ID = os.getenv("CHANNEL_ID")
DOWNLOAD_FOLDER = os.getenv("DOWNLOAD_FOLDER", "downloads")
DOWNLOAD_TIMEOUT = int(os.getenv("DOWNLOAD_TIMEOUT", 900))

# Функция для красивого вывода логов с временем
def log(message: str):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{current_time}] {message}")

# --- 2. Настройка Instaloader ---
L = instaloader.Instaloader(
    download_pictures=False,
    download_videos=False,
    download_video_thumbnails=False,
    download_geotags=False,
    download_comments=False,
    save_metadata=False,
    compress_json=False
)

# Маскируем бота под обычный десктопный браузер
L.context._session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
})

# Загружаем "золотую" сессию из браузера
INSTA_SESSIONID = os.getenv("INSTA_SESSIONID")
if INSTA_SESSIONID:
    L.context._session.cookies.set("sessionid", INSTA_SESSIONID, domain=".instagram.com")
    log("✅ Успешно внедрена доверенная браузерная сессия Instagram (sessionid)")
else:
    log("⚠️ Переменная INSTA_SESSIONID не найдена в .env!")

# --- 3. Инициализация бота ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class IsAdmin(Filter):
    async def __call__(self, message: types.Message) -> bool:
        return message.from_user.id in ADMIN_IDS

# --- 4. Обработчики команд ---
@dp.message(CommandStart(), IsAdmin())
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я готов к работе. Отправь мне ссылку на пост в Instagram.\n\n"
        "**Доступные команды:**\n"
        "`/queue` — Посмотреть количество ссылок в очереди\n"
        "`/error` — Посмотреть список файлов с ошибками\n"
        "`/error_reboot файл.txt` — Перезапустить ссылки из файла ошибок",
        parse_mode="Markdown"
    )

@dp.message(Command("queue"), IsAdmin())
async def cmd_queue(message: types.Message):
    try:
        with open("links.txt", "r", encoding="utf-8") as file:
            lines = [line for line in file if line.strip()]
        count = len(lines)
        await message.answer(f"📊 В очереди на публикацию: **{count}** ссылок.", parse_mode="Markdown")
    except FileNotFoundError:
        await message.answer("📊 Очередь пуста (файл links.txt пока не создан).")

@dp.message(Command("error"), IsAdmin())
async def cmd_error(message: types.Message):
    txt_files = [f for f in os.listdir(".") if f.endswith(".txt") and f != "links.txt"]
    
    if not txt_files:
        await message.answer("✅ Файлов с ошибками не найдено. Всё работает отлично!")
        return

    response = "⚠️ **Файлы с ошибками:**\n\n"
    for file in txt_files:
        try:
            with open(file, "r", encoding="utf-8") as f:
                count = len([line for line in f if line.strip()])
            response += f"📄 `{file}` — ссылок: {count}\n"
        except Exception:
            response += f"📄 `{file}` — ошибка чтения\n"
            
    response += "\nДля перезапуска используйте:\n`/error_reboot ИМЯ_ФАЙЛА.txt`"
    await message.answer(response, parse_mode="Markdown")

@dp.message(Command("error_reboot"), IsAdmin())
async def cmd_error_reboot(message: types.Message):
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer("❌ Вы не указали имя файла. Пример:\n`/error_reboot InvalidLinkFormat.txt`", parse_mode="Markdown")
        return
        
    filename = args[1].strip()
    
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
            
        with open("links.txt", "a", encoding="utf-8") as f:
            for link in error_links:
                f.write(link if link.endswith("\n") else link + "\n")
                
        os.remove(filename)
        
        await message.answer(f"✅ Успешно! **{len(error_links)}** ссылок из `{filename}` возвращены в конец очереди на публикацию.", parse_mode="Markdown")
        log(f"♻️ Ссылки из {filename} ({len(error_links)} шт.) возвращены в очередь администратором.")
        
    except Exception as e:
        await message.answer(f"❌ Ошибка при обработке файла: {e}")
        log(f"❌ Ошибка при выполнении error_reboot: {e}")

# --- 5. Обработчик ссылок ---
@dp.message(F.text.contains("instagram.com"), IsAdmin())
async def handle_instagram_link(message: types.Message):
    link = message.text.strip()
    try:
        with open("links.txt", "a", encoding="utf-8") as file:
            file.write(link + "\n")
        await message.answer("✅ Ссылка успешно добавлена в очередь!")
        log(f"📥 Добавлена ссылка: {link}")
    except Exception as e:
        await message.answer(f"❌ Ошибка при записи файла: {e}")
        log(f"❌ Ошибка записи в links.txt: {e}")

@dp.message(F.text, IsAdmin())
async def handle_other_messages(message: types.Message):
    await message.answer("Это не похоже на ссылку Instagram или неизвестная команда. Пожалуйста, отправьте корректную ссылку.")

# --- Функция уведомления об ошибках ---
async def notify_and_save_error(link: str, error_name: str, error_desc: str):
    error_file = f"{error_name}.txt"
    log(f"⚠️ Сохраняем проблемную ссылку в {error_file}")
    
    try:
        with open(error_file, "a", encoding="utf-8") as f:
            f.write(link + "\n")
    except Exception as e:
        log(f"❌ Не удалось записать в {error_file}: {e}")
        
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=f"❌ **Не удалось скачать публикацию!**\n\n"
                     f"🔗 **Ссылка:** {link}\n"
                     f"⚠️ **Ошибка:** {error_name}\n"
                     f"📝 **Детали:** {error_desc}",
                parse_mode="Markdown"
            )
        except Exception:
            pass

# --- 6. Логика скачивания (ТИХИЙ РЕЖИМ) ---
async def download_and_publish(link: str):
    log(f"🔄 Начинаю обработку ссылки: {link}")
    
    match = re.search(r"(?:p|reel|reels|tv)/([^/?#&]+)", link)
    if not match:
        log(f"❌ Не удалось извлечь shortcode из ссылки: {link}")
        await notify_and_save_error(link, "InvalidLinkFormat", "Не удалось распознать ID поста в ссылке")
        return
    
    shortcode = match.group(1)
    post_folder = os.path.join(DOWNLOAD_FOLDER, shortcode)
    
    try:
        def fetch_post():
            return instaloader.Post.from_shortcode(L.context, shortcode)
            
        post = await asyncio.to_thread(fetch_post)
        os.makedirs(post_folder, exist_ok=True)
        
        def download_manual():
            files = []
            if post.typename == 'GraphSidecar':
                for i, node in enumerate(post.get_sidecar_nodes()):
                    url = node.video_url if node.is_video else node.display_url
                    ext = ".mp4" if node.is_video else ".jpg"
                    file_path = os.path.join(post_folder, f"{shortcode}_{i}{ext}")
                    urllib.request.urlretrieve(url, file_path)
                    files.append({"type": "video" if node.is_video else "photo", "path": file_path})
            else:
                url = post.video_url if post.is_video else post.url
                ext = ".mp4" if post.is_video else ".jpg"
                file_path = os.path.join(post_folder, f"{shortcode}_0{ext}")
                urllib.request.urlretrieve(url, file_path)
                files.append({"type": "video" if post.is_video else "photo", "path": file_path})
            return files

        media_files = await asyncio.to_thread(download_manual)
        
        if not media_files:
            log("❌ Медиафайлы не найдены.")
            await notify_and_save_error(link, "NoMediaFound", "Пост скачался, но файлы не обнаружены")
            return

        for media in media_files:
            media_file = FSInputFile(media["path"])
            if media["type"] == "photo":
                await bot.send_photo(chat_id=CHANNEL_ID, photo=media_file)
            elif media["type"] == "video":
                await bot.send_video(chat_id=CHANNEL_ID, video=media_file)
            await asyncio.sleep(2)

        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=f"✅ Пост успешно опубликован в канал!\nИсходная ссылка: {link}"
                )
            except Exception:
                pass
                
        log(f"✅ Пост {shortcode} успешно опубликован.")

    except Exception as e:
        error_name = type(e).__name__
        log(f"❌ Ошибка при скачивании поста {shortcode}: {error_name} - {e}")
        await notify_and_save_error(link, error_name, str(e))
        
    finally:
        if 'post_folder' in locals() and os.path.exists(post_folder):
            shutil.rmtree(post_folder)

# --- 7. Фоновая очередь задач ---
async def process_queue():
    while True:
        link_to_process = None
        try:
            with open("links.txt", "r", encoding="utf-8") as file:
                lines = file.readlines()
            
            if lines:
                link_to_process = lines[0].strip()
                with open("links.txt", "w", encoding="utf-8") as file:
                    file.writelines(lines[1:])
        except FileNotFoundError:
            pass
        except Exception as e:
            log(f"❌ Ошибка при чтении очереди (links.txt): {e}")

        if link_to_process:
            await download_and_publish(link_to_process)
            log(f"⏳ Ожидание {DOWNLOAD_TIMEOUT} сек. до следующего скачивания...")
            await asyncio.sleep(DOWNLOAD_TIMEOUT)
        else:
            await asyncio.sleep(5)

# --- 8. Запуск приложения ---
async def main():
    log("🚀 Бот успешно запущен и ждет сообщения...")
    asyncio.create_task(process_queue())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())