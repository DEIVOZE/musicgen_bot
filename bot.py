import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import setup_application
from aiohttp import web
import asyncio
from aiogram import F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

API_TOKEN = os.getenv("API_TOKEN")  # получаем токен из переменной окружения
WEBHOOK_PATH = f"/webhook"  # путь, можно любой
BASE_WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL")  # Render вставит его сам
WEBHOOK_URL = f"{BASE_WEBHOOK_URL}{WEBHOOK_PATH}"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# Топики и их thread_id
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

# храним выбор пользователя и его аудио
user_choices = {}  # user_id -> set(topic_name)
user_audio = {}  # user_id -> {'file_id': ..., 'title': ..., 'performer': ...}


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


@dp.message(F.audio & (F.message_thread_id == None))
async def get_music(message: Message):
    user_id = message.from_user.id
    # сохраняем файл и метаданные
    user_audio[user_id] = {
        'file_id': message.audio.file_id,
        'title': message.audio.title,
        'performer': message.audio.performer
    }
    # сбрасываем предыдущий выбор
    user_choices[user_id] = set()
    # показываем клавиатуру
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
        # на всякий случай
        await callback.message.edit_text("Ошибка: не удалось найти аудио. Повторите отправку файла.")
        return

    if selected:
        # Отправляем аудио во все выбранные топики
        group_id = callback.message.chat.id
        tasks = []
        for topic in selected:
            thread_id = topics_cache[topic]
            # напрямую по file_id, без скачивания
            tasks.append(bot.send_audio(
                chat_id=group_id,
                message_thread_id=thread_id,
                audio=audio_info['file_id'],
                title=audio_info.get('title'),
                performer=audio_info.get('performer'),
                caption=f"Переслано от {callback.from_user.username or callback.from_user.full_name}"
            ))
        # Добавление в плейлист вся музыка
        tasks.append(bot.send_audio(
            chat_id=group_id,
            message_thread_id=2,
            audio=audio_info['file_id'],
            title=audio_info.get('title'),
            performer=audio_info.get('performer'),
            caption=f"Переслано от {callback.from_user.username or callback.from_user.full_name}"
        ))
        # параллельно
        await asyncio.gather(*tasks, return_exceptions=True)

        # Обновляем текст под кнопками
        await callback.message.edit_text(
            "Добавлено в плейлисты:\n" + "\n".join(selected)
        )
    else:
        await callback.message.edit_text("Вы ничего не выбрали.")

    # чистим
    user_choices.pop(user_id, None)
    user_audio.pop(user_id, None)
    await callback.answer()


async def on_startup(app: web.Application):
    await bot.set_webhook(WEBHOOK_URL)


async def on_shutdown(app: web.Application):
    await bot.delete_webhook()


app = web.Application()
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

# подключаем aiogram к серверу aiohttp
setup_application(app, dp, bot=bot)

if __name__ == "__main__":
    web.run_app(app, port=int(os.getenv("PORT", 10000)))
