import os
import re
import logging
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

# Silence instructor's internal retry/exception loggers that print XML noise
logging.getLogger("instructor").setLevel(logging.CRITICAL)
logging.getLogger("litellm").setLevel(logging.CRITICAL)
logging.getLogger("httpx").setLevel(logging.CRITICAL)


class ClientStatus(BaseModel):
    action: Literal["none", "mark_risk", "clear_risk", "mark_active", "mark_on_hold", "mark_completed"] = "none"
    current_status: str
    pending_items: list[str]
    completed_items: list[str]
    next_deadline: str
    risk_level: Literal["safe", "watch", "at_risk"]
    immediate_action_items: list[str]
    key_context: str


_instructor_client = instructor.from_litellm(litellm.completion)

SYSTEM_PROMPT = """You are the AI brain for JineeGreenCard, an immigration consulting company.
You have the client's full conversation history — WhatsApp, Fathom calls, emails, case notes.
You understand the PM's intent from CONTEXT, not just keywords. A PM is a human — they speak naturally.

── ACTION DETECTION ──
The PM may be giving you a COMMAND, not asking a question. Detect this from meaning, not exact words.
Set `action` field if the PM wants you to change something in the system:

  mark_risk    → PM wants to flag this client as AT RISK
    Examples: "flag this client", "mark as risk", "this case is problematic",
              "we're in trouble here", "escalate this", "this needs a flag",
              "mark this client as risk", "put a risk flag", "flag it"

  clear_risk   → PM wants to remove the AT RISK flag
    Examples: "remove the flag", "unflag", "clear risk", "we're good now",
              "mark as healthy", "no longer at risk", "resolved"

  mark_active  → PM wants status set to Active
    Examples: "reactivate", "set to active", "case is back on track"

  mark_on_hold → PM wants to pause the case
    Examples: "put on hold", "pause", "freeze this case", "hold for now"

  mark_completed → PM wants to close the case
    Examples: "case is done", "close it", "mark complete", "wrap up"

  none → PM is asking a question or requesting information (not a command)

── WHEN action != "none" ──
- Set key_context to a SHORT confirmation: "Done. [Client name] has been flagged as AT RISK."
- Set current_status to reflect the new state.
- Set risk_level to match the action (mark_risk → at_risk, clear_risk → safe, etc.)
- pending_items and completed_items can be empty lists.
- immediate_action_items: 1-2 follow-up actions after the change.

── WHEN action == "none" (answering a question) ──
- pending_items: list of things NOT yet done. ONLY include if question is about pending work.
- completed_items: list of things already done. ONLY include if question is about completed work.
- next_deadline: the most important upcoming deadline as a date string or 'Not set'.
- risk_level: 'at_risk' if urgent/overdue/RFE/denial, 'watch' if deadline within 30 days or stale, 'safe' otherwise.
- immediate_action_items: 1-3 concrete next actions the PM should take NOW.
- key_context: DIRECT answer to the specific question asked. 2-5 sentences.
- current_status: one sentence summary of overall case status.
- IMPORTANT: Your answer must be clearly different depending on the question asked."""

# Intent detection — handled before LLM, no AI call needed
# Uses keyword-combination logic so any natural phrasing is caught.

_REMOVE_WORDS = {"remove", "clear", "unflag", "unmark", "take off", "delete", "drop", "reset"}
_FLAG_WORDS   = {"flag", "risk", "flagged", "at-risk", "at risk", "mark", "warning"}
_SET_WORDS    = {"flag", "mark", "set", "put", "add", "make", "label", "tag"}

def _detect_intent(question: str) -> str | None:
    q = question.lower().strip()

    # clear_risk: any remove/clear word + any flag/risk word, or explicit healthy/safe phrases
    if (any(w in q for w in _REMOVE_WORDS) and any(w in q for w in _FLAG_WORDS)) \
       or any(p in q for p in ["mark as healthy", "mark as safe", "not at risk",
                                "no longer at risk", "resolved risk", "unflag"]):
        return "clear_risk"

    # mark_risk: any set/flag word + risk mention (and no remove word to avoid conflict with clear_risk)
    if not any(w in q for w in _REMOVE_WORDS):
        if (any(w in q for w in _SET_WORDS) and ("risk" in q or "at-risk" in q)) \
           or any(p in q for p in ["flag this client", "flag the client", "flag client",
                                   "mark at risk", "mark as at risk", "set as at risk",
                                   "this is risky", "needs attention", "escalate"]):
            return "mark_risk"

    if any(p in q for p in ["mark as active", "set to active", "reactivate", "set status active"]):
        return "mark_active"

    if any(p in q for p in ["on hold", "put on hold", "pause case", "set to on hold"]):
        return "mark_on_hold"

    if any(p in q for p in ["mark as completed", "mark complete", "case is done",
                             "close the case", "set to completed"]):
        return "mark_completed"

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
    # Redirect stdout+stderr during instructor call to kill XML retry noise.
    # Instructor prints <generation number="1"><exception>...</exception> via
    # sys.stdout directly — the logging module cannot suppress it.
    import sys, os as _os, contextlib
    with open(_os.devnull, "w") as _null, \
         contextlib.redirect_stdout(_null), \
         contextlib.redirect_stderr(_null):
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
    if intent == "mark_risk":
        update_client(client_id, risk_flag=True)
        return {
            "action": "mark_risk",
            "message": f"🚨 {client['name']} has been flagged as AT RISK.",
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

    # Gemini first — high free quota, great structured output.
    # Groq 70b fallback — free but 100k TPD daily cap.
    for model, key in [
        ("gemini/gemini-2.5-flash", gemini_key),
        ("groq/llama-3.3-70b-versatile", groq_key),
    ]:
        if not key:
            print(f"[ai_engine] Skipping {model} — API key not set")
            continue
        try:
            print(f"[ai_engine] Attempting {model} for client={client_id}")
            status = _call_structured(messages, model)

            # Execute DB action if LLM decided to take one
            if status.action == "mark_risk":
                update_client(client_id, risk_flag=True)
                print(f"[ai_engine] action=mark_risk applied for client={client_id}")
            elif status.action == "clear_risk":
                update_client(client_id, risk_flag=False)
                print(f"[ai_engine] action=clear_risk applied for client={client_id}")
            elif status.action == "mark_active":
                update_client(client_id, status="Active", risk_flag=False)
                print(f"[ai_engine] action=mark_active applied for client={client_id}")
            elif status.action == "mark_on_hold":
                update_client(client_id, status="On Hold")
                print(f"[ai_engine] action=mark_on_hold applied for client={client_id}")
            elif status.action == "mark_completed":
                update_client(client_id, status="Completed", risk_flag=False)
                print(f"[ai_engine] action=mark_completed applied for client={client_id}")

            if pm_username:
                try:
                    from memory_engine import add_pm_memory
                    add_pm_memory(pm_username, question, status.key_context)
                except Exception:
                    pass

            print(f"[ai_engine] ✅ {model} responded successfully (action={status.action})")
            return {"status": status.model_dump(), "model_used": model, "error": False}
        except Exception as e:
            err_str = str(e)
            is_rate_limit = "429" in err_str or "rate_limit" in err_str.lower() or "quota" in err_str.lower()
            print(f"[ai_engine] ❌ {model} failed ({'rate limit' if is_rate_limit else type(e).__name__})")
            continue

    return {
        "status": None, "model_used": "none", "error": True,
        "error_message": (
            "API quota exhausted for today. Both Gemini and Groq free tiers have daily limits. "
            "The AI will be available again tomorrow, or upgrade to a paid API key tier."
        ),
    }


class FathomSummary(BaseModel):
    client_issue: str
    action_items: list[str]
    deadlines: list[str]
    key_decisions: list[str]
    risk_flags: list[str]
    one_line_summary: str


_FATHOM_SYSTEM_PROMPT = """You are an expert immigration case manager summarizing a client call transcript for JineeGreenCard.
Extract actionable intelligence only. Be specific. No filler words.
Focus on: what the client needs, what the team promised, what deadlines were mentioned, what is at risk.
Return structured JSON matching the schema exactly."""


def generate_fathom_summary(transcript_text: str, client_name: str) -> FathomSummary | None:
    import sys, os as _os, contextlib
    messages = [
        {"role": "system", "content": _FATHOM_SYSTEM_PROMPT},
        {"role": "user", "content": f"Client: {client_name}\n\nTranscript:\n{transcript_text[:12000]}"},
    ]
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    for model, key in [
        ("gemini/gemini-2.5-flash", gemini_key),
        ("groq/llama-3.3-70b-versatile", groq_key),
    ]:
        if not key:
            continue
        try:
            with open(_os.devnull, "w") as _null, \
                 contextlib.redirect_stdout(_null), \
                 contextlib.redirect_stderr(_null):
                result = _instructor_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    response_model=FathomSummary,
                    max_retries=2,
                )
            return result
        except Exception:
            continue
    return None


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
