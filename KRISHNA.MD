# Krishna's Session Notes — Client 360 Engine

## Fixes Applied — May 2026
- **Problem 2 FIXED**: Daily at-risk reminder banner with per-client dismissal (`reminder_dismissals` table, `GET /api/reminders/today`, `POST /api/reminders/dismiss/{id}`)
- **Problem 3 FIXED**: Fathom auto-summary on fetch using Instructor + `FathomSummary` schema (6 fields: client_issue, action_items, deadlines, key_decisions, risk_flags, one_line_summary)
- **Google Doc link pasting**: already fixed before this session
- All 3 May 4 meeting problems now resolved

## Project: JineeGreenCard Client 360 Intelligence System

## Status
- [x] Environment setup — Python 3.14, venv, all packages installed
- [x] Backend (FastAPI) built — main.py with all routes + admin routes
- [x] Database (SQLite) — client360.db with audit_log, pm_digests, FTS5 full-text search
- [x] Vector store (LlamaIndex + ChromaDB) — per-client isolated collections
- [x] AI engine (LiteLLM + Instructor) — structured ClientStatus output, Groq → Gemini fallback
- [x] Risk engine — two-layer rule-based detection (deadline + activity + keyword)
- [x] PM memory (Mem0 self-hosted) — per-PM context across sessions
- [x] Scheduler (APScheduler) — daily risk scan 8AM IST, digest 9AM IST, weekly re-index
- [x] Parsers — MarkItDown PDF, spaCy date extraction, WhatsApp parser, Fathom fetcher
- [x] Frontend — structured AI status cards, admin panel, digest banner
- [x] Security hardened — entry ownership check, parameterized SQL, file type validation
- [x] Tests — 23 tests passing (vector store, risk engine, AI engine, parsers, DB schema)
- [x] Server running on port 8000

## PORT NOTE
Port 7000 is used by macOS AirPlay/ControlCenter.
→ We use PORT 8000 instead.
→ http://localhost:8000

## Architecture (Upgraded)

```
main.py (FastAPI)
  ├── auth.py              — JWT-style token auth, role system (admin/pm/staff)
  ├── database.py          — SQLite, FTS5, audit_log, pm_digests
  ├── vector_store.py      — LlamaIndex + ChromaDB per-client collections
  ├── ai_engine.py         — LiteLLM + Instructor → ClientStatus Pydantic model
  ├── risk_engine.py       — rule-based risk scoring (at_risk / watch / safe)
  ├── memory_engine.py     — Mem0 PM memory (Groq + ChromaDB + HuggingFace)
  ├── scheduler.py         — APScheduler: daily scan, morning digest, weekly re-index
  ├── parsers.py           — WhatsApp, Fathom, PDF (MarkItDown), spaCy dates
  └── frontend/index.html  — single-file UI with structured AI cards + admin view
```

## AI Response Format (NEW)

The AI now returns a structured `ClientStatus` object instead of freeform text:

```json
{
  "status": {
    "current_status": "...",
    "pending_items": ["..."],
    "completed_items": ["..."],
    "next_deadline": "2026-06-09",
    "risk_level": "safe | watch | at_risk",
    "immediate_action_items": ["..."],
    "key_context": "..."
  },
  "model_used": "groq/llama-3.3-70b-versatile",
  "error": false
}
```

## Admin Routes (NEW)

- `GET /api/admin/clients` — all clients with risk_level field (admin only)
- `GET /api/admin/audit` — recent audit log (admin only)
- `GET /api/admin/pm-summary` — per-PM client + activity summary (admin only)
- `GET /api/clients/{id}/digest` — today's morning digest for the PM of this client

## Demo Accounts

| Username | Password  | Role  |
|----------|-----------|-------|
| admin    | admin123  | admin |
| tulsi    | tulsi123  | pm    |
| dhruv    | dhruv123  | pm    |
| lakshita | lakshita123 | pm  |

## REQUIRED BEFORE DEMO — ADD YOUR API KEY

Edit `.env` and add your keys:
```
GROQ_API_KEY=your_key_here
GEMINI_API_KEY=your_key_here   # fallback if Groq fails
```
→ Get Groq FREE at: https://console.groq.com (takes 60 seconds, no credit card)

## How To Run

```bash
cd /Users/krishnabhardwaj/developer/conceptual-engine/jinee-client360
source venv/bin/activate
python3 main.py
```

Then open: **http://localhost:8000**

## Team Setup (for new members)

**Mac:**
```bash
git clone https://github.com/Team-Jinee/Conceptual-Engine.git
cd Conceptual-Engine/jinee-client360
cp .env.example .env   # then add your API keys
bash setup.sh
source venv/bin/activate && python3 main.py
```

**Windows:**
```
git clone https://github.com/Team-Jinee/Conceptual-Engine.git
cd Conceptual-Engine\jinee-client360
copy .env.example .env
setup.bat
venv\Scripts\activate && python main.py
```

## Demo Flow (10 minutes)

**1. Login as admin / admin123**
- Notice the 🛡 Admin View button in the sidebar
- Click it → see all clients with risk levels, filter by risk/PM
- Click PM Summary → per-PM stats

**2. Select Arjun Mehta (At Risk client)**
- Red dot, deadline in RED
- See risk banner at top

**3. AI Demo — the money shot (3 min)**
- Click "Full Status" → structured card renders: risk badge, pending/completed items, immediate actions, key context
- Click "What's at Risk" → specific risk analysis
- Click "Action Items" → prioritized list with deadline context

**4. Data Feed (1 min)**
- WhatsApp .txt upload, Fathom link auto-fetch, note/email paste, PDF upload

**5. Admin Panel Demo**
- Filter by "at_risk" → see flagged clients
- Click a client row → jumps directly to their dashboard

## Key Points to Say
- "AI returns structured data, not freeform text — it always gives risk level, pending items, action items"
- "The AI has read every conversation, call transcript, document, and email for this client"
- "Risk engine runs automatically every morning — PMs get a digest at 9AM IST"
- "Memory engine: the AI remembers what each PM asked about before — context persists across sessions"
- "All data is local — only the query goes to the AI API"

## Scheduler Jobs
| Job | Schedule | What it does |
|-----|----------|-------------|
| Daily Risk Scan | 8AM IST | Flags new at-risk clients |
| Morning Digest | 9AM IST | Generates per-PM priority list |
| Weekly Re-index | Sunday midnight IST | Rebuilds ChromaDB from SQLite |
