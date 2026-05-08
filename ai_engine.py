import os
import re
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

from dotenv import load_dotenv
load_dotenv()
os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY", "")
os.environ["GEMINI_API_KEY"] = os.getenv("GEMINI_API_KEY", "")

import litellm
import instructor
from pydantic import BaseModel
from typing import Literal

from database import get_client, get_data_entries, search_entries_fts

litellm.set_verbose = False
litellm.suppress_debug_info = True


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
- pending_items: list of things NOT yet done. ONLY include if question is about pending work.
- completed_items: list of things already done. ONLY include if question is about completed work.
- next_deadline: the most important upcoming deadline as a date string or 'Not set'.
- risk_level: 'at_risk' if urgent/overdue/RFE/denial, 'watch' if deadline within 30 days or stale, 'safe' otherwise.
- immediate_action_items: 1-3 concrete next actions the PM should take NOW.
- key_context: DIRECT answer to the specific question asked. 2-5 sentences. DO NOT give a general status update unless that is what was asked.
- current_status: one sentence summary of overall case status.
- IMPORTANT: Your answer must be clearly different depending on the question asked."""

# Intent detection — handled before LLM, no AI call needed
_ACTION_INTENTS = {
    "clear_risk": [
        "mark as healthy", "mark as safe", "clear risk", "remove flag",
        "unmark risk", "clear the risk", "remove risk flag", "mark not at risk",
        "not at risk anymore", "resolved risk", "remove the flag", "unflag",
        "remove as flag", "remove client flag", "remove the client",
        "no longer at risk", "not at risk", "clear flag", "remove risk",
    ],
    "mark_active": [
        "mark as active", "set status active", "reactivate", "set to active",
    ],
    "mark_on_hold": [
        "mark as on hold", "put on hold", "set to on hold", "pause case",
    ],
    "mark_completed": [
        "mark as completed", "mark complete", "case is done", "set to completed",
        "close the case",
    ],
}


def _detect_intent(question: str) -> str | None:
    q = question.lower().strip()
    for intent, phrases in _ACTION_INTENTS.items():
        for phrase in phrases:
            if phrase in q:
                return intent
    return None


# Question-type routing for biased retrieval
_QUESTION_BIAS = {
    "risk":     ["risk", "overdue", "urgent", "danger", "expired", "rfe", "denial", "red flag", "at risk"],
    "pending":  ["pending", "not done", "incomplete", "remaining", "still need", "missing", "outstanding"],
    "completed":["completed", "done", "finished", "submitted", "received", "approved", "filed"],
    "summary":  ["summary", "overview", "full status", "everything", "update", "brief"],
    "conversation": ["conversation", "whatsapp", "call", "transcript", "fathom", "talked", "said", "mentioned"],
    "deadline": ["deadline", "when", "date", "due", "expiry", "expires", "timeline"],
}


def _detect_question_type(question: str) -> str:
    q = question.lower()
    for qtype, keywords in _QUESTION_BIAS.items():
        if any(kw in q for kw in keywords):
            return qtype
    return "general"


def _get_context_chunks(client_id: int, question: str, max_chars: int = 6000) -> list:
    """Hybrid retrieval: vector search → FTS5 keyword → SQLite fallback. Question-type biased."""
    q_type = _detect_question_type(question)
    chunks = []

    # Build retrieval query: actual question + type-specific bias keywords
    bias_terms = {
        "risk": "risk overdue urgent RFE denial",
        "pending": "pending incomplete missing outstanding",
        "completed": "completed done submitted filed approved",
        "conversation": "WhatsApp call transcript Fathom",
        "deadline": "deadline date due expiry",
    }.get(q_type, "")
    retrieval_query = f"{question} {bias_terms}".strip()

    try:
        from vector_store import query_client as vector_query, is_vector_ready
        if is_vector_ready():
            chunks = vector_query(client_id, retrieval_query, n_results=6)
    except Exception:
        pass

    if question.strip():
        try:
            fts_hits = search_entries_fts(client_id, question)
            for hit in fts_hits:
                if hit not in chunks:
                    chunks.append(hit)
                    if len(chunks) >= 10:
                        break
        except Exception:
            pass

    if not chunks:
        try:
            entries = get_data_entries(client_id)
            # For conversation questions, prefer whatsapp/fathom source types
            if q_type == "conversation":
                entries = sorted(entries, key=lambda e: 0 if e.get("source_type") in ("whatsapp", "fathom") else 1)
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
        except Exception:
            pass

    return chunks


def _build_messages(client: dict, chunks: list, question: str) -> list:
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

SPECIFIC QUESTION TO ANSWER: {question}
IMPORTANT: Answer SPECIFICALLY the above question. Do NOT give a general status update unless the question asks for one. Your key_context field must directly answer: "{question}"."""

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _call_structured(messages: list, model: str) -> ClientStatus:
    return _instructor_client.chat.completions.create(
        model=model,
        messages=messages,
        response_model=ClientStatus,
        max_retries=2,
    )


def query_client_ai(client_id: int, question: str, pm_username: str = None) -> dict:
    from database import update_client
    client = get_client(client_id)
    if not client:
        return {"status": None, "model_used": "none", "error": True,
                "error_message": "Client not found."}

    question = question.strip()[:500]

    # ── Intent detection — handle action commands without LLM ──
    intent = _detect_intent(question)
    if intent == "clear_risk":
        update_client(client_id, risk_flag=False)
        return {
            "action": "clear_risk",
            "message": f"✅ Risk flag cleared for {client['name']}. The AT RISK banner has been removed.",
            "model_used": "intent_engine",
            "error": False,
        }
    if intent == "mark_active":
        update_client(client_id, status="Active", risk_flag=False)
        return {
            "action": "status_update",
            "message": f"✅ {client['name']} marked as Active.",
            "model_used": "intent_engine",
            "error": False,
        }
    if intent == "mark_on_hold":
        update_client(client_id, status="On Hold")
        return {
            "action": "status_update",
            "message": f"✅ {client['name']} set to On Hold.",
            "model_used": "intent_engine",
            "error": False,
        }
    if intent == "mark_completed":
        update_client(client_id, status="Completed", risk_flag=False)
        return {
            "action": "status_update",
            "message": f"✅ {client['name']} marked as Completed.",
            "model_used": "intent_engine",
            "error": False,
        }

    chunks = _get_context_chunks(client_id, question)

    if pm_username:
        try:
            from memory_engine import get_pm_context
            pm_ctx = get_pm_context(pm_username, question)
            if pm_ctx:
                chunks = [pm_ctx] + chunks
        except Exception:
            pass

    messages = _build_messages(client, chunks, question)

    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()

    for model, key in [
        ("groq/llama-3.3-70b-versatile", groq_key),
        ("gemini/gemini-2.5-flash", gemini_key),
    ]:
        if not key:
            print(f"[ai_engine] Skipping {model} — API key not set")
            continue
        try:
            print(f"[ai_engine] Attempting {model} for client={client_id}")
            status = _call_structured(messages, model)

            if pm_username:
                try:
                    from memory_engine import add_pm_memory
                    add_pm_memory(pm_username, question, status.key_context)
                except Exception:
                    pass

            print(f"[ai_engine] ✅ {model} responded successfully")
            return {"status": status.model_dump(), "model_used": model, "error": False}
        except Exception as e:
            print(f"[ai_engine] ❌ {model} failed: {type(e).__name__}: {str(e)[:200]}")
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
