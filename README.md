# Client 360 Intelligence Engine

An internal AI-powered case management system built for an immigration consulting firm. Program Managers use it to track client journeys, feed conversation data from multiple sources, and get instant AI answers about any client — without digging through WhatsApp, emails, or call notes manually.

## What It Does

- Multi-user login with role-based access — PMs see only their own clients, admin sees all with assignment controls
- Feeds data from WhatsApp exports, Fathom call transcripts, PDFs, emails, and manual notes into a per-client knowledge base
- Ask any natural language question about a client — AI answers using the full conversation history
- Auto-detects risk keywords (RFE, overdue, urgent, denial) and flags the client AT RISK in real time
- Tracks uploaded documents per client with full-text viewer and search
- Action items panel per client with checkbox completion
- Bulk client import from PDF/DOCX/TXT — AI parses and extracts all client records automatically
- Smart deadline editing — changing a deadline auto-updates the risk flag and status
- Real-time updates throughout — no page reloads after any action

## Tech Stack

- **FastAPI** — Python backend with all API routes
- **SQLite** — Structured client data, sessions, action items, and conversation history
- **ChromaDB** — Semantic vector search over conversation history (auto-enables when model is cached)
- **Groq** (llama-3.3-70b-versatile) — Primary AI model for client Q&A and bulk import parsing
- **Google Gemini** (2.5-flash) — Automatic fallback if Groq is unavailable
- **pdfplumber + pypdf** — PDF text extraction for document indexing
- **python-docx** — DOCX parsing for bulk client imports
- **Baileys** — Planned WhatsApp auto-sync integration (Phase 2)
- **Vanilla HTML/CSS/JS** — Single-file frontend, no framework, no build step

## Architecture

```
main.py              — FastAPI server, all API routes, auth middleware
ai_engine.py         — Groq/Gemini AI calls, context assembly, bulk import parsing
database.py          — SQLite schema, all CRUD operations
auth.py              — Session-based auth, pbkdf2 password hashing
vector_store.py      — ChromaDB wrapper, chunking, semantic search
parsers.py           — WhatsApp .txt parser, Fathom transcript fetcher, file extractors
seed_demo.py         — Demo data seeder for first launch
frontend/index.html  — Complete single-file UI (auth, dashboard, feed, AI, docs)
```

## Key Design Decisions

- **SQLite as primary RAG source** — ChromaDB requires a 79MB ONNX model download which is slow on restricted networks. The system uses direct SQLite retrieval as the primary context path — fast, zero-dependency, works everywhere. Vector search upgrades automatically when the model is cached.
- **No JWT, no Redis** — Sessions are UUID tokens stored in SQLite. Eliminates external dependencies while remaining secure for internal use.
- **Single HTML file frontend** — The entire UI is one file. No build tools, no npm, no bundler. Anyone can read and modify it. Works over any static server.
- **Dual AI fallback** — Every AI request tries Groq first, falls back to Gemini if it fails. The system never goes dark because of a single API outage.
- **Risk keyword auto-detection** — Every feed action scans content for risk signals and updates the client flag without any manual input from the PM.
- **Focused AI answers** — The system prompt enforces answer scoping: specific questions get 2-5 sentence answers, broad overview questions get structured multi-section responses. No padding.

## Data Sources Supported

| Source | Method |
|---|---|
| WhatsApp | .txt export upload or direct paste with conversation date |
| Fathom | Share link — system auto-fetches full transcript |
| PDF | Upload — full text extracted and indexed |
| Email | Paste raw email thread |
| Meeting Summary | Manual entry with type tagging |
| WhatsApp Call | Summary notes |
| Internal Update | PM-to-PM notes |

## AI Capabilities

- **Full status summary** — what's done, what's pending, risks, next actions
- **Specific questions** — "What did Dr. Williams say?", "When is the RFE deadline?"
- **Conversation summary** — across all WhatsApp, calls, and emails
- **Risk analysis** — flags and explains specific risks per client
- **Bulk client parsing** — paste a document with 20 clients, AI extracts all records into structured data

## Setup

1. Clone the repo
2. Run `bash setup.sh` (Mac) or `setup.bat` (Windows)
3. Copy `.env.example` to `.env` and add your API keys
   - Groq key (free): https://console.groq.com
   - Gemini key (free, optional fallback): https://aistudio.google.com/apikey
4. `source venv/bin/activate && python3 main.py`
5. Open `http://localhost:8000`

Server auto-creates the database and seeds demo data on first launch.

## Security

- Passwords hashed with `pbkdf2_hmac` (100,000 iterations)
- Session tokens are UUID4, stored server-side
- All file uploads validated by extension and magic bytes
- PDF uploads capped at 10MB
- All text inputs stripped and limited to 50,000 characters
- SQL uses parameterized queries throughout
- `.env` and database files are gitignored
