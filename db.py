import libsql_client
import time

TURSO_URL = "https://bot-yh12.aws-eu-west-1.turso.io"
TURSO_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3OTIwNDU5MjQsImlkIjoiMDFhMGRhMDItODgwMS03YzEyLTk5MDctOWU3NjUyNzU1ZTJiIiwia2lkIjoiVlBQNnp6OUpNWF93enYwZVJiYTliWkZOcnhfMGw0WlJpTFhBSVJEWHNwQSIsInJpZCI6ImViYzJmNWJkLTA0ZTUtNDQ2Mi05M2QwLTJiNDM2Zjc5OTliYyJ9.HqqLiA0YsPrIF9ETqWfbo3l_Vlp7uhsbw_sAEuvhlv6wUuBCaDa0Emn4JxdFWWRwTzRvEapO8tAWHUidtpQ3Cg"

def get_client():
    return libsql_client.create_client_sync(url=TURSO_URL, auth_token=TURSO_TOKEN)

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
    client.execute('''
        CREATE TABLE IF NOT EXISTS insta_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            password TEXT,
            price REAL
        )
    ''')
    client.close()

# ------- المستخدمون -------

def get_balance(user_id):
    client = get_client()
    result = client.execute("SELECT balance FROM users WHERE user_id = ?", [user_id])
    client.close()
    return result.rows[0][0] if result.rows else 0.0

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

# ------- الأوردرات -------

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

# ------- الدفعات المعلقة -------

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
    return result.rows[0][0] if result.rows else None

def clear_pending(user_id):
    client = get_client()
    client.execute("DELETE FROM pending_payments WHERE user_id = ?", [user_id])
    client.close()

# ------- حسابات إنستا -------

def add_insta_account(username, password, price):
    client = get_client()
    client.execute(
        "INSERT INTO insta_accounts (username, password, price) VALUES (?, ?, ?)",
        [username, password, price]
    )
    client.close()

def get_insta_accounts():
    client = get_client()
    result = client.execute("SELECT id, username, password, price FROM insta_accounts")
    client.close()
    return [
        {'id': row[0], 'username': row[1], 'password': row[2], 'price': row[3]}
        for row in result.rows
    ]

def get_insta_account_by_id(acc_id):
    client = get_client()
    result = client.execute(
        "SELECT id, username, password, price FROM insta_accounts WHERE id = ?",
        [acc_id]
    )
    client.close()
    if result.rows:
        row = result.rows[0]
        return {'id': row[0], 'username': row[1], 'password': row[2], 'price': row[3]}
    return None

def delete_insta_account(acc_id):
    client = get_client()
    client.execute("DELETE FROM insta_accounts WHERE id = ?", [acc_id])
    client.close()