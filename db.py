import libsql_client
import time

# ============================================================
# إعدادات Turso
# ============================================================

TURSO_URL = "https://bot-yh12.aws-eu-west-1.turso.io"
TURSO_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3OTAzNjQwMDYsImlkIjoiMDFhMGRhMDItODgwMS03YzEyLTk5MDctOWU3NjUyNzU1ZTJiIiwia2lkIjoiVlBQNnp6OUpNWF93enYwZVJiYTliWkZOcnhfMGw0WlJpTFhBSVJEWHNwQSIsInJpZCI6ImViYzJmNWJkLTA0ZTUtNDQ2Mi05M2QwLTJiNDM2Zjc5OTliYyJ9.ARjNKyILIi5-q6cZim76vGLlGs6H0W4UDiSsOprd7eTYjDbd_kG0g7IxXSB-pScaHVs0L3YbCgL8A6205fYiCg"

# ============================================================
# الاتصال
# ============================================================

def get_client():
    return libsql_client.create_client_sync(url=TURSO_URL, auth_token=TURSO_TOKEN)

# ============================================================
# تهيئة الجداول
# ============================================================

def init_db():
    client = get_client()
    client.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0
        )
    ''')
    client.execute('''
        CREATE TABLE IF NOT EXISTS used_orders (
            order_id TEXT PRIMARY KEY,
            user_id INTEGER,
            amount REAL,
            used_at INTEGER
        )
    ''')
    client.execute('''
        CREATE TABLE IF NOT EXISTS pending_payments (
            user_id INTEGER PRIMARY KEY,
            expected_amount REAL,
            created_at INTEGER
        )
    ''')
    client.close()

# ============================================================
# دوال المستخدمين
# ============================================================

def get_balance(user_id):
    client = get_client()
    result = client.execute("SELECT balance FROM users WHERE user_id = ?", [user_id])
    client.close()
    if result.rows:
        return result.rows[0][0]
    return 0.0

def add_balance(user_id, amount):
    client = get_client()
    client.execute('''
        INSERT INTO users (user_id, balance) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?
    ''', [user_id, amount, amount])
    client.close()

def deduct_balance(user_id, amount):
    client = get_client()
    client.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", [amount, user_id])
    client.close()

# ============================================================
# دوال الأوردرات المستخدمة
# ============================================================

def is_order_used(order_id):
    client = get_client()
    result = client.execute("SELECT order_id FROM used_orders WHERE order_id = ?", [order_id])
    client.close()
    return len(result.rows) > 0

def save_order(order_id, user_id, amount):
    client = get_client()
    try:
        client.execute('''
            INSERT INTO used_orders (order_id, user_id, amount, used_at)
            VALUES (?, ?, ?, ?)
        ''', [order_id, user_id, amount, int(time.time() * 1000)])
    except Exception:
        pass
    client.close()

# ============================================================
# دوال الدفعات المعلقة
# ============================================================

def set_pending(user_id, amount):
    client = get_client()
    now = int(time.time() * 1000)
    client.execute('''
        INSERT INTO pending_payments (user_id, expected_amount, created_at)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET expected_amount = ?, created_at = ?
    ''', [user_id, amount, now, amount, now])
    client.close()

def get_pending(user_id):
    client = get_client()
    result = client.execute("SELECT expected_amount FROM pending_payments WHERE user_id = ?", [user_id])
    client.close()
    if result.rows:
        return result.rows[0][0]
    return None

def clear_pending(user_id):
    client = get_client()
    client.execute("DELETE FROM pending_payments WHERE user_id = ?", [user_id])
    client.close()