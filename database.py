import sqlite3
from datetime import datetime, date

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
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            entity_type TEXT,
            entity_id INTEGER,
            detail TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS pm_digests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pm_name TEXT NOT NULL,
            digest_text TEXT NOT NULL,
            date TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts
            USING fts5(content, source_type, client_id UNINDEXED, entry_id UNINDEXED);
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
    entry_id = c.lastrowid
    try:
        conn.execute(
            "INSERT INTO entries_fts(content, source_type, client_id, entry_id) VALUES (?,?,?,?)",
            (content[:10000], source_type, str(client_id), str(entry_id)),
        )
    except Exception:
        pass
    conn.commit()
    conn.close()
    update_client_timestamp(client_id)
    return entry_id


def get_entry_client_id(entry_id: int):
    conn = get_conn()
    row = conn.execute("SELECT client_id FROM data_entries WHERE id=?", (entry_id,)).fetchone()
    conn.close()
    return row["client_id"] if row else None


def delete_data_entry(entry_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM data_entries WHERE id=?", (entry_id,))
    conn.execute("DELETE FROM entries_fts WHERE entry_id=?", (str(entry_id),))
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
    conn.execute("DELETE FROM entries_fts WHERE client_id=?", (str(client_id),))
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


def log_audit(user_id: int, action: str, entity_type: str = None, entity_id: int = None, detail: str = None):
    conn = get_conn()
    conn.execute(
        "INSERT INTO audit_log (user_id, action, entity_type, entity_id, detail) VALUES (?,?,?,?,?)",
        (user_id, action, entity_type, entity_id, detail),
    )
    conn.commit()
    conn.close()


def get_audit_log(limit: int = 100) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT a.*, u.username, u.name as user_name FROM audit_log a "
        "LEFT JOIN users u ON a.user_id = u.id "
        "ORDER BY a.created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def store_digest(pm_name: str, digest_text: str):
    today = date.today().isoformat()
    conn = get_conn()
    conn.execute(
        "INSERT INTO pm_digests (pm_name, digest_text, date) VALUES (?,?,?)",
        (pm_name, digest_text, today),
    )
    conn.commit()
    conn.close()


def get_latest_digest(pm_name: str) -> dict | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM pm_digests WHERE pm_name=? ORDER BY created_at DESC, id DESC LIMIT 1",
        (pm_name,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_pm_activity_summary() -> list:
    conn = get_conn()
    rows = conn.execute("""
        SELECT
            c.assigned_pm,
            COUNT(DISTINCT de.client_id) as clients_updated,
            SUM(CASE WHEN c.risk_flag=1 THEN 1 ELSE 0 END) as at_risk_count,
            MAX(s.created_at) as last_login
        FROM clients c
        LEFT JOIN data_entries de ON de.client_id = c.id
            AND de.created_at >= datetime('now', '-7 days')
        LEFT JOIN sessions s ON s.user_id = (
            SELECT id FROM users WHERE name = c.assigned_pm LIMIT 1
        )
        WHERE c.assigned_pm IS NOT NULL
        GROUP BY c.assigned_pm
        ORDER BY clients_updated DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_entries_fts(client_id: int, query: str) -> list:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT content FROM entries_fts WHERE client_id=? AND entries_fts MATCH ? ORDER BY rank LIMIT 10",
            (str(client_id), query),
        ).fetchall()
    except Exception:
        rows = []
    conn.close()
    return [r["content"] for r in rows]
