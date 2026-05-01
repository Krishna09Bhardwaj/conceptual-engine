import sqlite3
from datetime import datetime

DB_PATH = "client360.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'pm',
            position TEXT DEFAULT '',
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            case_type TEXT NOT NULL,
            deadline TEXT,
            assigned_pm TEXT,
            status TEXT DEFAULT 'Active',
            risk_flag INTEGER DEFAULT 0,
            last_updated TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS data_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            source_type TEXT NOT NULL,
            content TEXT NOT NULL,
            source_url TEXT,
            added_by TEXT DEFAULT 'PM',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients(id)
        );
        CREATE TABLE IF NOT EXISTS action_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            task TEXT NOT NULL,
            assigned_to TEXT,
            due_date TEXT,
            completed INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients(id)
        );
    """)
    conn.commit()
    # Migrate existing DBs that don't have the position column yet
    try:
        conn.execute("ALTER TABLE users ADD COLUMN position TEXT DEFAULT ''")
        conn.commit()
    except Exception:
        pass
    conn.close()


def create_client(name, case_type, deadline, assigned_pm, status="Active", risk_flag=0, notes=""):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO clients (name, case_type, deadline, assigned_pm, status, risk_flag, notes, last_updated)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (name, case_type, deadline, assigned_pm, status, int(risk_flag), notes, datetime.utcnow().isoformat()),
    )
    conn.commit()
    client_id = c.lastrowid
    conn.close()
    return client_id


def get_all_clients():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM clients ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_client(client_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_client(client_id: int, **kwargs):
    allowed = {"name", "case_type", "deadline", "assigned_pm", "status", "risk_flag", "notes"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    updates["last_updated"] = datetime.utcnow().isoformat()
    cols = ", ".join(f"{k}=?" for k in updates)
    vals = list(updates.values()) + [client_id]
    conn = get_conn()
    conn.execute(f"UPDATE clients SET {cols} WHERE id=?", vals)
    conn.commit()
    conn.close()


def update_client_timestamp(client_id: int):
    conn = get_conn()
    conn.execute("UPDATE clients SET last_updated=? WHERE id=?", (datetime.utcnow().isoformat(), client_id))
    conn.commit()
    conn.close()


def add_data_entry(client_id, source_type, content, source_url=None, added_by="PM"):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO data_entries (client_id, source_type, content, source_url, added_by) VALUES (?,?,?,?,?)",
        (client_id, source_type, content[:10000], source_url, added_by),
    )
    conn.commit()
    entry_id = c.lastrowid
    conn.close()
    update_client_timestamp(client_id)
    return entry_id


def delete_data_entry(entry_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM data_entries WHERE id=?", (entry_id,))
    conn.commit()
    conn.close()


def get_data_entries(client_id: int):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM data_entries WHERE client_id=? ORDER BY created_at DESC", (client_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_action_item(client_id, task, assigned_to=None, due_date=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO action_items (client_id, task, assigned_to, due_date) VALUES (?,?,?,?)",
        (client_id, task[:200], assigned_to, due_date),
    )
    conn.commit()
    item_id = c.lastrowid
    conn.close()
    return item_id


def get_action_items(client_id: int):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM action_items WHERE client_id=? ORDER BY completed ASC, created_at DESC",
        (client_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def toggle_action_item(item_id: int, completed: bool):
    conn = get_conn()
    conn.execute("UPDATE action_items SET completed=? WHERE id=?", (1 if completed else 0, item_id))
    conn.commit()
    conn.close()


def delete_client(client_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM action_items WHERE client_id=?", (client_id,))
    conn.execute("DELETE FROM data_entries WHERE client_id=?", (client_id,))
    conn.execute("DELETE FROM clients WHERE id=?", (client_id,))
    conn.commit()
    conn.close()


def is_db_empty():
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
    conn.close()
    return count == 0


# ─── User / Auth ──────────────────────────────────────────────────────────────

def create_user(username: str, name: str, role: str, password_hash: str, position: str = "") -> int:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO users (username, name, role, position, password_hash) VALUES (?,?,?,?,?)",
        (username, name, role, position, password_hash),
    )
    conn.commit()
    row_id = c.lastrowid
    conn.close()
    return row_id


def get_user_by_username(username: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_session(token: str, user_id: int):
    conn = get_conn()
    conn.execute("INSERT INTO sessions (token, user_id) VALUES (?,?)", (token, user_id))
    conn.commit()
    conn.close()


def get_session_user(token: str):
    conn = get_conn()
    row = conn.execute(
        "SELECT u.* FROM sessions s JOIN users u ON s.user_id = u.id WHERE s.token=?",
        (token,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_session(token: str):
    conn = get_conn()
    conn.execute("DELETE FROM sessions WHERE token=?", (token,))
    conn.commit()
    conn.close()


def is_users_empty() -> bool:
    conn = get_conn()
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return count == 0


def get_all_pms():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name, username FROM users WHERE role='pm' ORDER BY name"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_clients_for_pm(pm_name: str):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM clients WHERE assigned_pm=? ORDER BY created_at DESC", (pm_name,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
