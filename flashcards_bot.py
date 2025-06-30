from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
import sqlite3
import random
from datetime import datetime, timedelta

import os
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

# Получаем токен
bot_token = os.getenv("TELEGRAM_BOT_TOKEN")


# Подключение к базе данных
def get_db():
    return sqlite3.connect('task_manager.db')


# Получаем карточку для пользователя
def get_next_card(user_id):
    conn = get_db()
    cursor = conn.cursor()

    today = datetime.now().isoformat()
    cursor.execute('''
        SELECT * FROM learning_cards
        WHERE next_review <= ?
        ORDER BY RANDOM() LIMIT 1
    ''', (today,))

    card = cursor.fetchone()
    conn.close()
    return card


# Команда /start
async def start(update: Update, context):
    await update.message.reply_text("Добро пожаловать в ваш мини-курс программирования!")
    await show_card(update, context)


# Показываем карточку
async def show_card(update: Update, context):
    card = get_next_card(update.effective_user.id)

    if not card:
        await update.message.reply_text("Сегодня нет карточек для повторения. Молодец, ты всё знаешь(ешь)!")
        return

    card_id, category, question, answer, _, _, ease, count = card

    # Создаём несколько вариантов ответа
    options = [answer]
    while len(options) < 4:
        other = get_random_answer(answer)
        if other not in options:
            options.append(other)

    random.shuffle(options)

    buttons = [[InlineKeyboardButton(option, callback_data=f"{card_id},{option}") for option in options]]
    reply_markup = InlineKeyboardMarkup(buttons)

    await update.message.reply_text(f"Карточка ({category}): {question}")
    await update.message.reply_text("Выберите правильный ответ:")
    await update.message.reply_text("", reply_markup=reply_markup)


# Получаем случайный неправильный ответ
def get_random_answer(correct_answer):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT answer FROM learning_cards
        WHERE answer != ?
        ORDER BY RANDOM() LIMIT 1
    ''', (correct_answer,))
    wrong = cursor.fetchone()[0]
    conn.close()
    return wrong


# Обработка ответа
async def handle_answer(update: Update, context):
    query = update.callback_query
    await query.answer()

    data = query.data.split(',')
    card_id = int(data[0])
    user_answer = data[1]

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT answer FROM learning_cards WHERE id = ?", (card_id,))
    correct_answer = cursor.fetchone()[0]
    is_correct = (user_answer == correct_answer)

    # Сохраняем результат
    cursor.execute('''
        INSERT INTO card_reviews (card_id, user_answer, is_correct)
        VALUES (?, ?, ?)
    ''', (card_id, user_answer, is_correct))

    # Обновляем next_review и ease
    cursor.execute("SELECT ease, review_count FROM learning_cards WHERE id = ?", (card_id,))
    current_ease, count = cursor.fetchone()

    if is_correct:
        new_ease = current_ease + 0.1
        new_interval = int(timedelta(days=int(count * new_ease)).total_seconds())
        new_next_review = datetime.now() + timedelta(days=int(count * new_ease))
    else:
        new_ease = max(2.0, current_ease - 0.2)
        new_next_review = datetime.now() + timedelta(days=1)

    new_count = count + 1
    cursor.execute('''
        UPDATE learning_cards SET 
            last_review = ?, 
            next_review = ?, 
            ease = ?, 
            review_count = ?
        WHERE id = ?
    ''', (datetime.now(), new_next_review, new_ease, new_count, card_id))

    conn.commit()
    conn.close()

    if is_correct:
        await query.edit_message_text(text="Правильно! Отлично!")
    else:
        await query.edit_message_text(text=f"Неверно. Правильный ответ: {correct_answer}")


# Запуск бота
if __name__ == '__main__':
    application = ApplicationBuilder().token(bot_token).build()

    start_handler = CommandHandler('start', start)
    application.add_handler(start_handler)
    application.add_handler(CallbackQueryHandler(handle_answer))

    print("Бот запущен... ждём сообщений")
    application.run_polling()