from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
import sqlite3
import random
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import logging

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка токена из .env
load_dotenv()
bot_token = os.getenv("TELEGRAM_BOT_TOKEN")

# Количество карточек в одной серии
CARDS_PER_SESSION = 5


# Подключение к базе данных
def get_db():
    conn = sqlite3.connect('task_manager.db')
    conn.row_factory = sqlite3.Row
    return conn


# Получение набора карточек для сессии
def get_batch_of_cards(user_id, count=CARDS_PER_SESSION):
    conn = get_db()
    cursor = conn.cursor()
    today = datetime.now().isoformat()

    # Берём карточки, готовые к просмотру
    cursor.execute('''
        SELECT * FROM learning_cards
        WHERE next_review <= ?
        ORDER BY next_review ASC, RANDOM()
        LIMIT ?
    ''', (today, count))
    ready_cards = cursor.fetchall()

    # Если готовых карточек недостаточно, добавляем ближайшие карточки
    if len(ready_cards) < count:
        remaining = count - len(ready_cards)
        cursor.execute('''
            SELECT * FROM learning_cards
            WHERE next_review > ?
            ORDER BY next_review ASC
            LIMIT ?
        ''', (today, remaining))
        near_future_cards = cursor.fetchall()
        ready_cards.extend(near_future_cards)

    conn.close()
    return [dict(card) for card in ready_cards]


# Получение ближайших карточек вне зависимости от срока повторения
def get_nearby_cards(user_id, count=CARDS_PER_SESSION):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM learning_cards
        ORDER BY next_review ASC
        LIMIT ?
    ''', (count,))
    nearby_cards = cursor.fetchall()
    conn.close()
    return [dict(card) for card in nearby_cards]


# Создание кнопки "Продолжить"
def get_continue_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("➡️ Продолжить", callback_data="continue")]])


# Отправка сообщения пользователю
async def send_message(update, text, reply_markup=None):
    if update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=reply_markup)
    elif update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)


# Начало работы бота
async def start(update: Update, context):
    await send_message(update, "Добро пожаловать в вашу тренировочную сессию!")
    await start_new_session(update, context)


# Запуск новой сессии карточек
async def start_new_session(update: Update, context):
    try:
        user_id = update.effective_user.id
        queue = get_batch_of_cards(user_id)

        # Если нет готовых карточек на сегодня, используем ближайший доступные
        if not queue:
            queue = get_nearby_cards(user_id)
            if not queue:
                await send_message(update, "Все карточки временно исчерпаны. Попробуйте позже.")
                return

        context.user_data["queue"] = queue
        context.user_data["session_stats"] = {"correct": 0, "total": 0}
        await show_next_card_in_series(update, context)

    except Exception as e:
        logger.error(f"Ошибка в start_new_session: {e}")
        await send_message(update, "Произошла ошибка при загрузке карточек.")


# Отображает очередную карточку в текущей серии
async def show_next_card_in_series(update: Update, context):
    try:
        queue = context.user_data.get("queue", [])

        if not queue:
            await finish_current_series(update, context)
            return

        current_card = queue.pop(0)
        context.user_data["current_card"] = current_card

        options = get_options(current_card['id'])
        random.shuffle(options)
        correct_answer = None
        buttons = []

        for opt in options:
            buttons.append([InlineKeyboardButton(opt['answer_text'],
                                                 callback_data=f"{current_card['id']},{opt['answer_text']}"), ])
            if opt['is_correct']:
                correct_answer = opt['answer_text']

        reply_markup = InlineKeyboardMarkup(buttons)
        context.user_data["correct_answer"] = correct_answer

        await send_message(update, f"🔍 Вопрос: {current_card['question']}", reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Ошибка в show_next_card_in_series: {e}")
        await send_message(update, "Проблема при показе следующей карточки.")


# Завершение текущей серии и вывод статистики
async def finish_current_series(update: Update, context):
    session_stats = context.user_data.get("session_stats", {"correct": 0, "total": 0})
    total_answers = session_stats["total"]
    correct_answers = session_stats["correct"]
    percentage = round((correct_answers / total_answers) * 100, 1) if total_answers > 0 else 0

    message = (
        f"📊 Ваша сессия из {total_answers} карточек завершена.\n"
        f"Правильные ответы: {correct_answers}/{total_answers} ({percentage}%).\n\n"
    )

    if percentage >= 80:
        message += "🎉 Отличный результат!"
    elif percentage >= 50:
        message += "👍 Хорошее начало, продолжайте в том же духе."
    else:
        message += "🚀 Ничего страшного, попробуем ещё раз!"

    await send_message(update, message, reply_markup=get_continue_button())


# Обработчик выбора ответа на карточку
async def handle_answer(update: Update, context):
    query = update.callback_query
    await query.answer()

    if query.data == "continue":
        await start_new_session(update, context)
        return

    data = query.data.split(',')
    card_id = int(data[0])
    user_answer = data[1]

    correct_answer = context.user_data.get("correct_answer", "")
    is_correct = (user_answer == correct_answer)

    # Сохраняем результат проверки
    save_review(card_id, user_answer, is_correct)

    # Обновляем статистику сессии
    session_stats = context.user_data.get("session_stats", {"correct": 0, "total": 0})
    if is_correct:
        session_stats["correct"] += 1
    session_stats["total"] += 1
    context.user_data["session_stats"] = session_stats

    # Сообщаем пользователю результат
    explanation = get_explanation(card_id)
    if is_correct:
        message = f"✅ Верно! Ваш ответ: '{user_answer}'\n\n{explanation}"
    else:
        message = f"❌ К сожалению, неверно. Правильный ответ: '{correct_answer}'\n\n{explanation}"

    await query.edit_message_text(message, reply_markup=get_continue_button())

    # Обновляем интервал повторения карточки
    update_card_review_time(card_id, is_correct)


# Обновление интервала повторения карточки
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
    ''', (new_ease, next_review.isoformat(), card_id))
    conn.commit()
    conn.close()


# Получение варианта ответа
def get_options(card_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT answer_text, is_correct FROM card_options WHERE card_id = ?", (card_id,))
    options = cursor.fetchall()
    conn.close()

    if not options:
        return [{"answer_text": "Нет вариантов", "is_correct": False}]

    return [dict(option) for option in options]


# Получение объяснения
def get_explanation(card_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT explanation FROM learning_cards WHERE id = ?", (card_id,))
    result = cursor.fetchone()
    conn.close()
    return result["explanation"]


# Сохранение истории проверок
def save_review(card_id, user_answer, is_correct):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO card_reviews (card_id, user_answer, is_correct)
        VALUES (?, ?, ?)
    ''', (card_id, user_answer, is_correct))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    application = ApplicationBuilder().token(bot_token).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(handle_answer))
    application.run_polling(drop_pending_updates=True)


# Работает, но не делит на сессии и не показывает статистику