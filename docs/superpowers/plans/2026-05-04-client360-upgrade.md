# Client 360 Intelligence Engine — Full Upgrade Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the existing Client 360 system with proper vector retrieval (LlamaIndex), structured AI output (Instructor), smart risk detection, APScheduler jobs, Mem0 PM memory, admin view, and audit logging — without rebuilding anything from scratch.

**Architecture:** Replace naive full-document context injection with LlamaIndex-managed per-client ChromaDB collections (512-token chunks, top-5 retrieval). Force all AI responses to return `ClientStatus` Pydantic objects via Instructor + LiteLLM. Layer APScheduler jobs inside FastAPI's lifespan for daily risk scans and morning digests.

**Tech Stack:** LlamaIndex 0.10+, ChromaDB, sentence-transformers (all-MiniLM-L6-v2), LiteLLM, Instructor, Mem0, APScheduler, spaCy en_core_web_sm, MarkItDown, dateparser, SQLite FTS5, FastAPI lifespan

**Working directory:** `/Users/krishnabhardwaj/developer/conceptual-engine/jinee-client360`

---

## File Map

**Modify:**
- `requirements.txt` — add all new packages
- `database.py` — add `audit_log`, `pm_digests` tables, FTS5 virtual table, new CRUD fns
- `vector_store.py` — full rewrite: LlamaIndex + per-client `client_{id}` ChromaDB collections
- `ai_engine.py` — full rewrite: LiteLLM + Instructor + `ClientStatus` structured output + Mem0 context
- `parsers.py` — upgrade: MarkItDown for PDFs, spaCy date extraction, dateparser in WhatsApp parser
- `main.py` — add admin routes, audit logging calls, APScheduler lifespan, Mem0 after-query hook

**Create:**
- `risk_engine.py` — two-layer risk detection (rule engine + deadline math)
- `scheduler.py` — APScheduler job definitions
- `memory_engine.py` — Mem0 wrapper
- `tests/test_risk_engine.py`
- `tests/test_vector_store.py`
- `tests/test_ai_engine.py`
- `tests/test_parsers.py`
- `frontend/index.html` — upgrade: render `ClientStatus` structured cards, admin view, digest panel

---

## Task 1: Install Packages

**Files:**
- Modify: `requirements.txt`
- Modify: `setup.sh`, `setup.bat`

- [ ] **Step 1: Update requirements.txt**

```text
fastapi
uvicorn[standard]
chromadb
sentence-transformers
groq
google-generativeai
httpx
python-multipart
python-dotenv
aiofiles
pypdf
pdfplumber
python-docx
llama-index
llama-index-vector-stores-chroma
llama-index-embeddings-huggingface
litellm
instructor
mem0ai
apscheduler
spacy
markitdown[all]
dateparser
python-dateutil
pytz
pytest
pytest-asyncio
```

- [ ] **Step 2: Install everything**

```bash
source venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

Expected: all packages install without error. spaCy downloads `en_core_web_sm` model.

- [ ] **Step 3: Verify key imports**

```bash
python3 -c "import llama_index; import litellm; import instructor; import mem0; import apscheduler; import spacy; print('All OK')"
```

Expected: `All OK`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt setup.sh setup.bat
git commit -m "chore: add upgrade dependencies"
```

---

## Task 2: Database — Audit Log, Digests, FTS5

**Files:**
- Modify: `database.py`
- Create: `tests/test_db_schema.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_db_schema.py`:

```python
import sqlite3
import os
import pytest

TEST_DB = "/tmp/test_client360.db"

@pytest.fixture(autouse=True)
def clean_db():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    import database
    orig = database.DB_PATH
    database.DB_PATH = TEST_DB
    database.init_db()
    yield
    database.DB_PATH = orig
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)

def test_audit_log_table_exists():
    conn = sqlite3.connect(TEST_DB)
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'").fetchone()
    conn.close()
    assert row is not None

def test_pm_digests_table_exists():
    conn = sqlite3.connect(TEST_DB)
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pm_digests'").fetchone()
    conn.close()
    assert row is not None

def test_fts5_table_exists():
    conn = sqlite3.connect(TEST_DB)
    row = conn.execute("SELECT name FROM sqlite_master WHERE name='entries_fts'").fetchone()
    conn.close()
    assert row is not None

def test_log_audit_and_retrieve():
    import database
    database.log_audit(user_id=1, action="feed_data", entity_type="client", entity_id=5, detail="whatsapp upload")
    conn = sqlite3.connect(TEST_DB)
    row = conn.execute("SELECT * FROM audit_log WHERE user_id=1").fetchone()
    conn.close()
    assert row is not None
    assert row[2] == "feed_data"

def test_store_and_get_digest():
    import database
    database.store_digest("tulsi", "Today: 3 at-risk clients")
    digest = database.get_latest_digest("tulsi")
    assert digest is not None
    assert "3 at-risk" in digest["digest_text"]
```

- [ ] **Step 2: Run — verify it fails**

```bash
cd /Users/krishnabhardwaj/developer/conceptual-engine/jinee-client360
source venv/bin/activate
python -m pytest tests/test_db_schema.py -v
```

Expected: FAIL — `audit_log` table doesn't exist, `log_audit` not defined.

- [ ] **Step 3: Add new schema and functions to database.py**

In `database.py`, replace `init_db()` with this (keep all existing tables, add at the end of the `executescript`):

```python
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
    try:
        conn.execute("ALTER TABLE users ADD COLUMN position TEXT DEFAULT ''")
        conn.commit()
    except Exception:
        pass
    conn.close()
```

Then add these functions at the bottom of `database.py`:

```python
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
    from datetime import date
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
        "SELECT * FROM pm_digests WHERE pm_name=? ORDER BY created_at DESC LIMIT 1",
        (pm_name,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_pm_activity_summary() -> list:
    """For admin: per-PM stats for the past 7 days."""
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


def search_entries_fts(client_id: int, query: str) -> list[str]:
    """FTS5 keyword search across a client's entries."""
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
```

Also update `add_data_entry` to insert into FTS5 after the main insert:

```python
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
```

- [ ] **Step 4: Run tests — verify pass**

```bash
python -m pytest tests/test_db_schema.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add database.py tests/test_db_schema.py
git commit -m "feat: add audit_log, pm_digests, FTS5 tables and CRUD functions"
```

---

## Task 3: Vector Store — LlamaIndex + Per-Client ChromaDB Collections

**Files:**
- Modify: `vector_store.py` (full rewrite)
- Create: `tests/test_vector_store.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_vector_store.py`:

```python
import pytest
import shutil
import os

TEST_CHROMA_PATH = "/tmp/test_chroma_vs"

@pytest.fixture(autouse=True)
def clean_chroma(monkeypatch):
    if os.path.exists(TEST_CHROMA_PATH):
        shutil.rmtree(TEST_CHROMA_PATH)
    import vector_store
    monkeypatch.setattr(vector_store, "CHROMA_PATH", TEST_CHROMA_PATH)
    vector_store._chroma_client = None  # force reinit
    yield
    if os.path.exists(TEST_CHROMA_PATH):
        shutil.rmtree(TEST_CHROMA_PATH)

def test_add_and_query_returns_relevant_chunk():
    from vector_store import add_to_vector_store, query_client
    add_to_vector_store(
        client_id=1,
        client_name="Test Client",
        source_type="note",
        content="Dr. Williams sent the recommendation letter on April 15th. The letter is strong.",
        entry_id=1,
    )
    results = query_client(client_id=1, question="recommendation letter", n_results=3)
    assert len(results) > 0
    assert any("Williams" in r or "recommendation" in r for r in results)

def test_different_clients_isolated():
    from vector_store import add_to_vector_store, query_client
    add_to_vector_store(1, "Client A", "note", "Client A has an RFE pending.", 1)
    add_to_vector_store(2, "Client B", "note", "Client B deadline is March 2027.", 2)
    results_a = query_client(client_id=1, question="RFE", n_results=5)
    results_b = query_client(client_id=2, question="RFE", n_results=5)
    # Client B should not return Client A's RFE content
    assert not any("Client A" in r for r in results_b)

def test_delete_removes_vectors():
    from vector_store import add_to_vector_store, query_client, delete_client_vectors
    add_to_vector_store(1, "Test", "note", "Secret data only for client 1.", 1)
    delete_client_vectors(1)
    results = query_client(client_id=1, question="secret data", n_results=5)
    assert results == []
```

- [ ] **Step 2: Run — verify fails**

```bash
python -m pytest tests/test_vector_store.py -v
```

Expected: FAIL — imports work but behavior is wrong (current code uses single shared collection).

- [ ] **Step 3: Rewrite vector_store.py**

Replace entire `vector_store.py` with:

```python
"""
Vector store: LlamaIndex + ChromaDB, per-client collections named client_{id}.
Embeddings: all-MiniLM-L6-v2 via HuggingFace (local, no API cost).
Chunking: 512 tokens, 50-token overlap.
"""
import chromadb
from llama_index.core import VectorStoreIndex, Document, Settings
from llama_index.core.node_parser import SentenceSplitter
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core import StorageContext

CHROMA_PATH = "./chroma_db"

Settings.embed_model = HuggingFaceEmbedding(model_name="all-MiniLM-L6-v2")
Settings.transformations = [SentenceSplitter(chunk_size=512, chunk_overlap=50)]

_chroma_client: chromadb.PersistentClient | None = None


def _get_chroma() -> chromadb.PersistentClient:
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    return _chroma_client


def _get_index(client_id: int) -> VectorStoreIndex:
    collection = _get_chroma().get_or_create_collection(f"client_{client_id}")
    vector_store = ChromaVectorStore(chroma_collection=collection)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    return VectorStoreIndex.from_vector_store(vector_store, storage_context=storage_context)


def add_to_vector_store(client_id: int, client_name: str, source_type: str, content: str, entry_id: int):
    try:
        collection = _get_chroma().get_or_create_collection(f"client_{client_id}")
        vector_store = ChromaVectorStore(chroma_collection=collection)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        doc = Document(
            text=content,
            metadata={
                "client_id": str(client_id),
                "client_name": client_name,
                "source_type": source_type,
                "entry_id": str(entry_id),
            },
            doc_id=f"entry_{entry_id}",
        )
        VectorStoreIndex.from_documents(
            [doc],
            storage_context=storage_context,
        )
    except Exception:
        pass


def query_client(client_id: int, question: str, n_results: int = 5) -> list[str]:
    try:
        index = _get_index(client_id)
        retriever = index.as_retriever(similarity_top_k=n_results)
        nodes = retriever.retrieve(question)
        return [node.text for node in nodes]
    except Exception:
        return []


def delete_client_vectors(client_id: int):
    try:
        _get_chroma().delete_collection(f"client_{client_id}")
    except Exception:
        pass


def rebuild_client_index(client_id: int):
    """Re-index all entries for a client from SQLite. Called by weekly scheduler."""
    try:
        from database import get_data_entries, get_client
        client = get_client(client_id)
        if not client:
            return
        delete_client_vectors(client_id)
        entries = get_data_entries(client_id)
        for entry in entries:
            add_to_vector_store(
                client_id=client_id,
                client_name=client["name"],
                source_type=entry["source_type"],
                content=entry["content"],
                entry_id=entry["id"],
            )
    except Exception:
        pass


def init_vector_store():
    _get_chroma()


def is_vector_ready() -> bool:
    try:
        _get_chroma()
        return True
    except Exception:
        return False
```

- [ ] **Step 4: Run tests — verify pass**

```bash
python -m pytest tests/test_vector_store.py -v
```

Expected: all 3 tests PASS. (May take 30-60s first run — model loads.)

- [ ] **Step 5: Commit**

```bash
git add vector_store.py tests/test_vector_store.py
git commit -m "feat: replace vector store with LlamaIndex per-client ChromaDB collections"
```

---

## Task 4: Risk Engine — Two-Layer Detection

**Files:**
- Create: `risk_engine.py`
- Create: `tests/test_risk_engine.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_risk_engine.py`:

```python
from datetime import date, timedelta
import pytest

def _client(deadline_offset_days=None, last_updated_offset_days=0, risk_flag=False):
    """Helper: build a mock client dict."""
    deadline = None
    if deadline_offset_days is not None:
        deadline = (date.today() + timedelta(days=deadline_offset_days)).isoformat()
    last_updated = (date.today() - timedelta(days=last_updated_offset_days)).isoformat()
    return {
        "id": 1, "name": "Test", "case_type": "O-1A",
        "deadline": deadline, "last_updated": last_updated,
        "risk_flag": risk_flag,
    }

def test_deadline_within_14_days_no_activity_is_at_risk():
    from risk_engine import rule_based_risk
    client = _client(deadline_offset_days=10, last_updated_offset_days=8)
    assert rule_based_risk(client) == "at_risk"

def test_deadline_within_30_days_stale_is_watch():
    from risk_engine import rule_based_risk
    client = _client(deadline_offset_days=25, last_updated_offset_days=15)
    assert rule_based_risk(client) == "watch"

def test_deadline_far_out_is_safe():
    from risk_engine import rule_based_risk
    client = _client(deadline_offset_days=90, last_updated_offset_days=1)
    assert rule_based_risk(client) == "safe"

def test_no_deadline_is_safe():
    from risk_engine import rule_based_risk
    client = _client(deadline_offset_days=None)
    assert rule_based_risk(client) == "safe"

def test_risk_flag_true_is_at_risk():
    from risk_engine import rule_based_risk
    client = _client(deadline_offset_days=90, risk_flag=True)
    assert rule_based_risk(client) == "at_risk"

def test_deadline_within_14_recent_activity_is_watch_not_at_risk():
    from risk_engine import rule_based_risk
    # Deadline in 10 days but PM was active yesterday → watch, not at_risk
    client = _client(deadline_offset_days=10, last_updated_offset_days=1)
    assert rule_based_risk(client) == "watch"

def test_keyword_in_content_triggers_at_risk():
    from risk_engine import content_has_risk_keyword
    assert content_has_risk_keyword("Client received an RFE last week") is True
    assert content_has_risk_keyword("Everything is on track") is False
```

- [ ] **Step 2: Run — verify fails**

```bash
python -m pytest tests/test_risk_engine.py -v
```

Expected: FAIL — `risk_engine` module doesn't exist.

- [ ] **Step 3: Create risk_engine.py**

```python
"""
Two-layer risk detection.
Layer 1: rule engine (always runs, fast).
Layer 2: AI risk_level field in ClientStatus (runs on query via Instructor).
"""
from datetime import date, datetime

_RISK_KEYWORDS = {
    "overdue", "expired", "urgent", "missed deadline",
    "rfe", "denial", "no response", "rejected",
}


def content_has_risk_keyword(content: str) -> bool:
    low = content.lower()
    return any(kw in low for kw in _RISK_KEYWORDS)


def rule_based_risk(client: dict) -> str:
    """Returns 'safe', 'watch', or 'at_risk'. Pure function — no DB writes."""
    if client.get("risk_flag"):
        return "at_risk"

    deadline_str = client.get("deadline")
    last_updated_str = client.get("last_updated")

    if not deadline_str:
        return "safe"

    try:
        deadline = date.fromisoformat(deadline_str[:10])
        today = date.today()
        days_to_deadline = (deadline - today).days

        days_since_activity = 999
        if last_updated_str:
            last_updated = datetime.fromisoformat(last_updated_str).date()
            days_since_activity = (today - last_updated).days

        if days_to_deadline <= 0:
            return "at_risk"
        if days_to_deadline <= 14 and days_since_activity >= 7:
            return "at_risk"
        if days_to_deadline <= 14:
            return "watch"
        if days_to_deadline <= 30 and days_since_activity >= 14:
            return "watch"
    except (ValueError, TypeError):
        pass

    return "safe"


def scan_all_clients_risk() -> list[int]:
    """
    Daily scheduler job: scan all clients, flag newly at-risk ones.
    Returns list of client_ids that were newly flagged.
    """
    from database import get_all_clients, update_client
    clients = get_all_clients()
    newly_flagged = []
    for client in clients:
        level = rule_based_risk(client)
        if level == "at_risk" and not client.get("risk_flag"):
            update_client(client["id"], risk_flag=True)
            newly_flagged.append(client["id"])
    return newly_flagged


def flag_if_keyword(client_id: int, content: str) -> bool:
    """Called on every feed action. Flags client if risk keyword found."""
    if content_has_risk_keyword(content):
        from database import update_client
        update_client(client_id, risk_flag=True)
        return True
    return False
```

- [ ] **Step 4: Run tests — verify pass**

```bash
python -m pytest tests/test_risk_engine.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Update main.py to use risk_engine instead of inline function**

In `main.py`, remove `_RISK_KEYWORDS` and `_flag_risk_if_keywords`, add import:

```python
from risk_engine import flag_if_keyword
```

Replace all calls `_flag_risk_if_keywords(client_id, content)` with `flag_if_keyword(client_id, content)`.

- [ ] **Step 6: Verify server still starts**

```bash
python3 main.py &
sleep 3 && curl -s http://localhost:8000/ | head -c 50
kill %1
```

Expected: returns HTML start of the frontend.

- [ ] **Step 7: Commit**

```bash
git add risk_engine.py tests/test_risk_engine.py main.py
git commit -m "feat: two-layer risk engine, replace inline keyword check in main.py"
```

---

## Task 5: AI Engine — LiteLLM + Instructor + ClientStatus

**Files:**
- Modify: `ai_engine.py` (full rewrite)
- Create: `tests/test_ai_engine.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_ai_engine.py`:

```python
import pytest
from unittest.mock import patch, MagicMock

def test_query_returns_client_status_shape():
    """AI response must always have ClientStatus fields."""
    from ai_engine import ClientStatus
    status = ClientStatus(
        current_status="Active",
        pending_items=["recommendation letter", "I-94 copy"],
        completed_items=["biometrics done"],
        next_deadline="2026-06-01",
        risk_level="watch",
        immediate_action_items=["Follow up Dr. Williams by Friday"],
        key_context="RFE received on April 10, response due June 1.",
    )
    assert status.risk_level in ("safe", "watch", "at_risk")
    assert isinstance(status.pending_items, list)
    assert isinstance(status.completed_items, list)
    assert isinstance(status.immediate_action_items, list)

def test_build_messages_includes_client_name():
    from ai_engine import _build_messages
    client = {"name": "Arjun Mehta", "case_type": "O-1A", "deadline": "2026-06-01",
              "assigned_pm": "Tulsi", "status": "Active", "risk_flag": False, "notes": ""}
    msgs = _build_messages(client, ["WhatsApp chunk about Arjun"], "What is pending?")
    joined = " ".join(m["content"] for m in msgs)
    assert "Arjun Mehta" in joined
    assert "What is pending?" in joined

def test_client_status_risk_level_literal():
    from ai_engine import ClientStatus
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ClientStatus(
            current_status="ok",
            pending_items=[],
            completed_items=[],
            next_deadline="none",
            risk_level="unknown",  # invalid literal
            immediate_action_items=[],
            key_context="",
        )
```

- [ ] **Step 2: Run — verify partial fail**

```bash
python -m pytest tests/test_ai_engine.py -v
```

Expected: `test_query_returns_client_status_shape` and `test_client_status_risk_level_literal` FAIL — `ClientStatus` not in `ai_engine`.

- [ ] **Step 3: Rewrite ai_engine.py**

Replace entire `ai_engine.py` with:

```python
import os
import re
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

import litellm
import instructor
from pydantic import BaseModel
from typing import Literal

from database import get_client, get_data_entries, search_entries_fts
from vector_store import query_client as vector_query, is_vector_ready

litellm.set_verbose = False


class ClientStatus(BaseModel):
    current_status: str
    pending_items: list[str]
    completed_items: list[str]
    next_deadline: str
    risk_level: Literal["safe", "watch", "at_risk"]
    immediate_action_items: list[str]
    key_context: str


_instructor_client = instructor.from_litellm(litellm.completion)

SYSTEM_PROMPT = """You are an AI assistant for JineeGreenCard, an immigration consulting company.
You have the client's full conversation history — WhatsApp, Fathom calls, emails, case notes.

RULES:
- Always return structured JSON matching the ClientStatus schema exactly.
- pending_items: list of things NOT yet done.
- completed_items: list of things already done.
- next_deadline: the most important upcoming deadline as a date string or 'Not set'.
- risk_level: 'at_risk' if urgent/overdue/RFE/denial, 'watch' if deadline within 30 days or stale, 'safe' otherwise.
- immediate_action_items: 1-3 concrete next actions the PM should take NOW.
- key_context: direct answer to the specific question asked. 2-5 sentences max.
- current_status: one sentence summary of overall case status."""


def _get_context_chunks(client_id: int, question: str, max_chars: int = 6000) -> list[str]:
    """Hybrid retrieval: vector search first, FTS5 keyword second, SQLite fallback."""
    chunks = []

    # 1. Vector search
    if is_vector_ready():
        chunks = vector_query(client_id, question, n_results=5)

    # 2. FTS5 keyword boost — add any keyword hits not already in chunks
    if question.strip():
        fts_hits = search_entries_fts(client_id, question)
        for hit in fts_hits:
            if hit not in chunks:
                chunks.append(hit)
                if len(chunks) >= 8:
                    break

    # 3. SQLite fallback — always fill if chunks still empty
    if not chunks:
        entries = get_data_entries(client_id)
        total = 0
        for entry in entries:
            content = entry.get("content", "")
            source = entry.get("source_type", "data")
            created = entry.get("created_at", "")[:10]
            chunk = f"[{source.upper()} — {created}]\n{content[:1500]}"
            if total + len(chunk) > max_chars:
                break
            chunks.append(chunk)
            total += len(chunk)

    return chunks


def _build_messages(client: dict, chunks: list[str], question: str) -> list[dict]:
    context_str = (
        "=== CLIENT CONVERSATION HISTORY ===\n" + "\n\n".join(chunks)
        if chunks
        else "No conversation data has been added for this client yet."
    )
    user_content = f"""CLIENT PROFILE:
Name: {client['name']}
Case Type: {client['case_type']}
Deadline: {client.get('deadline') or 'Not set'}
Assigned PM: {client.get('assigned_pm') or 'Unassigned'}
Status: {client.get('status', 'Active')}
Risk Flag: {'YES — AT RISK' if client.get('risk_flag') else 'No'}
Notes: {client.get('notes') or 'None'}

{context_str}

QUESTION: {question}"""

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _call_structured(messages: list[dict], model: str) -> ClientStatus:
    return _instructor_client.chat.completions.create(
        model=model,
        messages=messages,
        response_model=ClientStatus,
        max_retries=2,
    )


def query_client_ai(client_id: int, question: str, pm_username: str = None) -> dict:
    client = get_client(client_id)
    if not client:
        return {"status": None, "model_used": "none", "error": True,
                "error_message": "Client not found."}

    question = question.strip()[:500]
    chunks = _get_context_chunks(client_id, question)

    # Prepend Mem0 PM context if available
    if pm_username:
        try:
            from memory_engine import get_pm_context
            pm_ctx = get_pm_context(pm_username, question)
            if pm_ctx:
                chunks = [pm_ctx] + chunks
        except Exception:
            pass

    messages = _build_messages(client, chunks, question)

    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

    for model, key_env in [
        ("groq/llama-3.3-70b-versatile", groq_key),
        ("gemini/gemini-2.5-flash", gemini_key),
    ]:
        if not key_env:
            continue
        try:
            os.environ["GROQ_API_KEY"] = groq_key
            os.environ["GEMINI_API_KEY"] = gemini_key
            status = _call_structured(messages, model)

            # Store PM interaction in Mem0 after successful query
            if pm_username:
                try:
                    from memory_engine import add_pm_memory
                    add_pm_memory(pm_username, question, status.key_context)
                except Exception:
                    pass

            return {"status": status.model_dump(), "model_used": model, "error": False}
        except Exception:
            continue

    return {
        "status": None, "model_used": "none", "error": True,
        "error_message": "AI unavailable. Check GROQ_API_KEY or GEMINI_API_KEY in .env",
    }


def generate_summary(client_id: int, pm_username: str = None) -> dict:
    return query_client_ai(
        client_id,
        "Give me a complete status summary: what is done, what is pending, risks, deadlines, next actions.",
        pm_username=pm_username,
    )


def parse_clients_from_text(text: str, default_pm: str) -> list:
    """Use Groq to extract client records from raw document text."""
    import json
    prompt = f"""Extract ALL client/case records from the document below.
Return a JSON array. Each object must have:
- name (string, required)
- case_type (string: O-1A, EB-1A, H-1B, etc. Use "Unknown" if missing)
- deadline (YYYY-MM-DD string or null)
- status (one of: "Active", "At Risk", "On Hold", "Completed")
- risk_flag (boolean)
- notes (string, one sentence or "")

Return ONLY valid JSON array. No markdown. No explanation.

DOCUMENT:
{text[:12000]}"""

    messages = [
        {"role": "system", "content": "Extract structured client data. Return only valid JSON arrays."},
        {"role": "user", "content": prompt},
    ]

    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if not groq_key:
        return []

    try:
        resp = litellm.completion(
            model="groq/llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=2000,
            temperature=0.1,
        )
        raw = resp.choices[0].message.content
        raw = re.sub(r"```(?:json)?", "", raw).strip().strip("`").strip()
        clients = json.loads(raw)
        if not isinstance(clients, list):
            return []
        clean = []
        for c in clients:
            if not isinstance(c, dict) or not c.get("name", "").strip():
                continue
            clean.append({
                "name": str(c.get("name", "")).strip()[:200],
                "case_type": str(c.get("case_type", "Unknown")).strip()[:50],
                "deadline": c.get("deadline") or None,
                "status": c.get("status", "Active") if c.get("status") in
                          ("Active", "At Risk", "On Hold", "Completed") else "Active",
                "risk_flag": bool(c.get("risk_flag", False)),
                "notes": str(c.get("notes", "")).strip()[:500],
                "assigned_pm": default_pm,
            })
        return clean
    except Exception:
        return []
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_ai_engine.py -v
```

Expected: all 3 PASS.

- [ ] **Step 5: Update /api/clients/{id}/query route in main.py to pass pm_username**

Find the query route in `main.py` (search for `query_client_ai`). Update to:

```python
@app.post("/api/clients/{client_id}/query")
async def query_client(client_id: int, body: QueryRequest, authorization: Optional[str] = Header(None)):
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    user = get_user_from_token(token)
    if not user:
        raise HTTPException(401, "Not authenticated")
    _check_client_access(client_id, user)
    result = query_client_ai(client_id, body.question, pm_username=user["username"])
    log_audit(user["id"], "ai_query", "client", client_id, body.question[:100])
    return result
```

Also add `log_audit` to imports at top of `main.py`:
```python
from database import (..., log_audit)
```

- [ ] **Step 6: Verify server starts and /query returns structured data**

```bash
# Start server
python3 main.py &
sleep 4

# Get a token first (replace with real credentials from your DB)
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))")

# Query a client (use client_id=1)
curl -s -X POST http://localhost:8000/api/clients/1/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"question":"What is pending for this client?"}' | python3 -m json.tool

kill %1
```

Expected: JSON with `status.pending_items`, `status.risk_level`, etc. — NOT freeform text.

- [ ] **Step 7: Commit**

```bash
git add ai_engine.py tests/test_ai_engine.py main.py
git commit -m "feat: LiteLLM + Instructor structured ClientStatus output, hybrid retrieval"
```

---

## Task 6: Parsers — MarkItDown + spaCy + dateparser

**Files:**
- Modify: `parsers.py`
- Create: `tests/test_parsers.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_parsers.py`:

```python
def test_whatsapp_parser_extracts_messages():
    from parsers import parse_whatsapp_txt
    sample = """[1/15/24, 10:30] Tulsi: Client submitted I-140 today
[1/15/24, 10:31] Arjun: Thank you for the update
[1/15/24, 10:32] Tulsi: Next step is medical exam
Messages and calls are end-to-end encrypted"""
    result = parse_whatsapp_txt(sample, "Arjun Mehta")
    assert "I-140" in result
    assert "end-to-end encrypted" not in result

def test_extract_dates_finds_dates_in_text():
    from parsers import extract_dates_from_text
    text = "The deadline is June 15th, 2026. Meeting scheduled for April 22, 2026."
    dates = extract_dates_from_text(text)
    assert len(dates) >= 1
    assert any("2026" in d for d in dates)

def test_extract_dates_returns_list_on_empty():
    from parsers import extract_dates_from_text
    assert extract_dates_from_text("") == []
```

- [ ] **Step 2: Run — verify fails**

```bash
python -m pytest tests/test_parsers.py -v
```

Expected: `test_extract_dates_*` FAIL — `extract_dates_from_text` not defined.

- [ ] **Step 3: Upgrade parsers.py**

Add these imports at the top of `parsers.py`:

```python
import spacy

_nlp = None

def _get_nlp():
    global _nlp
    if _nlp is None:
        try:
            _nlp = spacy.load("en_core_web_sm")
        except OSError:
            _nlp = False
    return _nlp
```

Add this function to `parsers.py`:

```python
def extract_dates_from_text(text: str) -> list[str]:
    """Extract date/time entities from text using spaCy."""
    if not text.strip():
        return []
    nlp = _get_nlp()
    if not nlp:
        return []
    try:
        doc = nlp(text[:50000])
        return [ent.text for ent in doc.ents if ent.label_ in ("DATE", "TIME")]
    except Exception:
        return []
```

Replace the `extract_text_from_file` function in `parsers.py`:

```python
def extract_text_from_file(filename: str, file_bytes: bytes) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext == "pdf":
        # Try MarkItDown first (better for LLM consumption), fall back to pdfplumber
        try:
            import io
            from markitdown import MarkItDown
            md = MarkItDown()
            result = md.convert_stream(io.BytesIO(file_bytes), file_extension=".pdf")
            text = result.text_content
            if text and len(text.strip()) > 100:
                return text[:40000]
        except Exception:
            pass
        # pdfplumber fallback
        import io
        import pdfplumber
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n".join(pages)[:40000]
    elif ext in ("docx", "doc"):
        import io
        from docx import Document
        doc = Document(io.BytesIO(file_bytes))
        lines = [p.text for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                lines.append(" | ".join(c.text.strip() for c in row.cells if c.text.strip()))
        return "\n".join(lines)[:40000]
    elif ext == "txt":
        return file_bytes.decode("utf-8", errors="replace")[:40000]
    else:
        raise ValueError(f"Unsupported file type: .{ext}")
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_parsers.py -v
```

Expected: all 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add parsers.py tests/test_parsers.py
git commit -m "feat: MarkItDown PDF extraction, spaCy date extractor"
```

---

## Task 7: Memory Engine — Mem0 Self-Hosted

**Files:**
- Create: `memory_engine.py`

- [ ] **Step 1: Create memory_engine.py**

```python
"""
Mem0 self-hosted PM memory.
Uses local ChromaDB for vector storage, Groq for memory extraction.
No external API key beyond Groq (already required).
"""
import os

_mem = None


def _get_mem():
    global _mem
    if _mem is not None:
        return _mem
    try:
        from mem0 import Memory
        config = {
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "pm_memory",
                    "path": "./mem0_db",
                },
            },
            "llm": {
                "provider": "groq",
                "config": {
                    "model": "llama-3.3-70b-versatile",
                    "api_key": os.getenv("GROQ_API_KEY", ""),
                },
            },
            "embedder": {
                "provider": "huggingface",
                "config": {"model": "all-MiniLM-L6-v2"},
            },
        }
        _mem = Memory.from_config(config)
    except Exception:
        _mem = False
    return _mem


def add_pm_memory(pm_username: str, query: str, response: str):
    """Store PM query + AI response as a memory fact."""
    mem = _get_mem()
    if not mem:
        return
    try:
        mem.add(
            messages=[
                {"role": "user", "content": query},
                {"role": "assistant", "content": response},
            ],
            user_id=pm_username,
        )
    except Exception:
        pass


def get_pm_context(pm_username: str, query: str) -> str:
    """Retrieve relevant past memories for this PM. Returns formatted string or ''."""
    mem = _get_mem()
    if not mem:
        return ""
    try:
        results = mem.search(query=query, user_id=pm_username, limit=5)
        if not results:
            return ""
        lines = [f"- {r['memory']}" for r in results]
        return "PM Past Context (from previous sessions):\n" + "\n".join(lines)
    except Exception:
        return ""
```

- [ ] **Step 2: Verify import works**

```bash
python3 -c "from memory_engine import add_pm_memory, get_pm_context; print('Mem0 engine OK')"
```

Expected: `Mem0 engine OK` (even if Mem0 fails to init — the functions handle it gracefully).

- [ ] **Step 3: Commit**

```bash
git add memory_engine.py
git commit -m "feat: Mem0 self-hosted PM memory engine"
```

---

## Task 8: Scheduler — APScheduler Jobs

**Files:**
- Create: `scheduler.py`

- [ ] **Step 1: Create scheduler.py**

```python
"""
APScheduler jobs running inside FastAPI's lifespan.
All times in IST (Asia/Kolkata).
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

IST = pytz.timezone("Asia/Kolkata")
_scheduler = AsyncIOScheduler(timezone=IST)


async def _daily_risk_scan():
    """8AM IST: scan all clients for new at-risk conditions."""
    try:
        from risk_engine import scan_all_clients_risk
        flagged = scan_all_clients_risk()
        if flagged:
            print(f"[Scheduler] Daily risk scan: flagged {len(flagged)} new at-risk clients: {flagged}")
    except Exception as e:
        print(f"[Scheduler] Risk scan error: {e}")


async def _morning_digest():
    """9AM IST: generate per-PM digest of priority clients."""
    try:
        from database import get_all_clients, store_digest
        from risk_engine import rule_based_risk
        clients = get_all_clients()
        pm_digests: dict[str, list] = {}
        for client in clients:
            level = rule_based_risk(client)
            if level in ("at_risk", "watch"):
                pm = client.get("assigned_pm") or "unassigned"
                pm_digests.setdefault(pm, []).append((client, level))
        for pm_name, items in pm_digests.items():
            lines = [f"Today's Focus — {len(items)} priority client(s):"]
            for client, level in sorted(items, key=lambda x: x[1] == "at_risk", reverse=True):
                lines.append(f"• {client['name']} ({client['case_type']}) — {level.upper()}"
                             f" | Deadline: {client.get('deadline') or 'Not set'}")
            store_digest(pm_name, "\n".join(lines))
        print(f"[Scheduler] Morning digest generated for {len(pm_digests)} PMs.")
    except Exception as e:
        print(f"[Scheduler] Digest error: {e}")


async def _weekly_reindex():
    """Sunday midnight IST: rebuild all ChromaDB collections from SQLite."""
    try:
        from database import get_all_clients
        from vector_store import rebuild_client_index
        clients = get_all_clients()
        for client in clients:
            rebuild_client_index(client["id"])
        print(f"[Scheduler] Weekly re-index complete for {len(clients)} clients.")
    except Exception as e:
        print(f"[Scheduler] Re-index error: {e}")


def start_scheduler():
    _scheduler.add_job(_daily_risk_scan, CronTrigger(hour=8, minute=0, timezone=IST), id="daily_risk")
    _scheduler.add_job(_morning_digest, CronTrigger(hour=9, minute=0, timezone=IST), id="morning_digest")
    _scheduler.add_job(_weekly_reindex, CronTrigger(day_of_week="sun", hour=0, minute=0, timezone=IST), id="weekly_reindex")
    _scheduler.start()
    print("✅ Scheduler started — daily risk scan 8AM IST, digest 9AM IST, re-index Sunday midnight IST")


def stop_scheduler():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
```

- [ ] **Step 2: Wire into main.py lifespan**

At the top of `main.py`, replace `app = FastAPI(...)` with:

```python
from contextlib import asynccontextmanager
from scheduler import start_scheduler, stop_scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()

app = FastAPI(title="JineeGreenCard Client 360", version="2.0.0", lifespan=lifespan)
```

- [ ] **Step 3: Verify server starts with scheduler**

```bash
python3 main.py &
sleep 4
cat /tmp/jinee_server.log | grep -i scheduler
kill %1
```

Expected output contains: `✅ Scheduler started — daily risk scan 8AM IST...`

- [ ] **Step 4: Commit**

```bash
git add scheduler.py main.py
git commit -m "feat: APScheduler daily risk scan, morning digest, weekly re-index"
```

---

## Task 9: Admin Routes in main.py

**Files:**
- Modify: `main.py` — add `/api/admin/*` routes

- [ ] **Step 1: Add admin helper and routes to main.py**

Add this helper after the existing `_check_client_access` function:

```python
def _require_admin(user: dict):
    if not user or user.get("role") != "admin":
        raise HTTPException(403, "Admin access required")
```

Add these routes at the end of `main.py` before `if __name__ == "__main__"`:

```python
# ─── Admin Routes ─────────────────────────────────────────────────────────────

@app.get("/api/admin/clients")
async def admin_all_clients(
    pm: Optional[str] = None,
    risk: Optional[str] = None,
    case_type: Optional[str] = None,
    search: Optional[str] = None,
    authorization: Optional[str] = Header(None),
):
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    user = get_user_from_token(token)
    _require_admin(user)

    clients = get_all_clients()

    if pm:
        clients = [c for c in clients if c.get("assigned_pm") == pm]
    if risk == "at_risk":
        clients = [c for c in clients if c.get("risk_flag")]
    elif risk == "safe":
        clients = [c for c in clients if not c.get("risk_flag")]
    if case_type:
        clients = [c for c in clients if c.get("case_type", "").lower() == case_type.lower()]
    if search:
        s = search.lower()
        clients = [c for c in clients if s in c.get("name", "").lower()]

    # Enrich with rule-based risk level
    from risk_engine import rule_based_risk
    for c in clients:
        c["risk_level"] = rule_based_risk(c)

    return {"clients": clients, "total": len(clients)}


@app.get("/api/admin/audit")
async def admin_audit_log(limit: int = 100, authorization: Optional[str] = Header(None)):
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    user = get_user_from_token(token)
    _require_admin(user)
    from database import get_audit_log
    return {"entries": get_audit_log(limit=min(limit, 500))}


@app.get("/api/admin/pm-summary")
async def admin_pm_summary(authorization: Optional[str] = Header(None)):
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    user = get_user_from_token(token)
    _require_admin(user)
    from database import get_pm_activity_summary
    return {"summary": get_pm_activity_summary()}


@app.get("/api/clients/{client_id}/digest")
async def get_digest(client_id: int, authorization: Optional[str] = Header(None)):
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    user = get_user_from_token(token)
    if not user:
        raise HTTPException(401, "Not authenticated")
    client = _check_client_access(client_id, user)
    from database import get_latest_digest
    digest = get_latest_digest(client.get("assigned_pm", ""))
    return {"digest": digest}
```

Also add `log_audit` calls to existing data feed routes. In the `fathom` branch of `feed_data`:

```python
log_audit(user["id"], "feed_fathom", "client", client_id, url[:100])
```

In the `whatsapp` branch:
```python
log_audit(user["id"], "feed_whatsapp", "client", client_id, f"{len(parsed)} chars")
```

In the `email/note` branch:
```python
log_audit(user["id"], "feed_note", "client", client_id, actual_type)
```

- [ ] **Step 2: Verify admin routes work**

```bash
python3 main.py &
sleep 4

TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))")

curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/admin/clients" | python3 -m json.tool | head -30

kill %1
```

Expected: JSON with `clients` array and `total` count.

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: admin routes for clients, audit log, PM summary, digest endpoint"
```

---

## Task 10: Frontend — Structured AI Output + Admin View + Digest Panel

**Files:**
- Modify: `frontend/index.html`

This task has the most UI changes. Make them in sub-sections.

### 10a — Render ClientStatus structured cards

- [ ] **Step 1: Replace `askAI` function and add CSS for structured output**

Find `#ai-answer-content` CSS in `index.html` and add after it:

```css
.ai-status-card { background: #f8fafc; border: 1px solid var(--border); border-radius: 10px; padding: 16px; margin-top: 14px; }
.ai-status-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.ai-risk-badge { padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }
.risk-safe { background: #dcfce7; color: #166534; }
.risk-watch { background: #fef9c3; color: #854d0e; }
.risk-at_risk { background: #fee2e2; color: #991b1b; }
.ai-section-label { font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin: 10px 0 4px; }
.ai-item-list { list-style: none; padding: 0; margin: 0; }
.ai-item-list li { font-size: 13px; padding: 3px 0; color: var(--text); }
.ai-item-list li::before { content: "• "; color: var(--primary); }
.ai-key-context { font-size: 13px; line-height: 1.6; color: var(--text); background: #fff; border-left: 3px solid var(--primary); padding: 8px 12px; border-radius: 0 6px 6px 0; margin-top: 8px; }
.ai-action-item { background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 6px; padding: 6px 10px; margin: 4px 0; font-size: 13px; color: #1e40af; }
```

Replace the `askAI` function in `index.html`:

```javascript
function _renderClientStatus(status, modelUsed) {
  const riskClass = `risk-${status.risk_level}`;
  const riskLabel = { safe: '✅ Safe', watch: '⚠️ Watch', at_risk: '🔴 At Risk' }[status.risk_level] || status.risk_level;

  const pendingHtml = status.pending_items.length
    ? status.pending_items.map(i => `<li>${i}</li>`).join('')
    : '<li>None</li>';
  const completedHtml = status.completed_items.length
    ? status.completed_items.map(i => `<li>${i}</li>`).join('')
    : '<li>None</li>';
  const actionsHtml = status.immediate_action_items.length
    ? status.immediate_action_items.map(i => `<div class="ai-action-item">→ ${i}</div>`).join('')
    : '';

  return `<div class="ai-status-card">
    <div class="ai-status-header">
      <span style="font-weight:600;font-size:14px">${status.current_status}</span>
      <span class="ai-risk-badge ${riskClass}">${riskLabel}</span>
    </div>
    <div class="ai-key-context">${status.key_context}</div>
    ${actionsHtml ? `<div class="ai-section-label">Immediate Actions</div>${actionsHtml}` : ''}
    <div class="ai-section-label">Pending</div>
    <ul class="ai-item-list">${pendingHtml}</ul>
    <div class="ai-section-label">Completed</div>
    <ul class="ai-item-list">${completedHtml}</ul>
    <div class="ai-section-label">Next Deadline</div>
    <div style="font-size:13px;padding:4px 0">${status.next_deadline}</div>
    <div style="font-size:11px;color:var(--text-muted);margin-top:8px">Answered by ${modelUsed}</div>
  </div>`;
}

async function askAI() {
  const q = document.getElementById('ai-question-input').value.trim();
  if (!q || !currentClientId) return;

  const btn = document.getElementById('ask-btn');
  const box = document.getElementById('ai-answer-box');
  const content = document.getElementById('ai-answer-content');
  const meta = document.getElementById('ai-answer-meta');

  btn.disabled = true;
  btn.textContent = 'Thinking...';
  box.style.display = 'block';
  content.innerHTML = '<span class="thinking-dots">Thinking</span>';
  meta.textContent = '';

  try {
    const res = await fetch(API + `/api/clients/${currentClientId}/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ question: q }),
    });
    const data = await res.json();
    if (data.error) {
      content.innerHTML = `<div style="color:#dc2626;padding:12px">${data.error_message || 'AI unavailable.'}</div>`;
    } else if (data.status) {
      content.innerHTML = _renderClientStatus(data.status, data.model_used);
    } else {
      content.textContent = 'No response received.';
    }
    meta.textContent = '';
  } catch(e) {
    content.textContent = 'Error connecting to AI. Is the server running?';
  } finally {
    btn.disabled = false;
    btn.textContent = 'Ask AI';
  }
}
```

### 10b — Admin View

- [ ] **Step 2: Add admin nav tab and panel in index.html**

Find the main nav or sidebar area and add an admin tab (only visible when `currentUser.role === 'admin'`). Add after the existing sidebar content:

```html
<!-- Admin panel — hidden by default, shown for admin role -->
<div id="admin-panel" style="display:none; padding: 16px;">
  <div style="font-weight:700; font-size:15px; margin-bottom:12px">Admin — All Clients</div>

  <!-- Filters -->
  <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px">
    <input type="text" id="admin-search" placeholder="Search client..." oninput="adminLoadClients()"
      style="flex:1;min-width:120px;padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px">
    <select id="admin-filter-risk" onchange="adminLoadClients()"
      style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px">
      <option value="">All Risk</option>
      <option value="at_risk">At Risk</option>
      <option value="safe">Safe</option>
    </select>
    <select id="admin-filter-pm" onchange="adminLoadClients()"
      style="padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:13px">
      <option value="">All PMs</option>
    </select>
  </div>

  <!-- Table -->
  <div id="admin-clients-table" style="overflow-x:auto"></div>

  <!-- PM Summary -->
  <div style="font-weight:700;font-size:14px;margin:20px 0 8px">PM Activity (Last 7 Days)</div>
  <div id="admin-pm-summary"></div>
</div>
```

Add a button to show admin panel (in the header or nav area, conditionally rendered):

```html
<button id="admin-btn" onclick="toggleAdminPanel()" style="display:none;padding:6px 14px;border:1px solid var(--border);border-radius:6px;font-size:13px;cursor:pointer;background:#f8fafc">
  Admin View
</button>
```

### 10c — Admin JS

- [ ] **Step 3: Add admin JavaScript functions**

Add to the script section of `index.html`:

```javascript
function toggleAdminPanel() {
  const panel = document.getElementById('admin-panel');
  const main = document.getElementById('main-content'); // or whatever the main panel id is
  const isShowing = panel.style.display !== 'none';
  panel.style.display = isShowing ? 'none' : 'block';
  if (!isShowing) adminLoadClients();
}

async function adminLoadClients() {
  const search = document.getElementById('admin-search')?.value || '';
  const risk = document.getElementById('admin-filter-risk')?.value || '';
  const pm = document.getElementById('admin-filter-pm')?.value || '';
  const params = new URLSearchParams();
  if (search) params.set('search', search);
  if (risk) params.set('risk', risk);
  if (pm) params.set('pm', pm);

  try {
    const res = await fetch(`${API}/api/admin/clients?${params}`, { headers: authHeaders() });
    const data = await res.json();
    renderAdminTable(data.clients || []);
  } catch(e) {
    document.getElementById('admin-clients-table').innerHTML = '<div style="color:#dc2626">Failed to load admin data.</div>';
  }
}

function renderAdminTable(clients) {
  const riskColor = { at_risk: '#fee2e2', watch: '#fef9c3', safe: '#dcfce7' };
  const riskLabel = { at_risk: '🔴 At Risk', watch: '⚠️ Watch', safe: '✅ Safe' };
  const rows = clients.map(c => `
    <tr style="cursor:pointer;background:${c.risk_flag ? '#fff7f7' : '#fff'}" onclick="selectClientFromAdmin(${c.id})">
      <td style="padding:8px 10px;font-weight:500">${c.name}</td>
      <td style="padding:8px 10px">${c.case_type}</td>
      <td style="padding:8px 10px">${c.assigned_pm || '—'}</td>
      <td style="padding:8px 10px">${c.deadline || '—'}</td>
      <td style="padding:8px 10px">${c.status}</td>
      <td style="padding:8px 10px">
        <span style="padding:3px 8px;border-radius:10px;font-size:11px;font-weight:600;background:${riskColor[c.risk_level]||'#f3f4f6'}">
          ${riskLabel[c.risk_level] || c.risk_level}
        </span>
      </td>
      <td style="padding:8px 10px;font-size:12px;color:#6b7280">${(c.last_updated||'').slice(0,10)}</td>
    </tr>`).join('');

  document.getElementById('admin-clients-table').innerHTML = `
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead>
        <tr style="background:#f8fafc;font-size:11px;font-weight:700;color:#6b7280;text-transform:uppercase">
          <th style="padding:8px 10px;text-align:left">Client</th>
          <th style="padding:8px 10px;text-align:left">Case</th>
          <th style="padding:8px 10px;text-align:left">PM</th>
          <th style="padding:8px 10px;text-align:left">Deadline</th>
          <th style="padding:8px 10px;text-align:left">Status</th>
          <th style="padding:8px 10px;text-align:left">Risk</th>
          <th style="padding:8px 10px;text-align:left">Updated</th>
        </tr>
      </thead>
      <tbody>${rows || '<tr><td colspan="7" style="padding:20px;text-align:center;color:#9ca3af">No clients found</td></tr>'}</tbody>
    </table>`;
}

async function selectClientFromAdmin(clientId) {
  // Reuse existing selectClient function
  await selectClient(clientId);
  toggleAdminPanel();
}

async function adminLoadPMSummary() {
  try {
    const res = await fetch(`${API}/api/admin/pm-summary`, { headers: authHeaders() });
    const data = await res.json();
    const rows = (data.summary || []).map(pm => `
      <div style="display:flex;justify-content:space-between;padding:8px 12px;border:1px solid var(--border);border-radius:6px;margin-bottom:6px;font-size:13px">
        <span style="font-weight:500">${pm.assigned_pm}</span>
        <span>${pm.clients_updated} clients updated</span>
        <span style="color:#dc2626">${pm.at_risk_count} at risk</span>
      </div>`).join('');
    document.getElementById('admin-pm-summary').innerHTML = rows || '<div style="color:#9ca3af;font-size:13px">No data yet.</div>';
  } catch(e) {}
}
```

### 10d — Digest Panel + Admin Button Visibility

- [ ] **Step 4: Show admin button after login, load digest**

Find the function that runs after login (likely `loadDashboard` or `afterLogin`). Add:

```javascript
// Show admin button only for admin role
if (currentUser && currentUser.role === 'admin') {
  document.getElementById('admin-btn').style.display = 'inline-block';
  adminLoadPMSummary();
}
```

Add a digest display after client selection. Find `selectClient` and add after it loads the client:

```javascript
// Load morning digest for this PM
try {
  const dRes = await fetch(`${API}/api/clients/${clientId}/digest`, { headers: authHeaders() });
  const dData = await dRes.json();
  if (dData.digest && dData.digest.digest_text) {
    const digestEl = document.getElementById('digest-banner');
    if (digestEl) {
      digestEl.textContent = dData.digest.digest_text;
      digestEl.style.display = 'block';
    }
  }
} catch(e) {}
```

Add the digest banner HTML near the top of the main dashboard area (before the AI query box):

```html
<div id="digest-banner" style="display:none;background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:10px 14px;font-size:12px;color:#1e40af;margin-bottom:12px;white-space:pre-line"></div>
```

- [ ] **Step 5: Hard-refresh browser and test full flow**

```bash
# Start server
python3 main.py &
sleep 4
# Open browser at http://localhost:8000
# 1. Login as PM → no admin button → select client → ask AI → verify structured cards render
# 2. Login as admin → admin button shows → click → see all clients table → filter by risk
# 3. Feed a Fathom transcript → check Data History entry appears
# 4. Check audit trail: GET /api/admin/audit with admin token
kill %1
```

- [ ] **Step 6: Commit**

```bash
git add frontend/index.html
git commit -m "feat: structured ClientStatus cards, admin view with filters, digest banner"
```

---

## Task 11: Security Audit + Final Checks

**Files:**
- Review: `main.py`, `database.py`, `ai_engine.py`, `vector_store.py`

- [ ] **Step 1: Verify no hardcoded API keys**

```bash
grep -rn "gsk_\|AIzaSy" . --include="*.py" --exclude-dir=venv
```

Expected: no matches.

- [ ] **Step 2: Verify all SQL is parameterized**

```bash
grep -n "f\".*SELECT\|f\".*INSERT\|f\".*UPDATE\|f\".*DELETE" database.py
```

Expected: no matches (all queries use `?` placeholders).

- [ ] **Step 3: Verify file upload restrictions**

```bash
grep -n "extension\|magic\|file_bytes\[:4\]" main.py | head -20
```

Expected: shows magic byte checks for PDF uploads, `.txt` restriction for WhatsApp.

- [ ] **Step 4: Verify cross-client isolation in vector store**

```bash
python -m pytest tests/test_vector_store.py::test_different_clients_isolated -v
```

Expected: PASS.

- [ ] **Step 5: Verify admin routes reject non-admin users**

```bash
python3 main.py &
sleep 4

# Get a PM token
PM_TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"pm1","password":"pm123"}' | python3 -c "import sys,json; print(json.load(sys.stdin).get('token','NO_TOKEN'))")

# Try admin route with PM token — should get 403
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $PM_TOKEN" \
  http://localhost:8000/api/admin/clients)
echo "Status: $STATUS"

kill %1
```

Expected: `Status: 403`

- [ ] **Step 6: Run full test suite**

```bash
python -m pytest tests/ -v --tb=short
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add .
git commit -m "chore: security audit pass — no hardcoded keys, parameterized SQL, cross-client isolation verified"
```

---

## Task 12: Update KRISHNA.MD

**Files:**
- Modify: `KRISHNA.MD`

- [ ] **Step 1: Replace KRISHNA.MD content**

Replace entire `KRISHNA.MD` with:

```markdown
# Krishna's Session Notes — Client 360 Engine v2

## Project: JineeGreenCard Client 360 Intelligence System

## Current Version: 2.0

## What's Done ✅

### Phase 1 (Original Build)
- FastAPI backend, SQLite DB, ChromaDB placeholder
- Auth: session tokens, pbkdf2 password hashing
- Basic WhatsApp parser, Fathom transcript fetcher (fixed May 4 2026)
- Single-file frontend (frontend/index.html)
- Groq primary + Gemini fallback
- Demo data seeder

### Phase 2 (This Upgrade)
- [x] LlamaIndex + per-client ChromaDB collections (client_{id})
  - 512-token chunks, 50-token overlap, all-MiniLM-L6-v2 embeddings
- [x] LiteLLM single-interface for Groq + Gemini
- [x] Instructor + ClientStatus — all AI responses are structured JSON
  - Fields: current_status, pending_items, completed_items, next_deadline, risk_level, immediate_action_items, key_context
- [x] Mem0 self-hosted PM memory (mem0_db/) — learns PM preferences cross-session
- [x] Hybrid retrieval: vector search → FTS5 keyword → SQLite fallback
- [x] MarkItDown PDF extraction (better than pdfplumber for LLM)
- [x] spaCy date extraction from all ingested content
- [x] Two-layer risk engine (rule_based_risk + AI risk_level field)
- [x] APScheduler: 8AM IST risk scan, 9AM IST digest, Sunday midnight re-index
- [x] Audit log (every feed + query logged with user_id, timestamp)
- [x] Admin routes: /api/admin/clients (filterable), /api/admin/audit, /api/admin/pm-summary
- [x] Admin frontend: full client table with filters, PM activity summary, click-to-open any client
- [x] Morning digest banner on PM dashboard
- [x] Frontend renders ClientStatus cards (not freeform text)

## Port
Port 8000 → http://localhost:8000

## Architecture
```
main.py          — FastAPI, all API routes, lifespan (scheduler)
ai_engine.py     — LiteLLM + Instructor + ClientStatus, hybrid retrieval
vector_store.py  — LlamaIndex + ChromaDB per-client collections
risk_engine.py   — two-layer risk detection
scheduler.py     — APScheduler jobs (daily scan, digest, re-index)
memory_engine.py — Mem0 PM memory wrapper
database.py      — SQLite CRUD + FTS5 + audit_log + pm_digests
parsers.py       — WhatsApp parser + MarkItDown + spaCy
auth.py          — session auth
frontend/        — single HTML file, renders ClientStatus structured cards
```

## How to Run
```bash
cd /Users/krishnabhardwaj/developer/conceptual-engine/jinee-client360
source venv/bin/activate
python3 main.py
```

Open http://localhost:8000

## ChromaDB Paths
- Client vectors: ./chroma_db/  (collections named client_{id})
- Mem0 PM memory: ./mem0_db/

## Not Built Yet (Phase 3)
- Backend team dashboard
- Client-facing dashboard
- Baileys WhatsApp auto-sync
- Telegram bot
- Resend email integration
- Centralized master URL for external teams

## Security Status
- No API keys in code — all in .env
- All SQL parameterized
- File uploads validated by extension + magic bytes
- Cross-client vector isolation: each client has own ChromaDB collection
- Admin routes protected by role check (_require_admin)
- Audit log: every feed + query logged

## Known Issues / Watch List
- Mem0 first-run is slow (downloads models) — normal
- LlamaIndex embedding load takes ~10s on cold start — normal
- If GROQ_API_KEY missing: Instructor falls through to Gemini automatically
- FTS5 search only works for entries added after this upgrade (no backfill)
  → Fix: run `rebuild_client_index(client_id)` for all existing clients once after deploy

## Team Setup
```bash
git clone https://github.com/Team-Jinee/Conceptual-Engine.git
cd Conceptual-Engine
cp .env.example .env   # add GROQ_API_KEY and GEMINI_API_KEY
bash setup.sh
source venv/bin/activate && python3 main.py
```
```

- [ ] **Step 2: Commit KRISHNA.MD**

```bash
git add KRISHNA.MD
git commit -m "docs: update KRISHNA.MD for v2 upgrade complete"
```

- [ ] **Step 3: Push to both repos**

```bash
git push origin main
git push conceptual-engine main
```

---

## Final Verification Checklist

- [ ] `python3 main.py` starts without errors, scheduler prints start message
- [ ] PM logs in → sees only their clients, no admin button
- [ ] Admin logs in → admin button shows, all clients visible, filters work
- [ ] Upload WhatsApp .txt → entry appears in timeline, FTS5 indexed
- [ ] Paste Fathom link → full transcript fetched and stored
- [ ] Ask "what is pending?" → returns structured ClientStatus card (not plain text)
- [ ] `risk_level` in response reflects actual client state
- [ ] Admin audit log shows the query was logged
- [ ] `GET /api/admin/clients?risk=at_risk` returns only flagged clients
- [ ] PM token rejected by `/api/admin/*` with 403
- [ ] No Python tracebacks visible in browser responses
- [ ] Both GitHub repos updated: Team-Jinee/Conceptual-Engine and Krishna09Bhardwaj/conceptual-engine
```
