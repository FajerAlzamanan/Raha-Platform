import psycopg2
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    'dbname': 'raha',
    'user': 'fellwakh',
    'password': '',
    'host': 'localhost',
    'port': '5432'
}

def get_conn():
    try:
        return psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        print(f"Connection error: {e}")
        return None

from contextlib import contextmanager

@contextmanager
def _conn():
    conn = get_conn()
    if conn is None:
        raise RuntimeError("Could not connect to database")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# ─── Fajer's Helpers ───────────────────────────

def create_user(full_name, email, password_hash, role='researcher', gender=None, title=None, professional_role=None, institution=None):
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO users (full_name,email,password_hash,role,gender,title,professional_role,institution) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                    (full_name, email, password_hash, role, gender, title, professional_role, institution)
                )
    except Exception as e:
        print(f"create_user error: {e}")
        return None

def get_user(email):
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('SELECT * FROM users WHERE email=%s', (email,))
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as e:
        print(f"get_user error: {e}")
        return None

def save_scan(user_id, filename, original_name):
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO scans (user_id,filename,original_name) VALUES (%s,%s,%s) RETURNING id',
                    (user_id, filename, original_name)
                )
                return cur.fetchone()[0]
    except Exception as e:
        print(f"save_scan error: {e}")
        return None

def save_reset_token(user_id, token, expires_at):
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO password_reset_tokens (user_id,token,expires_at) VALUES (%s,%s,%s)',
                    (user_id, token, expires_at)
                )
    except Exception as e:
        print(f"save_reset_token error: {e}")
        return None

def verify_reset_token(token):
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    'SELECT * FROM password_reset_tokens WHERE token=%s AND used=FALSE AND expires_at > NOW()',
                    (token,)
                )
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as e:
        print(f"verify_reset_token error: {e}")
        return None

def save_contact_message(first_name, last_name, email, message):
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO contact_messages (first_name,last_name,email,message) VALUES (%s,%s,%s,%s)',
                    (first_name, last_name, email, message)
                )
    except Exception as e:
        print(f"save_contact_message error: {e}")
        return None

# ─── Sarah's Helpers ───────────────────────────

def get_user_by_id(user_id):
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('SELECT * FROM users WHERE id=%s', (user_id,))
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as e:
        print(f"get_user_by_id error: {e}")
        return None

_ALLOWED_USER_FIELDS = {
    'full_name', 'email', 'password_hash', 'role', 'gender',
    'title', 'professional_role', 'institution', 'avatar_url'
}

def update_user(user_id, fields: dict):
    invalid = set(fields) - _ALLOWED_USER_FIELDS
    if invalid:
        raise ValueError(f"Invalid fields: {invalid}")
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                sets = ', '.join(f'{k}=%s' for k in fields)
                cur.execute(f'UPDATE users SET {sets} WHERE id=%s', (*fields.values(), user_id))
    except Exception as e:
        print(f"update_user error: {e}")
        return None

def update_avatar(user_id, avatar_url):
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'UPDATE users SET avatar_url=%s WHERE id=%s',
                    (avatar_url, user_id)
                )
    except Exception as e:
        print(f"update_avatar error: {e}")
        return None

def delete_user(user_id):
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute('UPDATE scans SET user_id=NULL WHERE user_id=%s', (user_id,))
                cur.execute('UPDATE issues SET user_id=NULL WHERE user_id=%s', (user_id,))
                cur.execute('UPDATE system_logs SET user_id=NULL WHERE user_id=%s', (user_id,))
                cur.execute('DELETE FROM users WHERE id=%s', (user_id,))
    except Exception as e:
        print(f"delete_user error: {e}")
        return None

def get_results_by_scan(scan_id):
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    '''SELECT id, scan_id,
                              bv_mm3 AS "BV_mm3", tv_mm3 AS "TV_mm3", bv_tv AS "BV_TV",
                              severity, diagnosis, analyzed_at
                       FROM results WHERE scan_id=%s''',
                    (scan_id,)
                )
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"get_results_by_scan error: {e}")
        return None

def save_issue(user_id, scan_id, title, description):
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO issues (user_id,scan_id,title,description) VALUES (%s,%s,%s,%s)',
                    (user_id, scan_id, title, description)
                )
    except Exception as e:
        print(f"save_issue error: {e}")
        return None

def get_issues():
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('SELECT issues.*, users.full_name FROM issues JOIN users ON issues.user_id=users.id')
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"get_issues error: {e}")
        return None

def get_system_logs(limit=100):
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('SELECT * FROM system_logs ORDER BY timestamp DESC LIMIT %s', (limit,))
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"get_system_logs error: {e}")
        return None

# ─── Analysis Helpers ───────────────────────────

def save_results(scan_id, BV, TV, BV_TV, severity, diagnosis=None):
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO results (scan_id,BV_mm3,TV_mm3,BV_TV,severity,diagnosis) VALUES (%s,%s,%s,%s,%s,%s)',
                    (scan_id, BV, TV, BV_TV, severity, diagnosis)
                )
    except Exception as e:
        print(f"save_results error: {e}")
        return None

def get_scan_filename(scan_id):
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT filename FROM scans WHERE id=%s', (scan_id,))
                row = cur.fetchone()
                return row[0] if row else None
    except Exception as e:
        print(f"get_scan_filename error: {e}")
        return None

def log_event(user_id, event_type, description):
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO system_logs (user_id,event_type,description) VALUES (%s,%s,%s)',
                    (user_id, event_type, description)
                )
    except Exception as e:
        print(f"log_event error: {e}")
        return None

# ─── Admin Helpers ───────────────────────────
def admin_get_all_users():
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('SELECT * FROM users')
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"admin_get_all_users error: {e}")
        return None

def admin_create_user(full_name, email, password_hash, role, gender=None, title=None, professional_role=None, institution=None):
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO users (full_name,email,password_hash,role,gender,title,professional_role,institution) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                    (full_name, email, password_hash, role, gender, title, professional_role, institution)
                )
    except Exception as e:
        print(f"admin_create_user error: {e}")
        return None

def admin_delete_user(user_id):
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute('UPDATE scans SET user_id=NULL WHERE user_id=%s', (user_id,))
                cur.execute('UPDATE issues SET user_id=NULL WHERE user_id=%s', (user_id,))
                cur.execute('UPDATE system_logs SET user_id=NULL WHERE user_id=%s', (user_id,))
                cur.execute('DELETE FROM users WHERE id=%s', (user_id,))
    except Exception as e:
        print(f"admin_delete_user error: {e}")
        return None

def get_analysis_history(user_id):
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('''
                    SELECT scans.*,
                           results.bv_mm3 AS "BV_mm3",
                           results.tv_mm3 AS "TV_mm3",
                           results.bv_tv  AS "BV_TV",
                           results.severity, results.diagnosis,
                           results.analyzed_at,
                           CONCAT('/uploads/', scans.filename) as file_url
                    FROM scans LEFT JOIN results ON scans.id = results.scan_id
                    WHERE scans.user_id=%s ORDER BY scans.uploaded_at DESC
                ''', (user_id,))
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"get_analysis_history error: {e}")
        return None