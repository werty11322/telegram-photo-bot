import os
import logging
import requests
import replicate
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- ИЗМЕНЕНИЕ №1: УБИРАЕМ ПЕРЕМЕННЫЕ ИЗ ГЛОБАЛЬНОЙ ОБЛАСТИ ---

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# "База данных" для хранения фото
user_photo_cache = {}

# Функции-обработчики (остаются такими же)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Отправь мне фото, и я предложу, что с ним можно сделать.")

async def ask_for_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    photo_file_id = update.message.photo[-1].file_id
    user_photo_cache[user_id] = photo_file_id
    keyboard = [
        [
            InlineKeyboardButton("Удалить фон 🗑️", callback_data='remove_bg'),
            InlineKeyboardButton("Улучшить качество ✨", callback_data='enhance_photo'),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Отлично! Что сделать с этим фото?', reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    choice = query.data
    photo_file_id = user_photo_cache.get(user_id)
    if not photo_file_id:
        await query.edit_message_text(text="Кажется, я потерял ваше фото. Пожалуйста, отправьте его снова.")
        return
    if choice == 'remove_bg':
        await query.edit_message_text(text="Принято! Удаляю фон...")
        await remove_background(user_id, photo_file_id, context)
    elif choice == 'enhance_photo':
        await query.edit_message_text(text="Принято! Улучшаю качество (это может занять до 30 секунд)...")
        await enhance_photo(user_id, photo_file_id, context)

async def remove_background(user_id, file_id, context: ContextTypes.DEFAULT_TYPE):
    try:
        # --- ИЗМЕНЕНИЕ №2: ПОЛУЧАЕМ КЛЮЧ ПРЯМО ЗДЕСЬ ---
        api_key = os.environ.get("REMOVEBG_API_KEY")
        photo_file = await context.bot.get_file(file_id)
        file_bytes = await photo_file.download_as_bytearray()
        response = requests.post(
            'https://api.remove.bg/v1.0/removebg',
            files={'image_file': file_bytes}, data={'size': 'auto'}, headers={'X-Api-Key': api_key}
        )
        response.raise_for_status()
        await context.bot.send_document(chat_id=user_id, document=response.content, filename='photo_no_bg.png', caption='Фон удален!')
    except Exception as e:
        logger.error(f"Ошибка при удалении фона: {e}")
        await context.bot.send_message(chat_id=user_id, text=f"Ошибка при удалении фона.")

async def enhance_photo(user_id, file_id, context: ContextTypes.DEFAULT_TYPE):
    try:
        # --- ИЗМЕНЕНИЕ №3: ПЕРЕДАЕМ КЛЮЧ ПРЯМО ЗДЕСЬ ---
        os.environ["REPLICATE_API_TOKEN"] = os.environ.get("REPLICATE_API_KEY")
        photo_file = await context.bot.get_file(file_id)
        output = replicate.run(
            "nightmareai/real-esrgan:42fed1c4974146d4d2414e2be2c52377c472f1072563bb1da35a8a9a5a4523af",
            input={"image": photo_file.file_path}
        )
        await context.bot.send_photo(chat_id=user_id, photo=output, caption='Качество улучшено!')
    except Exception as e:
        logger.error(f"Ошибка при улучшении качества: {e}")
        await context.bot.send_message(chat_id=user_id, text=f"Ошибка при улучшении качества.")

# --- НОВАЯ ЧАСТЬ ДЛЯ РАБОТЫ В ВЕБ-СРЕДЕ ---
# --- ИЗМЕНЕНИЕ №4: ПОЛУЧАЕМ ТОКЕН ВНУТРИ ФУНКЦИИ ---
def setup_application():
    bot_token = os.environ.get("BOT_TOKEN")
    application = Application.builder().token(bot_token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.PHOTO, ask_for_action))
    application.add_handler(CallbackQueryHandler(button_handler))
    return application, bot_token

application, bot_token = setup_application()

server = Flask(__name__)

@server.route(f"/{bot_token}", methods=['POST'])
async def webhook():
    update_data = request.get_json(force=True)
    update = Update.de_json(update_data, application.bot)
    await application.process_update(update)
    return 'ok'
