"""
Одноразовый перенос пользователей из users.json (старое файловое хранилище)
в Postgres. Нужен только один раз, после первого деплоя новой версии бота.

Как использовать:
1. До деплоя новой версии — скачайте текущий users.json из Railway
   (Deployments → Shell → cat users.json), сохраните его рядом с этим
   скриптом под именем users_backup.json.
2. Задеплойте новую версию бота (с Postgres) — таблица users создастся
   автоматически при первом запуске.
3. Запустите этот скрипт с тем же DATABASE_URL, что и у бота:
   DATABASE_URL=postgres://... python migrate_users.py
"""
import json
import os
import sys
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

DATABASE_URL = os.getenv("DATABASE_URL")
BACKUP_FILE = Path(__file__).parent / "users_backup.json"


def main():
    if not DATABASE_URL:
        sys.exit("Укажите DATABASE_URL в переменных окружения")
    if not BACKUP_FILE.exists():
        sys.exit(f"Не найден {BACKUP_FILE}. Сохраните туда содержимое старого users.json")

    users = json.loads(BACKUP_FILE.read_text(encoding="utf-8"))

    conn = psycopg.connect(DATABASE_URL)
    with conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    notifications BOOLEAN NOT NULL DEFAULT TRUE,
                    notify_start BOOLEAN NOT NULL DEFAULT TRUE,
                    notify_15 BOOLEAN NOT NULL DEFAULT TRUE,
                    prayers JSONB NOT NULL DEFAULT '{}'::jsonb
                )
            """)
            for uid_str, u in users.items():
                cur.execute("""
                    INSERT INTO users (user_id, notifications, notify_start, notify_15, prayers)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) DO NOTHING
                """, (
                    int(uid_str),
                    u.get("notifications", True),
                    u.get("notify_start", True),
                    u.get("notify_15", True),
                    Jsonb(u.get("prayers", {})),
                ))
    conn.close()
    print(f"Перенесено пользователей: {len(users)}")


if __name__ == "__main__":
    main()
