from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
import sqlite3
import random
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import logging

# Логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка токена
load_dotenv()
bot_token = os.getenv("TELEGRAM_BOT_TOKEN")

CARDS_PER_SESSION = 5

# Подключение к БД
def get_db():
    conn = sqlite3.connect('task_manager.db')
    conn.row_factory = sqlite3.Row
    return conn

# Получить карточки
def get_batch_of_cards(user_id, count=CARDS_PER_SESSION):
    conn = get_db()
    cursor = conn.cursor()
    today = datetime.now().isoformat()

    cursor.execute('''
        SELECT * FROM learning_cards
        WHERE next_review <= ?
        ORDER BY next_review ASC, RANDOM()
        LIMIT ?
    ''', (today, count))
    ready = cursor.fetchall()

    if len(ready) < count:
        remaining = count - len(ready)
        cursor.execute('''
            SELECT * FROM learning_cards
            WHERE next_review > ?
            ORDER BY next_review ASC
            LIMIT ?
        ''', (today, remaining))
        near_future = cursor.fetchall()
        ready.extend(near_future)

    conn.close()
    return [dict(card) for card in ready]

# Получить кнопки "Продолжить"
def get_continue_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("➡️ Продолжить", callback_data="continue")]])

# Отправка сообщений
async def send_message(update, text, reply_markup=None):
    if update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=reply_markup)
    elif update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_message(update, "Добро пожаловать! Начинаем тренировку.")
    await start_new_session(update, context)

# Начать новую сессию
async def start_new_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    queue = get_batch_of_cards(user_id)

    if not queue:
        await send_message(update, "Нет карточек для показа. Попробуйте позже.")
        return

    context.chat_data["queue"] = queue
    context.chat_data["processed_cards"] = 0
    context.chat_data["session_stats"] = {"correct": 0, "total": 0}

    await show_next_card(update, context)

# Показ карточки
async def show_next_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    queue = context.chat_data.get("queue", [])
    processed = context.chat_data.get("processed_cards", 0)

    logger.info(f"Показ карточки. processed_cards={processed}, осталось в queue={len(queue)}")

    if processed >= CARDS_PER_SESSION or not queue:
        await finish_series(update, context)
        return

    card = queue.pop(0)
    context.chat_data["current_card"] = card

    options = get_options(card["id"])
    random.shuffle(options)
    buttons = []
    correct_answer = None

    for opt in options:
        buttons.append([InlineKeyboardButton(opt["answer_text"],
                        callback_data=f"{card['id']},{opt['answer_text']}")])
        if opt["is_correct"]:
            correct_answer = opt["answer_text"]

    context.chat_data["correct_answer"] = correct_answer

    await send_message(update, f"🔍 Вопрос: {card['question']}",
                       reply_markup=InlineKeyboardMarkup(buttons))

# Завершение серии
async def finish_series(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = context.chat_data.get("session_stats", {"correct": 0, "total": 0})
    total = stats["total"]
    correct = stats["correct"]
    percent = round((correct / total) * 100, 1) if total else 0

    logger.info("Серия завершена. Показываем статистику.")

    msg = (
        f"📊 Сессия завершена.\n"
        f"Правильных ответов: {correct}/{total} ({percent}%)\n\n"
    )

    if percent >= 80:
        msg += "🎉 Отличный результат!"
    elif percent >= 50:
        msg += "👍 Хорошее начало!"
    else:
        msg += "🚀 Не сдавайтесь, всё получится!"

    await send_message(update, msg, reply_markup=get_continue_button())

# Обработка ответов и "Продолжить"
async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "continue":
        await start_new_session(update, context)
        return

    card_id, user_answer = query.data.split(',')
    correct_answer = context.chat_data.get("correct_answer")
    is_correct = (user_answer == correct_answer)

    save_review(int(card_id), user_answer, is_correct)
    update_card_review_time(int(card_id), is_correct)

    stats = context.chat_data.get("session_stats", {"correct": 0, "total": 0})
    stats["total"] += 1
    if is_correct:
        stats["correct"] += 1
    context.chat_data["session_stats"] = stats

    explanation = get_explanation(int(card_id))

    # Формируем новое сообщение: оставляем старый текст + добавляем результат
    original_text = query.message.text  # Это текущий вопрос и варианты
    if is_correct:
        result_text = f"\n\n✅ <b>Верно!</b> Ваш ответ: '<i>{user_answer}</i>'"
    else:
        result_text = f"\n\n❌ <b>Неверно.</b> Правильный ответ: '<i>{correct_answer}</i>'"

    # Добавляем объяснение
    full_text = f"{original_text}{result_text}\n\n{explanation}"

    # Редактируем только текст, оставляя те же кнопки (или меняем на "Продолжить")
    await query.edit_message_text(
        text=full_text,
        parse_mode='HTML',
        reply_markup=get_continue_button()
    )

    # Увеличиваем processed_cards
    count = context.chat_data.get("processed_cards", 0)
    context.chat_data["processed_cards"] = count + 1
    logger.info(f"[Ответ] processed_cards={context.chat_data['processed_cards']}")

# --- Вспомогательные функции ---

def get_options(card_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT answer_text, is_correct FROM card_options WHERE card_id = ?", (card_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_explanation(card_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT explanation FROM learning_cards WHERE id = ?", (card_id,))
    row = cursor.fetchone()
    conn.close()
    return row["explanation"] if row else "Объяснение отсутствует."

def save_review(card_id, answer, is_correct):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO card_reviews (card_id, user_answer, is_correct) VALUES (?, ?, ?)",
                   (card_id, answer, is_correct))
    conn.commit()
    conn.close()

def update_card_review_time(card_id, is_correct):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT ease, review_count FROM learning_cards WHERE id = ?", (card_id,))
    card = cursor.fetchone()

    if is_correct:
        new_ease = min(card["ease"] + 0.1, 2.5)
        interval = max(1, int(card["review_count"] * new_ease))
    else:
        new_ease = max(1.3, card["ease"] - 0.2)
        interval = 1

    next_review = datetime.now() + timedelta(days=interval)
    cursor.execute('''
        UPDATE learning_cards 
        SET ease = ?, review_count = review_count + 1, next_review = ?
        WHERE id = ?
    ''', (new_ease, next_review.isoformat(), card_id))
    conn.commit()
    conn.close()

# Запуск
if __name__ == "__main__":
    # Сначала наполняем базу, если она пустая
    from init_db import init_db_and_populate
    init_db_and_populate()

    # Затем запускаем бота
    app = ApplicationBuilder().token(bot_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_answer))

    print("Бот запущен... ждём сообщений")
    app.run_polling(drop_pending_updates=True)
