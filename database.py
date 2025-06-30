import sqlite3

def init_db():
    conn = sqlite3.connect('task_manager.db')
    cursor = conn.cursor()

    # Таблица items (информационные единицы)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,                                 -- task, idea, note...
            title TEXT NOT NULL,                                -- заголовок или краткое описание
            content TEXT,                                       -- содержимое (подробности)
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,     -- дата создания
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,     -- дата последнего изменения
            item_state TEXT DEFAULT 'incoming',                 -- incoming / processed / in_trash
            is_auto_tagged BOOLEAN DEFAULT FALSE,               -- была ли автоматическая категоризация
            outcome TEXT,                                       -- результат выполнения задачи
            needs_confirmation BOOLEAN DEFAULT FALSE            -- задача была создана программой
        )
    ''')

    # Таблица tags (универсальные метки)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,                                 -- например: мастерская, срочно_важно, шитьё
            tag_type TEXT NOT NULL,                             -- context, category, collection, habit, person...
            UNIQUE(name, tag_type)
        )
    ''')

    # Таблица item_tags (связи между информационными единицами и тегами)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS item_tags (
            item_id INTEGER REFERENCES items(id),
            tag_id INTEGER REFERENCES tags(id),
            PRIMARY KEY (item_id, tag_id)
        )
    ''')

    # Таблица auto_tagging_log (журнал автоматической категоризации)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS auto_tagging_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER REFERENCES items(id),
            tag_id INTEGER REFERENCES tags(id),
            reason TEXT,                                        -- причина, по которой присвоен тег (обнаружена дата / обнаружена персона / обнаружено ключевое слово / и т.д.)
            confidence REAL,                                    -- уровень уверенности, с которой тег был присвоен (0.95 — высокая уверенность, 0.6 — средняя, 0.3 — возможно, стоит проверить)
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP      -- время, когда была записана эта информация
        )
    ''')

    # Таблица item_repeats (повторения цикличных задач)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS item_repeats (
            item_id INTEGER PRIMARY KEY REFERENCES items(id),
            repeat_type TEXT NOT NULL,                          -- daily / weekly / monthly...
            repeat_value TEXT,                                  -- например: "monday" / "5 days", может быть JSON с деталями
            last_executed TIMESTAMP,
            next_due TIMESTAMP
        )
    ''')

    # Таблица item_resources (ресурсы, требуемые для выполнения задачи)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS item_resources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER REFERENCES items(id),
            resource_type TEXT NOT NULL,                        -- time, money, energy...
            value REAL NOT NULL,                                -- например: 30 (минут), 200 (рублей)
            unit TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Таблица item_dependencies (хранение цепочек задач)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS item_dependencies (
            parent_id INTEGER REFERENCES items(id),
            child_id INTEGER REFERENCES items(id),
            dependency_type TEXT DEFAULT 'subtask',
            PRIMARY KEY (parent_id, child_id)
        )
    ''')

    # Таблица message_patterns (обучение системы - составление списка правил обработки запроса пользователя)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS message_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_message TEXT NOT NULL,                          -- исходное сообщение от пользователя
            parsed_task TEXT,                                   -- JSON: основная задача
            parsed_subtasks TEXT,                               -- JSON: список подзадач
            parsed_tags TEXT,                                   -- JSON: теги
            parsed_resources TEXT,                              -- JSON: ресурсы
            is_confirmed BOOLEAN DEFAULT FALSE,                 -- пользователь подтвердил правило
            use_count INTEGER DEFAULT 0,                        -- сколько раз применяли это правило
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Таблица для самообучения (модуль обучения) на основе интервального повторения
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS learning_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,          -- python / sql / git...
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            last_review TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            next_review TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            review_count INTEGER DEFAULT 0,
            ease REAL DEFAULT 2.5           -- коэффициент запоминания (Anki-style)
    ''')

    # Таблица для хранения истории ответов (модуль обучения)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS card_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id INTEGER REFERENCES learning_cards(id),
            user_answer TEXT,
            is_correct BOOLEAN,
            reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()