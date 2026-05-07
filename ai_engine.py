import os
import re
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

import litellm
import instructor
from pydantic import BaseModel
from typing import Literal

from database import get_client, get_data_entries, search_entries_fts

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


def _get_context_chunks(client_id: int, question: str, max_chars: int = 6000) -> list:
    """Hybrid retrieval: vector search → FTS5 keyword → SQLite fallback."""
    chunks = []

    try:
        from vector_store import query_client as vector_query, is_vector_ready
        if is_vector_ready():
            chunks = vector_query(client_id, question, n_results=5)
    except Exception:
        pass

    if question.strip():
        try:
            fts_hits = search_entries_fts(client_id, question)
            for hit in fts_hits:
                if hit not in chunks:
                    chunks.append(hit)
                    if len(chunks) >= 8:
                        break
        except Exception:
            pass

    if not chunks:
        try:
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

QUESTION: {question}"""

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
    client = get_client(client_id)
    if not client:
        return {"status": None, "model_used": "none", "error": True,
                "error_message": "Client not found."}

    question = question.strip()[:500]
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

    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

    for model, key in [
        ("groq/llama-3.3-70b-versatile", groq_key),
        ("gemini/gemini-2.5-flash", gemini_key),
    ]:
        if not key:
            continue
        try:
            status = _call_structured(messages, model)

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
