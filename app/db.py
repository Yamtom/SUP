import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable

DB_PATH = Path(__file__).resolve().parent / "app.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS personnel (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL,
            callsign TEXT,
            unit TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS duty_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            color TEXT NOT NULL,
            description TEXT,
            blocks_availability INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS equipment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            UNIQUE(name, category)
        );

        CREATE TABLE IF NOT EXISTS schedule_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            duty_date TEXT NOT NULL,
            person_id INTEGER NOT NULL,
            duty_type_id INTEGER NOT NULL,
            note TEXT,
            UNIQUE(duty_date, person_id),
            FOREIGN KEY(person_id) REFERENCES personnel(id) ON DELETE CASCADE,
            FOREIGN KEY(duty_type_id) REFERENCES duty_types(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS plan_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_date TEXT NOT NULL,
            unit TEXT NOT NULL,
            mission TEXT NOT NULL,
            start_time TEXT,
            end_time TEXT,
            pilot_id INTEGER,
            navigator_id INTEGER,
            uav_id INTEGER,
            vehicle_id INTEGER,
            battery_id INTEGER,
            notes TEXT,
            FOREIGN KEY(pilot_id) REFERENCES personnel(id) ON DELETE SET NULL,
            FOREIGN KEY(navigator_id) REFERENCES personnel(id) ON DELETE SET NULL,
            FOREIGN KEY(uav_id) REFERENCES equipment(id) ON DELETE SET NULL,
            FOREIGN KEY(vehicle_id) REFERENCES equipment(id) ON DELETE SET NULL,
            FOREIGN KEY(battery_id) REFERENCES equipment(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS vacations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id INTEGER NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'approved',
            FOREIGN KEY(person_id) REFERENCES personnel(id) ON DELETE CASCADE
        );
        """
    )
    conn.commit()
    conn.close()


def seed_if_empty() -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        from .security import hash_password

        cur.executemany(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            [
                ("admin", hash_password("admin123"), "admin"),
                ("planner", hash_password("plan123"), "planner"),
                ("viewer", hash_password("view123"), "viewer"),
            ],
        )

    cur.execute("SELECT COUNT(*) FROM personnel")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO personnel (full_name, role, callsign, unit) VALUES (?, ?, ?, ?)",
            [
                ("Іван Петренко", "Пілот", "Сокол", "11 ПрикЗ"),
                ("Олег Іванов", "Штурман", "Буревій", "11 ПрикЗ"),
                ("Марія Коваленко", "Пілот", "Зірка", "БПАК 1"),
                ("Сергій Дорошенко", "Штурман", "Орел", "БПАК 1"),
            ],
        )

    cur.execute("SELECT COUNT(*) FROM duty_types")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO duty_types (code, name, color, description, blocks_availability) VALUES (?, ?, ?, ?, ?)",
            [
                ("р", "Бойове чергування", "#e74c3c", "Бойове чергування", 1),
                ("зп", "Запасний екіпаж", "#3498db", "Черговий екіпаж у резерві", 0),
                ("в", "Відпустка", "#2ecc71", "Офіційна відпустка", 1),
                ("рс", "Розвідка", "#9b59b6", "Розвідувальні польоти", 1),
            ],
        )

    cur.execute("SELECT COUNT(*) FROM equipment")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO equipment (name, category) VALUES (?, ?)",
            [
                ("БПЛА-1", "uav"),
                ("БПЛА-2", "uav"),
                ("ТЗ-1", "vehicle"),
                ("АКБ-1", "battery"),
            ],
        )

    cur.execute("SELECT COUNT(*) FROM plan_entries")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO plan_entries (plan_date, unit, mission, start_time, end_time, pilot_id, navigator_id, uav_id, vehicle_id, battery_id, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("2025-01-15", "11 ПрикЗ", "Патрулювання", "08:00", "12:00", 1, 2, 1, 3, 4, "Ранковий виліт"),
                ("2025-01-15", "БПАК 1", "Тренування", "13:00", "16:00", 3, 4, 2, None, None, "Підготовка екіпажу"),
            ],
        )

    cur.execute("SELECT COUNT(*) FROM vacations")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO vacations (person_id, start_date, end_date, status) VALUES (?, ?, ?, ?)",
            [
                (1, "2025-02-01", "2025-02-10", "approved"),
                (4, "2025-01-20", "2025-01-25", "approved"),
            ],
        )

    cur.execute("SELECT COUNT(*) FROM schedule_entries")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO schedule_entries (duty_date, person_id, duty_type_id, note) VALUES (?, ?, ?, ?)",
            [
                ("2025-01-15", 1, 1, "Нічне чергування"),
                ("2025-01-15", 2, 2, "Резерв"),
                ("2025-01-16", 3, 4, "Розвідка"),
                ("2025-01-16", 4, 1, "Основний екіпаж"),
            ],
        )

    conn.commit()
    conn.close()
