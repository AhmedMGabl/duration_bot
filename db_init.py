# -*- coding: utf-8 -*-
"""
db_init.py
Initialize SQLite database with schema for duration_bot.
"""
import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'db', 'duration_bot.db')

def init_db():
    """Create database schema if not exists."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Schedule config (single row)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS schedule_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            cron_expression TEXT NOT NULL,
            enabled BOOLEAN DEFAULT 1,
            selected_groups TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Run history
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS run_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            status TEXT CHECK(status IN ('running', 'success', 'failed')),
            trigger_type TEXT,
            groups_sent TEXT,
            output_log TEXT,
            error_message TEXT
        )
    ''')

    # Available groups cache
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS available_groups (
            chat_id TEXT PRIMARY KEY,
            chat_name TEXT,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Create indexes for frequently queried columns
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_run_history_status ON run_history(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_run_history_started_at ON run_history(started_at DESC)')

    # Insert default schedule if empty
    cursor.execute('SELECT COUNT(*) FROM schedule_config')
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            INSERT INTO schedule_config (id, cron_expression, enabled, selected_groups)
            VALUES (1, '0 14 * * *', 1, '[]')
        ''')

    conn.commit()
    conn.close()
    print(f'Database initialized at {DB_PATH}')

if __name__ == '__main__':
    init_db()
