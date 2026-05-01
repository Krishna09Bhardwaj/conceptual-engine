import os
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
from groq import Groq
import google.generativeai as genai
from database import get_client, get_data_entries

SYSTEM_PROMPT = """You are an intelligent assistant for JineeGreenCard, an immigration consulting company.
You have access to a client's complete journey — their WhatsApp conversations, call transcripts, emails, and case notes.

CRITICAL RULE: Answer ONLY what was asked. Do not output sections or information that weren't requested.

- If asked a specific question ("what's the task for this week?", "what did Dr. Williams say?", "when is the deadline?"), give a direct, focused answer to that question only. 2-5 sentences max.
- If asked for a broad overview ("full status", "summarize everything", "what's going on?"), then provide a structured multi-section response.
- Never pad answers with unrelated sections. If someone asks for tasks, don't add status, deadlines, or completed items unless directly relevant.
- Be concise, professional, and flag risks clearly.
- If information is missing or unclear, say so honestly in one sentence."""


def _get_context_chunks(client_id: int, max_chars: int = 6000) -> list:
    """Pull all data entries from SQLite — no vector search needed."""
    try:
        entries = get_data_entries(client_id)
        chunks = []
        total = 0
        for entry in entries:
            content = entry.get("content", "")
            source = entry.get("source_type", "data")
            created = entry.get("created_at", "")[:10]
            label = f"[{source.upper()} — {created}]"
            snippet = content[:1500]
            chunk = f"{label}\n{snippet}"
            if total + len(chunk) > max_chars:
                break
            chunks.append(chunk)
            total += len(chunk)
        return chunks
    except Exception:
        return []


def _call_groq(messages: list) -> str:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GROQ_API_KEY not set")
    client = Groq(api_key=api_key)
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=1024,
        temperature=0.3,
    )
    return resp.choices[0].message.content


def _call_gemini(messages: list) -> str:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")
    prompt = "\n\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
    resp = model.generate_content(prompt)
    return resp.text


def _build_messages(client: dict, chunks: list, question: str) -> list:
    context_str = ""
    if chunks:
        context_str = "=== CLIENT CONVERSATION HISTORY ===\n" + "\n\n".join(chunks)
    else:
        context_str = "No conversation data has been added for this client yet."

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


def query_client_ai(client_id: int, question: str) -> dict:
    client = get_client(client_id)
    if not client:
        return {"answer": "Client not found.", "model_used": "none", "error": True}

    question = question.strip()[:500]

    # Try vector search first, fall back to SQLite retrieval
    chunks = []
    try:
        from vector_store import query_client as vector_query, is_vector_ready
        if is_vector_ready():
            chunks = vector_query(client_id, question, n_results=5)
    except Exception:
        pass

    # SQLite fallback — always works, no model needed
    if not chunks:
        chunks = _get_context_chunks(client_id)

    messages = _build_messages(client, chunks, question)

    try:
        answer = _call_groq(messages)
        return {"answer": answer, "model_used": "groq/llama-3.3-70b-versatile", "error": False}
    except Exception as groq_err:
        try:
            answer = _call_gemini(messages)
            return {"answer": answer, "model_used": "gemini-2.5-flash (fallback)", "error": False}
        except Exception as gemini_err:
            return {
                "answer": (
                    "AI is unavailable right now.\n\n"
                    f"Groq error: {str(groq_err)[:120]}\n"
                    f"Gemini error: {str(gemini_err)[:120]}\n\n"
                    "Please set GROQ_API_KEY or GEMINI_API_KEY in the .env file.\n"
                    "Get a free Groq key at: https://console.groq.com"
                ),
                "model_used": "none",
                "error": True,
            }


def parse_clients_from_text(text: str, default_pm: str) -> list:
    """Use Groq to extract client records from raw document text."""
    prompt = f"""You are a data extraction assistant. Extract ALL client/case records from the document below.

For each client found, return a JSON object with these exact fields:
- name: full client name (string, required)
- case_type: visa/immigration type like O-1A, EB-1A, H-1B, EB-2 NIW, L-1A, TN, O-1B, etc. (string, use "Unknown" if not found)
- deadline: filing deadline in YYYY-MM-DD format (string or null if not mentioned)
- status: one of "Active", "At Risk", "On Hold", "Completed" (default "Active")
- risk_flag: true if case is urgent/at risk/overdue, false otherwise (boolean)
- notes: any extra details about this client in one sentence (string or "")

Return ONLY a valid JSON array — no explanation, no markdown, no code fences.
If no clients are found, return an empty array [].

DOCUMENT:
{text[:12000]}"""

    messages = [
        {"role": "system", "content": "You extract structured client data from documents. Return only valid JSON arrays."},
        {"role": "user", "content": prompt},
    ]

    try:
        raw = _call_groq(messages)
        # Strip any accidental markdown fences
        raw = re.sub(r"```(?:json)?", "", raw).strip().strip("`").strip()
        import json
        clients = json.loads(raw)
        if not isinstance(clients, list):
            return []
        # Sanitize each record
        clean = []
        for c in clients:
            if not isinstance(c, dict) or not c.get("name", "").strip():
                continue
            clean.append({
                "name": str(c.get("name", "")).strip()[:200],
                "case_type": str(c.get("case_type", "Unknown")).strip()[:50],
                "deadline": c.get("deadline") or None,
                "status": c.get("status", "Active") if c.get("status") in ("Active", "At Risk", "On Hold", "Completed") else "Active",
                "risk_flag": bool(c.get("risk_flag", False)),
                "notes": str(c.get("notes", "")).strip()[:500],
                "assigned_pm": default_pm,
            })
        return clean
    except Exception as e:
        return []

import re


def generate_summary(client_id: int) -> dict:
    return query_client_ai(
        client_id,
        "Give me a complete status summary of this client: what has been completed, what is pending, any risks, deadlines, and recommended next actions.",
    )
