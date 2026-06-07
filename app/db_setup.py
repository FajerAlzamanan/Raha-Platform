import psycopg2

DB_CONFIG = {
    'dbname': 'raha',
    'user': 'fellwakh',
    'password': '',
    'host': 'localhost',
    'port': '5432'
}

def create_tables():
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                full_name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'researcher',
                gender TEXT,
                title TEXT,
                professional_role TEXT,
                institution TEXT,
                avatar_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scans (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                filename TEXT NOT NULL,
                original_name TEXT,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending'
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS results (
                id SERIAL PRIMARY KEY,
                scan_id INTEGER REFERENCES scans(id) ON DELETE CASCADE,
                BV_mm3 REAL,
                TV_mm3 REAL,
                BV_TV REAL,
                severity TEXT,
                diagnosis TEXT,
                analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS issues (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                scan_id INTEGER REFERENCES scans(id) ON DELETE SET NULL,
                title TEXT,
                description TEXT,
                status TEXT DEFAULT 'open',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                event_type TEXT,
                description TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS contact_messages (
                id SERIAL PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                email TEXT,
                message TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                token TEXT NOT NULL,
                expires_at TIMESTAMP,
                used BOOLEAN DEFAULT FALSE
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS batches (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                title TEXT,
                image_count INTEGER DEFAULT 0,
                bv_mm3 REAL,
                tv_mm3 REAL,
                bv_tv REAL,
                severity TEXT,
                diagnosis TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            ALTER TABLE scans ADD COLUMN IF NOT EXISTS
                batch_id INTEGER REFERENCES batches(id) ON DELETE SET NULL
        ''')

        cursor.execute('''
            ALTER TABLE scans ADD COLUMN IF NOT EXISTS base_scan_path TEXT
        ''')

        cursor.execute('''
            ALTER TABLE scans ADD COLUMN IF NOT EXISTS ai_mask_path TEXT
        ''')

        cursor.execute('''
            ALTER TABLE results ADD COLUMN IF NOT EXISTS tb_th REAL
        ''')

        cursor.execute('''
            ALTER TABLE results ADD COLUMN IF NOT EXISTS tb_sp REAL
        ''')

        cursor.execute('''
            UPDATE users
            SET
                title = regexp_replace(
                    COALESCE(
                        NULLIF(title, ''),
                        regexp_replace(full_name, '^((Dr|Ms|Mr|Mrs|Prof))\\.?\\s+.*$', '\\1', 'i')
                    ),
                    '\\.$',
                    ''
                ),
                full_name = regexp_replace(
                    regexp_replace(full_name, '^(Dr|Ms|Mr|Mrs|Prof)\\.?\\s+', '', 'i'),
                    '^[\\.\\s]+',
                    ''
                )
            WHERE full_name ~* '^(Dr|Ms|Mr|Mrs|Prof)\\.?\\s+'
               OR full_name ~ '^[\\.\\s]+'
        ''')

        conn.commit()
        print("All tables created!")
    except Exception as e:
        conn.rollback()
        print(f"create_tables error: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    create_tables()
