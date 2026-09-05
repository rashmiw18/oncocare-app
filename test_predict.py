import sys, os
sys.path.insert(0, os.path.join(os.getcwd(), 'oncocare'))
from app import app
import db

# Create a doctor and patient for testing (idempotent-ish)
with app.app_context():
    doc = db.get_user_by_username('dr_test')
    if doc:
        doc_id = doc['id']
    else:
        doc_id = db.create_user('dr_test', 'hash', 'doctor', 'Dr Test')

    pat = db.get_user_by_username('patient_test')
    if pat:
        pat_id = pat['id']
    else:
        pat_id = db.create_user('patient_test', 'hash', 'patient', 'Patient Test', doctor_id=doc_id)

# Build a healthy vitals payload
vitals = {
    "temperature": 98.6,
    "heart_rate": 78,
    "spo2": 97,
    "sleep_hours": 7.0,
    "pain_level": 1,
    "fatigue_level": 1,
    "nausea_level": 0,
    "dizziness": 0
}

with app.test_client() as c:
    # Log in as the patient (session emulation)
    with c.session_transaction() as sess:
        sess['user_id'] = pat_id
        sess['role'] = 'patient'
        sess['full_name'] = 'Patient Test'

    resp = c.post('/api/predict', json=vitals)
    print('Status:', resp.status_code)
    try:
        print('Response JSON:', resp.get_json())
    except Exception:
        print('No JSON response')

    # Check DB counts
    import sqlite3
    conn = sqlite3.connect('oncocare/oncocare.db')
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM readings')
    print('readings after POST:', cur.fetchone()[0])
    conn.close()
