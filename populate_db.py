
# Добавление карточек в базу данных из файлов json (для серверной базы данных)

import os
import json
import sqlite3
from datetime import datetime

def get_db():
    return sqlite3.connect('task_manager.db')

def clear_tables():
    """Очищает все таблицы перед новой загрузкой"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM card_options")
    cursor.execute("DELETE FROM learning_cards")
    cursor.execute("DELETE FROM card_reviews")

    # Очищаем счётчики ID
    cursor.execute("DELETE FROM sqlite_sequence WHERE name='learning_cards'")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name='card_options'")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name='card_reviews'")

    conn.commit()
    conn.close()
    print("🗑️ Все таблицы очищены")

def load_json_file(filename):
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)

def populate_cards(cards):
    conn = get_db()
    cursor = conn.cursor()

    for card in cards:
        # Проверяем, что карточка — это словарь и содержит нужные поля
        if not isinstance(card, dict):
            print(f"⚠️ Пропущен(а) некорректный объект: {card}")
            continue

        # Проверяем обязательные поля
        if "question" not in card:
            print(f"❌ Пропущена карточка: нет поля 'question'")
            continue

        if "category" not in card:
            print(f"❌ Карточка без категории: '{card['question'][:50]}...' — будет установлена 'unknown'")
            card["category"] = "unknown"  # или "python", если знаешь контекст

        if "explanation" not in card:
            card["explanation"] = "Нет объяснения."

        # Проверяем дубликаты
        cursor.execute("SELECT id FROM learning_cards WHERE question = ?", (card["question"],))
        existing = cursor.fetchone()
        if existing:
            print(f"🔁 Уже есть карточка: {card['question']}")
            continue

        # Добавляем карточку
        cursor.execute('''
            INSERT INTO learning_cards 
            (category, question, explanation)
            VALUES (?, ?, ?)
        ''', (
            card["category"],
            card["question"],
            card["explanation"]
        ))

        card_id = cursor.lastrowid

        # Добавляем варианты ответов
        for option in card.get("options", []):
            cursor.execute('''
                INSERT INTO card_options 
                (card_id, answer_text, is_correct)
                VALUES (?, ?, ?)
            ''', (
                card_id,
                option["text"][:30],
                option["is_correct"]
            ))

    conn.commit()
    conn.close()
    print(f"✅ Добавлено {len(cards)} новых карточек")

if __name__ == "__main__":
    # Путь к папке с JSON-файлами
    cards_dir = "cards"
    files = [f for f in os.listdir(cards_dir) if f.endswith(".json")]

    for file in files:
        print(f"🔄 Загружаем файл: {file}")
        full_path = os.path.join(cards_dir, file)
        cards = load_json_file(full_path)
        populate_cards(cards)