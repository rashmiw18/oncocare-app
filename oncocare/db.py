"""
OncoCare AI — Database layer (PostgreSQL)
=============================
PostgreSQL persistence for users, readings, and notes.
"""

import os
import json
import psycopg2
import psycopg2.extras
from datetime import datetime
from contextlib import contextmanager

DATABASE_URL = os.environ.get("DATABASE_URL")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('doctor', 'patient')),
    full_name TEXT NOT NULL,
    email TEXT,
    specialization TEXT,
    doctor_id INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS readings (
    id SERIAL PRIMARY KEY,
    patient_id INTEGER NOT NULL,
    logged_by INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    temperature REAL, heart_rate REAL, spo2 REAL, sleep_hours REAL,
    pain_level REAL, fatigue_level REAL, nausea_level REAL, dizziness REAL,
    risk_level TEXT, risk_score REAL,
    is_anomaly INTEGER, anomaly_score REAL,
    flags_json TEXT
);

CREATE TABLE IF NOT EXISTS notes (
    id SERIAL PRIMARY KEY,
    patient_id INTEGER NOT NULL,
    doctor_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    note TEXT NOT NULL
);
"""

def init_db():
    if not DATABASE_URL:
        # Fallback if no URL is set (for local testing, though it will fail if not using sqlite)
        # We assume if init_db is called, environment is setup or it is deploying.
        pass
    else:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(SCHEMA)
            conn.commit()


@contextmanager
def get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def create_user(username, password_hash, role, full_name, email=None,
                 specialization=None, doctor_id=None):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO users (username, password_hash, role, full_name, email,
                                   specialization, doctor_id, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (username, password_hash, role, full_name, email, specialization,
             doctor_id, datetime.utcnow().isoformat() + "Z")
        )
        user_id = cur.fetchone()[0]
        conn.commit()
        return user_id

def get_user_by_username(username):
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        row = cur.fetchone()
        return dict(row) if row else None

def get_user_by_id(user_id):
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        return dict(row) if row else None

def list_doctors():
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT id, full_name, specialization FROM users WHERE role = 'doctor' ORDER BY full_name")
        rows = cur.fetchall()
        return [dict(r) for r in rows]

def list_patients_for_doctor(doctor_id):
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT * FROM users WHERE role = 'patient' AND doctor_id = %s ORDER BY full_name", (doctor_id,))
        rows = cur.fetchall()
        return [dict(r) for r in rows]

# ---------------------------------------------------------------------------
# Readings
# ---------------------------------------------------------------------------

def insert_reading(patient_id, logged_by, vitals, prediction):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO readings
               (patient_id, logged_by, timestamp, temperature, heart_rate, spo2, sleep_hours,
                pain_level, fatigue_level, nausea_level, dizziness,
                risk_level, risk_score, is_anomaly, anomaly_score, flags_json)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (
                patient_id, logged_by, datetime.utcnow().isoformat() + "Z",
                vitals["temperature"], vitals["heart_rate"], vitals["spo2"], vitals["sleep_hours"],
                vitals["pain_level"], vitals["fatigue_level"], vitals["nausea_level"], vitals["dizziness"],
                prediction["risk_level"], prediction["risk_score"],
                int(prediction["is_anomaly"]), prediction["anomaly_score"],
                json.dumps(prediction["flags"])
            )
        )
        reading_id = cur.fetchone()[0]
        conn.commit()
        return reading_id

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
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT * FROM readings WHERE patient_id = %s ORDER BY timestamp DESC LIMIT %s", (patient_id, limit))
        rows = cur.fetchall()
        records = [_row_to_record(r) for r in rows]
        records.reverse()
        return records

def get_latest_reading(patient_id):
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT * FROM readings WHERE patient_id = %s ORDER BY timestamp DESC LIMIT 1", (patient_id,))
        row = cur.fetchone()
        return _row_to_record(row) if row else None

def clear_history(patient_id):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM readings WHERE patient_id = %s", (patient_id,))
        conn.commit()

def get_history_between(patient_id, start_iso, end_iso):
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT * FROM readings WHERE patient_id = %s AND timestamp BETWEEN %s AND %s ORDER BY timestamp ASC", (patient_id, start_iso, end_iso))
        rows = cur.fetchall()
        return [_row_to_record(r) for r in rows]

# ---------------------------------------------------------------------------
# Doctor notes
# ---------------------------------------------------------------------------

def add_note(patient_id, doctor_id, note):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO notes (patient_id, doctor_id, timestamp, note) VALUES (%s,%s,%s,%s) RETURNING id",
            (patient_id, doctor_id, datetime.utcnow().isoformat() + "Z", note))
        note_id = cur.fetchone()[0]
        conn.commit()
        return note_id

def get_notes(patient_id, limit=50):
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            """SELECT notes.*, users.full_name AS doctor_name FROM notes
               JOIN users ON users.id = notes.doctor_id
               WHERE patient_id = %s ORDER BY timestamp DESC LIMIT %s""",
            (patient_id, limit)
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]
