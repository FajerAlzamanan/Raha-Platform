import sqlite3

DB_PATH = 'raha.db'

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ─── Fajer's Helpers ───────────────────────────

def create_user(full_name, email, password_hash, role='researcher', gender=None, title=None, professional_role=None):
    with get_conn() as conn:
        conn.execute(
            'INSERT INTO Users (full_name,email,password_hash,role,gender,title,professional_role) VALUES (?,?,?,?,?,?,?)',
            (full_name, email, password_hash, role, gender, title, professional_role)
        )

def get_user(email):
    with get_conn() as conn:
        row = conn.execute('SELECT * FROM Users WHERE email=?', (email,)).fetchone()
        return dict(row) if row else None

def save_scan(user_id, filename, original_name):
    with get_conn() as conn:
        cursor = conn.execute(
            'INSERT INTO Scans (user_id,filename,original_name) VALUES (?,?,?)',
            (user_id, filename, original_name)
        )
        return cursor.lastrowid

def save_reset_token(user_id, token, expires_at):
    with get_conn() as conn:
        conn.execute(
            'INSERT INTO PasswordResetTokens (user_id,token,expires_at) VALUES (?,?,?)',
            (user_id, token, expires_at)
        )

def verify_reset_token(token):
    with get_conn() as conn:
        row = conn.execute(
            'SELECT * FROM PasswordResetTokens WHERE token=? AND used=0 AND expires_at > CURRENT_TIMESTAMP',
            (token,)
        ).fetchone()
        return dict(row) if row else None

def save_contact_message(first_name, last_name, email, message):
    with get_conn() as conn:
        conn.execute(
            'INSERT INTO ContactMessages (first_name,last_name,email,message) VALUES (?,?,?,?)',
            (first_name, last_name, email, message)
        )

# ─── Sarah's Helpers ───────────────────────────

def get_user_by_id(user_id):
    with get_conn() as conn:
        row = conn.execute('SELECT * FROM Users WHERE id=?', (user_id,)).fetchone()
        return dict(row) if row else None

def update_user(user_id, fields: dict):
    with get_conn() as conn:
        sets = ', '.join(f'{k}=?' for k in fields)
        conn.execute(f'UPDATE Users SET {sets} WHERE id=?', (*fields.values(), user_id))

def get_results_by_scan(scan_id):
    with get_conn() as conn:
        row = conn.execute('SELECT * FROM Results WHERE scan_id=?', (scan_id,)).fetchone()
        return dict(row) if row else None

def save_issue(user_id, scan_id, title, description):
    with get_conn() as conn:
        conn.execute(
            'INSERT INTO Issues (user_id,scan_id,title,description) VALUES (?,?,?,?)',
            (user_id, scan_id, title, description)
        )

def get_issues():
    with get_conn() as conn:
        rows = conn.execute(
            'SELECT Issues.*, Users.full_name FROM Issues JOIN Users ON Issues.user_id=Users.id'
        ).fetchall()
        return [dict(r) for r in rows]

def get_system_logs(limit=100):
    with get_conn() as conn:
        rows = conn.execute(
            'SELECT * FROM SystemLogs ORDER BY timestamp DESC LIMIT ?', (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

# ─── Analysis Helpers ───────────────────────────

def save_results(scan_id, BV, TV, BV_TV, severity):
    with get_conn() as conn:
        conn.execute(
            'INSERT INTO Results (scan_id,BV_mm3,TV_mm3,BV_TV,severity) VALUES (?,?,?,?,?)',
            (scan_id, BV, TV, BV_TV, severity)
        )

def get_scan_filename(scan_id):
    with get_conn() as conn:
        row = conn.execute('SELECT filename FROM Scans WHERE id=?', (scan_id,)).fetchone()
        return row['filename'] if row else None

def log_event(user_id, event_type, description):
    with get_conn() as conn:
        conn.execute(
            'INSERT INTO SystemLogs (user_id,event_type,description) VALUES (?,?,?)',
            (user_id, event_type, description)
        )