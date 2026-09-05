import sys, os
sys.path.insert(0, os.path.join(os.getcwd(), 'oncocare'))
from werkzeug.security import generate_password_hash
import db

USERNAME = 'demo_patient'
PASSWORD = 'demo123'
FULL_NAME = 'Demo Patient'

existing = db.get_user_by_username(USERNAME)
if existing:
    print('Demo patient already exists:', USERNAME)
    print('You can log in with:', USERNAME, '/', PASSWORD)
else:
    uid = db.create_user(username=USERNAME,
                         password_hash=generate_password_hash(PASSWORD),
                         role='patient',
                         full_name=FULL_NAME,
                         email=None,
                         specialization=None,
                         doctor_id=None)
    print('Created demo patient:', USERNAME)
    print('Credentials -> username:', USERNAME, ' password:', PASSWORD)
