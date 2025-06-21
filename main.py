import sqlite3

# Подключаемся к базе данных (файл будет создан автоматически)
conn = sqlite3.connect('task_manager.db')
cursor = conn.cursor()

# Создаём таблицу items (информационные единицы)
cursor.execute('''
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT NOT NULL,                                 -- тип элемента (task, idea, note, image...)
        title TEXT NOT NULL,                                -- заголовок
        content TEXT,                                       -- содержимое
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,     -- дата создания
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,     -- дата последнего изменения
        item_state TEXT DEFAULT 'incoming',                 -- состояние: входящие / обработанные / в корзине
        is_auto_tagged BOOLEAN DEFAULT FALSE                -- был ли автоматически присвоен тег
    )
''')


# Создаём таблицу tags (универсальные метки)
cursor.execute('''
    CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,                                 -- например: мастерская, срочно_важно, шитьё
        tag_type TEXT NOT NULL,                             -- context, category, collection, habit, person...
        UNIQUE(name, tag_type)
    )
''')


# Создаем таблицу item_tags — связи между информационными единицами и тегами
cursor.execute('''
    CREATE TABLE IF NOT EXISTS item_tags (
        item_id INTEGER REFERENCES items(id),
        tag_id INTEGER REFERENCES tags(id),
        PRIMARY KEY (item_id, tag_id)
    );
''')


# Создаем таблицу - журнал автоматической категоризации
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


# Таблица для повторения цикличных задач
cursor.execute('''
    CREATE TABLE item_repeats (
        item_id INTEGER PRIMARY KEY REFERENCES items(id),
        interval_type TEXT NOT NULL,                        -- daily / weekly / monthly...
        interval_value TEXT,                                -- например: "monday" / "5 days", может быть JSON с деталями
        last_executed TIMESTAMP,
        next_due TIMESTAMP
    );
''')


# Таблица для ресурсов
cursor.execute('''
    CREATE TABLE item_resources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER REFERENCES items(id),
        resource_type TEXT NOT NULL,                        -- time, money, energy...
        value REAL NOT NULL,                                -- например: 30 (минут), 200 (рублей)
        unit TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
''')



# Сохраняем изменения
conn.commit()
conn.close()

print("База данных создана!")

