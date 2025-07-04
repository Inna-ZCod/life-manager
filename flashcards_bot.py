from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
import sqlite3
import random
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import logging

# Настройки логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Загрузка токена из .env
load_dotenv()
bot_token = os.getenv("TELEGRAM_BOT_TOKEN")

# Константы
CARDS_PER_SESSION = 5


# Подключение к базе данных
def get_db():
    conn = sqlite3.connect('task_manager.db')
    conn.row_factory = sqlite3.Row
    return conn


# Получаем блок карточек для серии (с учетом ближайших карточек, если готовых мало)
def get_batch_of_cards(user_id, count=CARDS_PER_SESSION):
    conn = get_db()
    cursor = conn.cursor()
    today = datetime.now().isoformat()

    # Сначала берем карточки, готовые к повторению
    cursor.execute('''
        SELECT * FROM learning_cards
        WHERE next_review <= ?
        ORDER BY next_review ASC, RANDOM()
        LIMIT ?
    ''', (today, count))
    cards = cursor.fetchall()

    # Если готовых карточек меньше, чем нужно, добираем ближайшие
    if len(cards) < count:
        remaining = count - len(cards)
        cursor.execute('''
            SELECT * FROM learning_cards
            WHERE next_review > ?
            ORDER BY next_review ASC
            LIMIT ?
        ''', (today, remaining))
        additional_cards = cursor.fetchall()
        cards.extend(additional_cards)

    conn.close()
    return [dict(card) for card in cards]


# Создаем кнопку "Продолжить"
def get_continue_button():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➡️ Продолжить", callback_data="continue")]
    ])


# Начало работы
async def start(update: Update, context):
    await send_message(update, "Добро пожаловать в ваш мини-курс программирования!")
    await start_new_session(update, context)


# Универсальная функция отправки сообщений
async def send_message(update, text, reply_markup=None):
    if update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=reply_markup)
    elif update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)


# Начинаем новую сессию
async def start_new_session(update: Update, context):
    try:
        user_id = update.effective_user.id
        queue = get_batch_of_cards(user_id)

        if not queue:
            await send_message(update, "На сегодня все карточки пройдены!")
            return

        context.user_data["queue"] = queue
        context.user_data["session_stats"] = {"correct": 0, "total": 0}
        await show_card(update, context)

    except Exception as e:
        logger.error(f"Ошибка в start_new_session: {e}")
        await send_message(
            update,
            "Произошла ошибка при загрузке карточек.",
            reply_markup=get_continue_button()
        )


# Показываем карточку пользователю
async def show_card(update: Update, context):
    try:
        queue = context.user_data.get("queue", [])

        # Если серия закончилась, показываем статистику
        if not queue:
            await finish_session(update, context)
            return

        current_card = queue.pop(0)
        context.user_data["current_card"] = current_card

        options = get_options(current_card['id'])
        random.shuffle(options)
        correct_answer = None
        buttons = []

        for opt in options:
            buttons.append(
                [InlineKeyboardButton(opt['answer_text'], callback_data=f"{current_card['id']},{opt['answer_text']}")])
            if opt['is_correct']:
                correct_answer = opt['answer_text']

        reply_markup = InlineKeyboardMarkup(buttons)
        context.user_data["correct_answer"] = correct_answer

        await send_message(update, f"🧠 {current_card['question']}", reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Ошибка в show_card: {e}")
        await send_message(
            update,
            "Произошла ошибка при показе карточки.",
            reply_markup=get_continue_button()
        )


# Завершение сессии и вывод статистики
async def finish_session(update: Update, context):
    stats = context.user_data.get("session_stats", {"correct": 0, "total": 0})
    percent = stats["correct"] / stats["total"] * 100 if stats["total"] > 0 else 0

    message = f"📊 Серия из {stats['total']} карточек завершена!\n"
    message += f"Правильных ответов: {stats['correct']} ({percent:.1f}%)"

    if percent >= 80:
        message += "\n\n✨ Отличный результат! Так держать!"
    elif percent >= 50:
        message += "\n\n🫶 Хорошо, но есть куда расти!"
    else:
        message += "\n\n💪 Не переживай! Следующая серия будет лучше!"

    await send_message(
        update,
        message,
        reply_markup=get_continue_button()
    )


# Получаем варианты ответов для карточки
def get_options(card_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT answer_text, is_correct FROM card_options WHERE card_id = ?", (card_id,))
    options = cursor.fetchall()
    conn.close()

    if not options:
        return [{"answer_text": "Нет вариантов", "is_correct": False}]

    return [dict(option) for option in options]


# Обработка нажатия на кнопку
async def handle_answer(update: Update, context):
    query = update.callback_query
    await query.answer()

    # Обработка кнопки "Продолжить"
    if query.data == "continue":
        await start_new_session(update, context)
        return

    # Обработка ответа на карточку
    data = query.data.split(',')
    card_id = int(data[0])
    user_answer = data[1]

    correct_answer = context.user_data.get("correct_answer", "")
    is_correct = (user_answer == correct_answer)

    # Сохраняем результат
    save_review(card_id, user_answer, is_correct)

    # Обновляем статистику серии
    stats = context.user_data.get("session_stats", {"correct": 0, "total": 0})
    if is_correct:
        stats["correct"] += 1
    stats["total"] += 1
    context.user_data["session_stats"] = stats

    # Выводим объяснение
    explanation = get_explanation(card_id)
    if is_correct:
        message = f"✅ Отлично! Правильный ответ: {correct_answer}\n\n{explanation}"
    else:
        message = f"❌ Неправильно. Правильный ответ: {correct_answer}\n\n{explanation}"

    await query.edit_message_text(text=message, reply_markup=get_continue_button())

    # Обновляем интервал повторения
    update_card_review_time(card_id, is_correct)


# Обновляем время следующего повторения карточки
def update_card_review_time(card_id, is_correct):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT ease, review_count FROM learning_cards WHERE id = ?", (card_id,))
    card = cursor.fetchone()

    if is_correct:
        new_ease = min(card['ease'] + 0.1, 2.5)
        interval = max(1, int(card['review_count'] * new_ease))
    else:
        new_ease = max(1.3, card['ease'] - 0.2)
        interval = 1

    next_review = datetime.now() + timedelta(days=interval)

    cursor.execute('''
        UPDATE learning_cards 
        SET ease = ?, review_count = review_count + 1, next_review = ?
        WHERE id = ?
    ''', (new_ease, next_review, card_id))
    conn.commit()
    conn.close()


# Функция получения объяснения
def get_explanation(card_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT explanation FROM learning_cards WHERE id = ?", (card_id,))
    result = cursor.fetchone()["explanation"]
    conn.close()
    return result


# Сохраняем результат в историю
def save_review(card_id, user_answer, is_correct):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO card_reviews (card_id, user_answer, is_correct)
        VALUES (?, ?, ?)
    ''', (card_id, user_answer, is_correct))
    conn.commit()
    conn.close()


if __name__ == '__main__':
    application = ApplicationBuilder().token(bot_token).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(handle_answer))
    application.run_polling(drop_pending_updates=True)


