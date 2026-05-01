import os
import sys
from pathlib import Path

# ── Startup checks ────────────────────────────────────────────────────────────
if not Path("venv").exists():
    print("\n❌ ERROR: venv folder not found.")
    print("   Run setup first:  bash setup.sh  (Mac) or  setup.bat  (Windows)\n")
    sys.exit(1)

from dotenv import load_dotenv
load_dotenv()

if not os.getenv("GROQ_API_KEY", "").strip():
    print("\n❌ ERROR: .env file not found or GROQ_API_KEY is missing.")
    print("   Create a .env file in this folder and add:")
    print("   GROQ_API_KEY=your_key_here")
    print("   Get a free key at: https://console.groq.com\n")
    sys.exit(1)
# ─────────────────────────────────────────────────────────────────────────────

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, field_validator
from typing import Optional
import uvicorn

from database import (
    init_db, is_db_empty, get_all_clients, get_clients_for_pm, get_all_pms, get_client, create_client,
    update_client, add_data_entry, get_data_entries, delete_data_entry,
    add_action_item, get_action_items, toggle_action_item, delete_client,
)
from vector_store import init_vector_store, add_to_vector_store, delete_client_vectors
from ai_engine import query_client_ai, generate_summary, parse_clients_from_text
from parsers import parse_whatsapp_txt, fetch_fathom_transcript, extract_text_from_file
from auth import login as auth_login, get_user_from_token, logout as auth_logout

_RISK_KEYWORDS = {
    "overdue", "expired", "urgent", "missed deadline",
    "rfe", "denial", "no response",
}

def _flag_risk_if_keywords(client_id: int, content: str) -> bool:
    low = content.lower()
    if any(kw in low for kw in _RISK_KEYWORDS):
        update_client(client_id, risk_flag=True)
        return True
    return False

app = FastAPI(title="JineeGreenCard Client 360", version="1.0.0")

# CORS — open for demo; restrict before production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Pydantic models ──────────────────────────────────────────────────────────

class ClientCreate(BaseModel):
    name: str
    case_type: str
    deadline: Optional[str] = None
    assigned_pm: Optional[str] = None
    status: str = "Active"
    risk_flag: bool = False
    notes: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_length(cls, v):
        v = v.strip()
        if not v or len(v) > 200:
            raise ValueError("Name must be 1–200 characters")
        return v

    @field_validator("case_type")
    @classmethod
    def case_type_length(cls, v):
        return v.strip()[:50]


class QueryRequest(BaseModel):
    question: str

    @field_validator("question")
    @classmethod
    def question_length(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Question cannot be empty")
        return v[:500]


class ActionItemCreate(BaseModel):
    task: str
    assigned_to: Optional[str] = None
    due_date: Optional[str] = None

    @field_validator("task")
    @classmethod
    def task_length(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Task cannot be empty")
        return v[:200]


class ActionItemToggle(BaseModel):
    completed: bool


class LoginRequest(BaseModel):
    username: str
    password: str


def require_auth(authorization: Optional[str] = Header(None)):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    user = get_user_from_token(token)
    if not user:
        raise HTTPException(401, "Not authenticated")
    return user


def _check_client_access(client_id: int, user: dict):
    client = get_client(client_id)
    if not client:
        raise HTTPException(404, "Client not found")
    if user["role"] != "admin" and client.get("assigned_pm") != user["name"]:
        raise HTTPException(403, "Access denied")
    return client


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    html_path = Path(__file__).parent / "frontend" / "index.html"
    if not html_path.exists():
        return HTMLResponse("<h1>Frontend not found</h1>", status_code=404)
    return HTMLResponse(
        html_path.read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"}
    )


@app.get("/api/health")
async def health():
    groq_key = bool(os.getenv("GROQ_API_KEY", "").strip())
    gemini_key = bool(os.getenv("GEMINI_API_KEY", "").strip())
    return {
        "status": "ok",
        "groq_api_key_set": groq_key,
        "gemini_api_key_set": gemini_key,
        "ai_ready": groq_key or gemini_key,
    }


PM_POSITIONS = {"Program Manager", "Senior Program Manager"}

ROLE_MAP = {
    "Founder / Mentor": "admin",
    "Program Manager": "pm",
    "Senior Program Manager": "pm",
}

ALL_POSITIONS = [
    "Founder / Mentor",
    "Mentor",
    "Operations Head",
    "Senior Program Manager",
    "Program Manager",
    "Research Mentor",
    "Vendor Management",
    "PR Head",
    "PR and Outreach",
    "Opportunities Head",
    "Opportunity Sourcing",
    "Onboarding Lead",
    "Onboarding",
]


class RegisterRequest(BaseModel):
    full_name: str
    position: str
    password: str

    @field_validator("full_name")
    @classmethod
    def name_check(cls, v):
        v = v.strip()
        if not v or len(v) > 100:
            raise ValueError("Full name required (max 100 chars)")
        return v

    @field_validator("position")
    @classmethod
    def position_check(cls, v):
        v = v.strip()
        if v not in ALL_POSITIONS:
            raise ValueError("Invalid position")
        return v

    @field_validator("password")
    @classmethod
    def password_check(cls, v):
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v


def _make_username(full_name: str) -> str:
    import re
    base = re.sub(r"[^a-z0-9]", "", full_name.lower().replace(" ", "."))
    base = base[:20] or "user"
    from database import get_user_by_username
    candidate = base
    suffix = 1
    while get_user_by_username(candidate):
        candidate = f"{base}{suffix}"
        suffix += 1
    return candidate


@app.post("/api/auth/register", status_code=201)
async def register_route(body: RegisterRequest):
    from database import create_user
    from auth import hash_password
    username = _make_username(body.full_name)
    role = ROLE_MAP.get(body.position, "staff")
    create_user(username, body.full_name, role, hash_password(body.password), body.position)
    result = auth_login(username, body.password)
    if result:
        result["position"] = body.position
    return result


@app.post("/api/auth/login")
async def login_route(body: LoginRequest):
    result = auth_login(body.username, body.password)
    if not result:
        raise HTTPException(401, "Invalid username or password")
    return result


@app.get("/api/auth/me")
async def me(authorization: Optional[str] = Header(None)):
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    user = get_user_from_token(token)
    if not user:
        raise HTTPException(401, "Not authenticated")
    return {"id": user["id"], "name": user["name"], "role": user["role"], "username": user["username"]}


@app.post("/api/auth/logout")
async def logout_route(authorization: Optional[str] = Header(None)):
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    if token:
        auth_logout(token)
    return {"message": "Logged out"}


@app.get("/api/users/pms")
async def list_pms(authorization: Optional[str] = Header(None)):
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    user = get_user_from_token(token)
    if not user or user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    return get_all_pms()


@app.get("/api/clients")
async def list_clients(authorization: Optional[str] = Header(None)):
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    user = get_user_from_token(token)
    if not user:
        raise HTTPException(401, "Not authenticated")
    try:
        if user["role"] == "admin":
            return get_all_clients()
        return get_clients_for_pm(user["name"])
    except Exception as e:
        raise HTTPException(500, f"Database error: {str(e)[:100]}")


@app.post("/api/clients", status_code=201)
async def create_new_client(body: ClientCreate, authorization: Optional[str] = Header(None)):
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    user = get_user_from_token(token)
    if not user:
        raise HTTPException(401, "Not authenticated")
    assigned_pm = body.assigned_pm if user["role"] == "admin" else user["name"]
    try:
        client_id = create_client(
            name=body.name,
            case_type=body.case_type,
            deadline=body.deadline,
            assigned_pm=assigned_pm,
            status=body.status,
            risk_flag=body.risk_flag,
            notes=body.notes or "",
        )
        return {"id": client_id, "message": "Client created"}
    except Exception as e:
        raise HTTPException(500, f"Error creating client: {str(e)[:100]}")


@app.post("/api/clients/bulk-import", status_code=201)
async def bulk_import_clients(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None),
):
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    user = get_user_from_token(token)
    if not user:
        raise HTTPException(401, "Not authenticated")
    if user["role"] not in ("admin", "pm"):
        raise HTTPException(403, "Only PMs and admins can import clients")

    fname = file.filename or ""
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
    if ext not in ("pdf", "docx", "doc", "txt"):
        raise HTTPException(400, "Only PDF, DOCX, DOC, or TXT files are accepted")

    try:
        raw_bytes = await file.read()
        if len(raw_bytes) > 10 * 1024 * 1024:
            raise HTTPException(400, "File too large (max 10MB)")
        text = extract_text_from_file(fname, raw_bytes)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Could not read file: {str(e)[:100]}")

    if not text.strip():
        raise HTTPException(400, "Could not extract any text from the file")

    default_pm = user["name"] if user["role"] == "pm" else ""
    clients = parse_clients_from_text(text, default_pm)

    if not clients:
        raise HTTPException(422, "No client records found in the file. Make sure the file contains client name, case type, and other details.")

    created = []
    for c in clients:
        try:
            cid = create_client(
                name=c["name"],
                case_type=c["case_type"],
                deadline=c.get("deadline"),
                assigned_pm=c.get("assigned_pm", default_pm),
                status=c.get("status", "Active"),
                risk_flag=c.get("risk_flag", False),
                notes=c.get("notes", ""),
            )
            created.append({"id": cid, "name": c["name"], "case_type": c["case_type"]})
        except Exception:
            continue

    return {"imported": len(created), "clients": created}


@app.get("/api/clients/{client_id}")
async def get_client_detail(client_id: int, authorization: Optional[str] = Header(None)):
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    user = get_user_from_token(token)
    if not user:
        raise HTTPException(401, "Not authenticated")
    client = _check_client_access(client_id, user)
    entries = get_data_entries(client_id)
    actions = get_action_items(client_id)
    return {"client": client, "data_entries": entries, "action_items": actions}


@app.post("/api/clients/{client_id}/feed")
async def feed_data(
    client_id: int,
    source_type: str = Form(...),
    content: Optional[str] = Form(None),
    url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    conversation_date: Optional[str] = Form(None),
    note_type: Optional[str] = Form(None),
    authorization: Optional[str] = Header(None),
):
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    user = get_user_from_token(token)
    if not user:
        raise HTTPException(401, "Not authenticated")
    client = _check_client_access(client_id, user)

    try:
        if source_type == "whatsapp":
            if file is not None:
                if not file.filename.endswith(".txt"):
                    raise HTTPException(400, "Only .txt WhatsApp export files are accepted")
                raw = (await file.read()).decode("utf-8", errors="replace")
            elif content and content.strip():
                raw = content.strip()[:50000]
            else:
                raise HTTPException(400, "Provide a .txt file or paste chat text")
            parsed = parse_whatsapp_txt(raw, client["name"])
            # Prepend conversation date for pasted chats so AI has temporal context
            if conversation_date and not file:
                parsed = f"[Conversation Date: {conversation_date}]\n\n{parsed}"
            entry_id = add_data_entry(client_id, "whatsapp", parsed)
            add_to_vector_store(client_id, client["name"], "whatsapp", parsed, entry_id)
            risk = _flag_risk_if_keywords(client_id, parsed)
            return {"message": "WhatsApp conversation imported", "entry_id": entry_id, "risk_triggered": risk}

        elif source_type == "fathom":
            if not url or not url.strip().startswith("https://fathom.video/"):
                raise HTTPException(400, "URL must start with https://fathom.video/")
            transcript = await fetch_fathom_transcript(url.strip())
            entry_id = add_data_entry(client_id, "fathom", transcript, source_url=url.strip())
            add_to_vector_store(client_id, client["name"], "fathom", transcript, entry_id)
            risk = _flag_risk_if_keywords(client_id, transcript)
            return {"message": "Fathom transcript fetched", "entry_id": entry_id, "preview": transcript[:200], "risk_triggered": risk}

        elif source_type in ("email", "note", "meeting", "wa_call", "internal"):
            if not content or not content.strip():
                raise HTTPException(400, "Content cannot be empty")
            # Use note_type override if provided (frontend sends it as source_type already)
            actual_type = note_type if note_type in ("email", "note", "meeting", "wa_call", "internal") else source_type
            text = content.strip()[:50000]
            entry_id = add_data_entry(client_id, actual_type, text)
            add_to_vector_store(client_id, client["name"], actual_type, text, entry_id)
            risk = _flag_risk_if_keywords(client_id, text)
            return {"message": f"Saved", "entry_id": entry_id, "risk_triggered": risk}

        else:
            raise HTTPException(400, f"Unknown source_type: {source_type}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error processing data: {str(e)[:150]}")


@app.post("/api/clients/{client_id}/feed/document", status_code=201)
async def feed_document(
    client_id: int,
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None),
):
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    user = get_user_from_token(token)
    if not user:
        raise HTTPException(401, "Not authenticated")
    client = _check_client_access(client_id, user)

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted")

    file_bytes = await file.read()

    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(400, "File too large. Maximum size is 10MB.")

    if not file_bytes.startswith(b"%PDF"):
        raise HTTPException(400, "File does not appear to be a valid PDF.")

    try:
        import pdfplumber, io
        text_parts = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
        text = "\n".join(text_parts).strip()[:50000]
        if not text:
            raise ValueError("Empty")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Could not read this PDF. Please check the file is not password-protected.")

    entry_id = add_data_entry(client_id, "document", text, source_url=file.filename)
    add_to_vector_store(client_id, client["name"], "document", text, entry_id)
    risk = _flag_risk_if_keywords(client_id, text)
    return {
        "message": "Document indexed successfully",
        "entry_id": entry_id,
        "filename": file.filename,
        "risk_triggered": risk,
    }


@app.post("/api/clients/{client_id}/query")
async def query_client_endpoint(client_id: int, body: QueryRequest, authorization: Optional[str] = Header(None)):
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    user = get_user_from_token(token)
    if not user:
        raise HTTPException(401, "Not authenticated")
    _check_client_access(client_id, user)
    try:
        result = query_client_ai(client_id, body.question)
        return result
    except Exception as e:
        raise HTTPException(500, f"AI query error: {str(e)[:100]}")


@app.get("/api/clients/{client_id}/summary")
async def client_summary(client_id: int, authorization: Optional[str] = Header(None)):
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    user = get_user_from_token(token)
    if not user:
        raise HTTPException(401, "Not authenticated")
    _check_client_access(client_id, user)
    try:
        return generate_summary(client_id)
    except Exception as e:
        raise HTTPException(500, f"Summary error: {str(e)[:100]}")


@app.delete("/api/clients/{client_id}")
async def remove_client(client_id: int, authorization: Optional[str] = Header(None)):
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    user = get_user_from_token(token)
    if not user:
        raise HTTPException(401, "Not authenticated")
    _check_client_access(client_id, user)
    try:
        delete_client_vectors(client_id)
        delete_client(client_id)
        return {"message": "Client deleted"}
    except Exception as e:
        raise HTTPException(500, f"Delete error: {str(e)[:100]}")


@app.post("/api/clients/{client_id}/action_items", status_code=201)
async def create_action_item(client_id: int, body: ActionItemCreate, authorization: Optional[str] = Header(None)):
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    user = get_user_from_token(token)
    if not user:
        raise HTTPException(401, "Not authenticated")
    _check_client_access(client_id, user)
    try:
        item_id = add_action_item(client_id, body.task, body.assigned_to, body.due_date)
        return {"id": item_id, "message": "Action item added"}
    except Exception as e:
        raise HTTPException(500, f"Error: {str(e)[:100]}")


@app.patch("/api/clients/{client_id}")
async def update_client_details(client_id: int, body: dict, authorization: Optional[str] = Header(None)):
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    user = get_user_from_token(token)
    if not user:
        raise HTTPException(401, "Not authenticated")
    _check_client_access(client_id, user)
    allowed = {}
    if "name" in body:
        name = str(body["name"]).strip()[:200]
        if not name:
            raise HTTPException(400, "Name cannot be empty")
        allowed["name"] = name
    if "case_type" in body:
        allowed["case_type"] = str(body["case_type"]).strip()[:50]
    if "deadline" in body:
        allowed["deadline"] = str(body["deadline"]).strip() if body["deadline"] else None
    if "status" in body:
        allowed["status"] = str(body["status"]).strip()[:20]
    if "risk_flag" in body:
        allowed["risk_flag"] = bool(body["risk_flag"])
    if not allowed:
        raise HTTPException(400, "Nothing to update")
    update_client(client_id, **allowed)
    return {"message": "Updated", **allowed}


@app.patch("/api/clients/{client_id}/assign-pm")
async def assign_pm(client_id: int, body: dict, authorization: Optional[str] = Header(None)):
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    user = get_user_from_token(token)
    if not user or user["role"] != "admin":
        raise HTTPException(403, "Admin only")
    client = get_client(client_id)
    if not client:
        raise HTTPException(404, "Client not found")
    pm_name = str(body.get("pm_name", "")).strip()[:100]
    update_client(client_id, assigned_pm=pm_name)
    return {"message": "PM assigned", "assigned_pm": pm_name}


@app.delete("/api/entries/{entry_id}", status_code=200)
async def delete_entry(entry_id: int, authorization: Optional[str] = Header(None)):
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    if not get_user_from_token(token):
        raise HTTPException(401, "Not authenticated")
    delete_data_entry(entry_id)
    return {"message": "Deleted"}


@app.patch("/api/action_items/{item_id}")
async def toggle_item(item_id: int, body: ActionItemToggle, authorization: Optional[str] = Header(None)):
    token = authorization[7:] if authorization and authorization.startswith("Bearer ") else None
    if not get_user_from_token(token):
        raise HTTPException(401, "Not authenticated")
    try:
        toggle_action_item(item_id, body.completed)
        return {"message": "Updated"}
    except Exception as e:
        raise HTTPException(500, f"Error: {str(e)[:100]}")


# ─── Startup ──────────────────────────────────────────────────────────────────

def run_startup():
    print("\n" + "=" * 55)
    print("  JineeGreenCard Client 360 Intelligence Engine")
    print("=" * 55)

    # Init DB
    init_db()
    print("✅ SQLite database initialized")

    # Init vector store
    init_vector_store()
    print("✅ ChromaDB vector store initialized")

    # Seed demo data if empty
    if is_db_empty():
        print("⏳ Seeding demo data...")
        from seed_demo import seed, seed_users
        seed_users()
        seed()
        print("✅ Demo data seeded (3 clients, 4 users)")
    else:
        from seed_demo import seed_users
        seed_users()
        print("ℹ️  Database already has data — skipping seed")

    # Security check report
    print("\n✅ Security Check Report")
    env_exists = Path(".env").exists()
    groq_key = bool(os.getenv("GROQ_API_KEY", "").strip())
    gemini_key = bool(os.getenv("GEMINI_API_KEY", "").strip())

    print(f"   {'✅' if env_exists else '⚠️ '} .env file {'exists' if env_exists else 'NOT FOUND — create it!'}")
    print(f"   {'✅' if groq_key else '⚠️ '} GROQ_API_KEY {'loaded' if groq_key else 'NOT SET — get free key at https://console.groq.com'}")
    print(f"   {'✅' if gemini_key else '⚠️ '} GEMINI_API_KEY {'loaded' if gemini_key else 'not set (optional fallback)'}")
    print(f"   {'✅' if groq_key or gemini_key else '⚠️ '} AI ready: {'YES' if groq_key or gemini_key else 'NO — set at least one API key'}")

    if not groq_key:
        print("\n  ⚠️  WARNING: GROQ_API_KEY not set in .env file")
        print("     Get your free key at: https://console.groq.com")
        print("     AI queries will not work until this is set.\n")

    print("\n🚀 Server starting at http://localhost:8000")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    os.chdir(Path(__file__).parent)
    run_startup()
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
