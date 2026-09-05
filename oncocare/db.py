"""
OncoCare AI — Database layer
=============================
Lightweight SQLite persistence (no ORM) for users (doctors + patients),
vitals readings, and doctor clinical notes. Replaces the old in-memory
history store so data survives server restarts.
"""

import sqlite3
import os
import json
from datetime import datetime
from contextlib import contextmanager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "oncocare.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('doctor', 'patient')),
    full_name TEXT NOT NULL,
    email TEXT,
    specialization TEXT,          -- doctors only
    doctor_id INTEGER,            -- patients only: assigned doctor's user id
    created_at TEXT NOT NULL,
    FOREIGN KEY (doctor_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    logged_by INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    temperature REAL, heart_rate REAL, spo2 REAL, sleep_hours REAL,
    pain_level REAL, fatigue_level REAL, nausea_level REAL, dizziness REAL,
    risk_level TEXT, risk_score REAL,
    is_anomaly INTEGER, anomaly_score REAL,
    flags_json TEXT,
    FOREIGN KEY (patient_id) REFERENCES users(id),
    FOREIGN KEY (logged_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    doctor_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    note TEXT NOT NULL,
    FOREIGN KEY (patient_id) REFERENCES users(id),
    FOREIGN KEY (doctor_id) REFERENCES users(id)
);
"""


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        conn.commit()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def create_user(username, password_hash, role, full_name, email=None,
                 specialization=None, doctor_id=None):
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO users (username, password_hash, role, full_name, email,
                                   specialization, doctor_id, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (username, password_hash, role, full_name, email, specialization,
             doctor_id, datetime.utcnow().isoformat() + "Z")
        )
        conn.commit()
        return cur.lastrowid


def get_user_by_username(username):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def list_doctors():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, full_name, specialization FROM users WHERE role = 'doctor' ORDER BY full_name"
        ).fetchall()
        return [dict(r) for r in rows]


def list_patients_for_doctor(doctor_id):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM users WHERE role = 'patient' AND doctor_id = ? ORDER BY full_name",
            (doctor_id,)
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Readings
# ---------------------------------------------------------------------------

def insert_reading(patient_id, logged_by, vitals, prediction):
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO readings
               (patient_id, logged_by, timestamp, temperature, heart_rate, spo2, sleep_hours,
                pain_level, fatigue_level, nausea_level, dizziness,
                risk_level, risk_score, is_anomaly, anomaly_score, flags_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                patient_id, logged_by, datetime.utcnow().isoformat() + "Z",
                vitals["temperature"], vitals["heart_rate"], vitals["spo2"], vitals["sleep_hours"],
                vitals["pain_level"], vitals["fatigue_level"], vitals["nausea_level"], vitals["dizziness"],
                prediction["risk_level"], prediction["risk_score"],
                int(prediction["is_anomaly"]), prediction["anomaly_score"],
                json.dumps(prediction["flags"])
            )
        )
        conn.commit()
        return cur.lastrowid


def _row_to_record(row):
    d = dict(row)
    d["vitals"] = {
        "temperature": d.pop("temperature"), "heart_rate": d.pop("heart_rate"),
        "spo2": d.pop("spo2"), "sleep_hours": d.pop("sleep_hours"),
        "pain_level": d.pop("pain_level"), "fatigue_level": d.pop("fatigue_level"),
        "nausea_level": d.pop("nausea_level"), "dizziness": d.pop("dizziness"),
    }
    d["is_anomaly"] = bool(d["is_anomaly"])
    d["flags"] = json.loads(d.pop("flags_json") or "[]")
    return d


def get_history(patient_id, limit=200):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM readings WHERE patient_id = ? ORDER BY timestamp DESC LIMIT ?",
            (patient_id, limit)
        ).fetchall()
        records = [_row_to_record(r) for r in rows]
        records.reverse()  # chronological order (oldest -> newest) for charts/tables
        return records


def get_latest_reading(patient_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM readings WHERE patient_id = ? ORDER BY timestamp DESC LIMIT 1",
            (patient_id,)
        ).fetchone()
        return _row_to_record(row) if row else None


def clear_history(patient_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM readings WHERE patient_id = ?", (patient_id,))
        conn.commit()


def get_history_between(patient_id, start_iso, end_iso):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM readings WHERE patient_id = ? AND timestamp BETWEEN ? AND ? ORDER BY timestamp ASC",
            (patient_id, start_iso, end_iso)
        ).fetchall()
        return [_row_to_record(r) for r in rows]


# ---------------------------------------------------------------------------
# Doctor notes
# ---------------------------------------------------------------------------

def add_note(patient_id, doctor_id, note):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO notes (patient_id, doctor_id, timestamp, note) VALUES (?,?,?,?)",
            (patient_id, doctor_id, datetime.utcnow().isoformat() + "Z", note)
        )
        conn.commit()
        return cur.lastrowid


def get_notes(patient_id, limit=50):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT notes.*, users.full_name AS doctor_name FROM notes
               JOIN users ON users.id = notes.doctor_id
               WHERE patient_id = ? ORDER BY timestamp DESC LIMIT ?""",
            (patient_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]
