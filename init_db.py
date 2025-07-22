import sqlite3
from datetime import datetime

def get_db():
    return sqlite3.connect('task_manager.db')

# Функция создания таблиц и наполнения их данными
def init_db_and_populate():
    conn = get_db()
    cursor = conn.cursor()

    # Создание таблиц (если ещё не созданы)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS learning_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,          -- python / sql / git...
            question TEXT NOT NULL,         -- вопрос
            explanation TEXT,                  -- объяснение темы (например, про .get() или JOIN)
            last_review TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            next_review TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            review_count INTEGER DEFAULT 0,
            ease REAL DEFAULT 2.5          -- коэффициент запоминания
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS card_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id INTEGER REFERENCES learning_cards(id),
            user_answer TEXT,
            is_correct BOOLEAN,
            reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS card_options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id INTEGER NOT NULL,
            answer_text TEXT NOT NULL,
            is_correct BOOLEAN NOT NULL,
            FOREIGN KEY(card_id) REFERENCES learning_cards(id)
        )
    ''')



    conn.close()

if __name__ == '__main__':
    init_db_and_populate()