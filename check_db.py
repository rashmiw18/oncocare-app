import sqlite3, os
DB=r'c:\Users\nikhi\Downloads\oncocare_ai_app_1\oncocare\oncocare.db'
if not os.path.exists(DB):
    print('DB missing:', DB)
else:
    conn=sqlite3.connect(DB)
    cur=conn.cursor()
    try:
        cur.execute('SELECT COUNT(*) FROM users')
        print('users:', cur.fetchone()[0])
        cur.execute('SELECT COUNT(*) FROM readings')
        print('readings:', cur.fetchone()[0])
        cur.execute('SELECT COUNT(*) FROM notes')
        print('notes:', cur.fetchone()[0])
    except Exception as e:
        print('Error querying DB:', e)
    finally:
        conn.close()
