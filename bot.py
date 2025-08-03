import logging
import os
import asyncio
from idlelib.undo import Command

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import setup_application
from aiohttp import web

API_TOKEN = os.getenv("API_TOKEN")  # токен бота
WEBHOOK_PATH = "/webhook"  # путь для webhook, обязательно с /
BASE_WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL")  # URL твоего сервера без слэша на конце
WEBHOOK_URL = f"{BASE_WEBHOOK_URL}{WEBHOOK_PATH}"

logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Здесь твой словарь topics_cache и остальные обработчики (копируй свои)

topics_cache = {
    'Любимое': 23,
    'Сон': 22,
    'Погрустить': 21,
    'В дороге': 20,
    'Иностранные': 19,
    'Русские': 18,
    'Космо музыка': 14,
    'Поп': 12,
    'Джаз': 10,
    'Рок': 8
}

user_choices = {}
user_audio = {}


def get_keyboard(user_id: int):
    builder = InlineKeyboardBuilder()
    selected = user_choices.get(user_id, set())
    for topic, tid in topics_cache.items():
        is_sel = topic in selected
        builder.button(
            text=f"{'✅' if is_sel else '☐'} {topic}",
            callback_data=f"toggle:{topic}"
        )
    builder.button(text="✅ Готово", callback_data="done")
    builder.adjust(1)
    return builder.as_markup()


@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("Привет! Я бот для сортировки музыки по жанрам и не только!")


@dp.message(F.audio & (F.message_thread_id == None))
async def get_music(message: Message):
    user_id = message.from_user.id
    user_audio[user_id] = {
        'file_id': message.audio.file_id,
        'title': message.audio.title,
        'performer': message.audio.performer
    }
    user_choices[user_id] = set()
    await message.reply(
        "Выберите плейлисты, куда переслать эту музыку:",
        reply_markup=get_keyboard(user_id)
    )


@dp.callback_query(F.data.startswith("toggle:"))
async def toggle_choice(callback: CallbackQuery):
    user_id = callback.from_user.id
    topic = callback.data.split(":", 1)[1]
    selected = user_choices.setdefault(user_id, set())
    if topic in selected:
        selected.remove(topic)
    else:
        selected.add(topic)
    await callback.message.edit_reply_markup(reply_markup=get_keyboard(user_id))
    await callback.answer()


@dp.callback_query(F.data == "done")
async def process_done(callback: CallbackQuery):
    user_id = callback.from_user.id
    selected = user_choices.get(user_id, set())
    audio_info = user_audio.get(user_id)

    if not audio_info:
        await callback.message.edit_text("Ошибка: не удалось найти аудио. Повторите отправку файла.")
        return

    if selected:
        group_id = callback.message.chat.id
        tasks = []
        for topic in selected:
            thread_id = topics_cache[topic]
            tasks.append(bot.send_audio(
                chat_id=group_id,
                message_thread_id=thread_id,
                audio=audio_info['file_id'],
                title=audio_info.get('title'),
                performer=audio_info.get('performer'),
                caption=f"Переслано от {callback.from_user.username or callback.from_user.full_name}"
            ))
        tasks.append(bot.send_audio(
            chat_id=group_id,
            message_thread_id=2,
            audio=audio_info['file_id'],
            title=audio_info.get('title'),
            performer=audio_info.get('performer'),
            caption=f"Переслано от {callback.from_user.username or callback.from_user.full_name}"
        ))
        await asyncio.gather(*tasks, return_exceptions=True)

        await callback.message.edit_text(
            "Добавлено в плейлисты:\n" + "\n".join(selected)
        )
    else:
        await callback.message.edit_text("Вы ничего не выбрали.")

    user_choices.pop(user_id, None)
    user_audio.pop(user_id, None)
    await callback.answer()


async def on_startup(app: web.Application):
    try:
        await bot.set_webhook(WEBHOOK_URL)
        logging.info(f"Webhook установлен: {WEBHOOK_URL}")
    except Exception as e:
        logging.error(f"Ошибка при установке webhook: {e}")


async def on_shutdown(app: web.Application):
    await bot.delete_webhook()


app = web.Application()

app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

# Указываем путь webhook явно
setup_application(app, dp, bot=bot, path=WEBHOOK_PATH)

if __name__ == "__main__":
    web.run_app(app, port=int(os.getenv("PORT", 10000)))
