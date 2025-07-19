import os
import django
from aiogram import Bot, Dispatcher, executor, types
from asgiref.sync import sync_to_async
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton

# --- Инициализация Django ---
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "legitcheck.settings")
django.setup()

from webapp.models import Verdict

API_TOKEN = "7620197633:AAHqBbPgVEtloxy6we7YyvMU7eWK9-hSyrU"
bot = Bot(token=API_TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot)


# Синхронный доступ к одному Verdict по коду + первая фотография
@sync_to_async
def fetch_verdict_by_code(code):
    try:
        v = Verdict.objects.prefetch_related('photos').get(code__iexact=code)
    except Verdict.DoesNotExist:
        return None, None

    first = v.photos.first()
    photo_path = first.image.path if first else None
    return v, photo_path


@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    """
    Обрабатывает deep link /start=<code>:
    - если code передан, ищет Verdict по нему и присылает данные
    - иначе просит запустить бота со ссылкой
    """
    args = message.get_args().strip()
    if not args:
        await message.reply("❗️ Пожалуйста, запускайте бота по специальной ссылке вида `https://t.me/YourBot?start=<code>`.")
        return

    code = args
    webapp_url = f"https://legitcheck.one/verdict?code={code}"
    button = InlineKeyboardButton(
        text="🔗 Открыть веб-приложение",
        web_app=WebAppInfo(url=webapp_url)
    )
    markup = InlineKeyboardMarkup().add(button)
    v, photo_path = await fetch_verdict_by_code(code)
    if not v:
        await message.reply(f"❌ Вердикт с кодом <b>{code}</b> не найден.")
        return

    caption = (
        f"<b>Код:</b> {v.code}\n"
        f"<b>Категория вещи:</b> {v.get_category_display()}\n"
        f"<b>Бренд:</b> {v.brand}\n"
        f"<b>Модель:</b> {v.item_model}\n"
        f"<b>Статус проверки:</b> {v.get_status_display()}\n"
        f"<b>Дата:</b> {v.created_at:%Y-%m-%d %H:%M}\n"
        f"<b>Комментарий:</b> {v.comment}\n"
        f"<b>Комментарий пользователя:</b> {v.comment_from_user}"
    )

    if photo_path and os.path.exists(photo_path):
        photo = types.InputFile(photo_path)
        await bot.send_photo(
            chat_id=message.chat.id,
            photo=photo,
            caption=caption,
            reply_markup=markup
        )
    else:
        await message.answer(caption)


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
