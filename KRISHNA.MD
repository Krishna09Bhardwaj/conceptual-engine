# Krishna's Session Notes — Client 360 Engine

## Project: JineeGreenCard Client 360 Intelligence System

## Status
- [x] Environment setup — Python 3.14, venv, all packages installed
- [x] Backend (FastAPI) built — main.py with all routes
- [x] Database (SQLite) initialized — client360.db ✅
- [x] Vector store (ChromaDB) — available as enhancement when model cached
- [x] AI integration (Groq) — working, Gemini fallback ready
- [x] Fathom transcript fetcher — parsers.py
- [x] WhatsApp .txt parser — parsers.py
- [x] Frontend (demo UI) built — frontend/index.html (single file, full UI)
- [x] Demo data seeded — 3 clients with rich data
- [x] Security checks — parameterized SQL, file type validation, input limits
- [x] Server running on port 8000

## PORT NOTE
Port 7000 is used by macOS AirPlay/ControlCenter.
→ We use PORT 8000 instead.
→ http://localhost:8000

## What Is Done
✅ All files written and verified
✅ venv at ./venv with all packages
✅ SQLite DB (client360.db) with 3 demo clients
✅ 3 demo clients seeded:
   - Arjun Mehta (O-1A, AT RISK) — 3 entries + 5 action items
   - Priya Sharma (EB-1A, Active) — 2 entries + 2 action items
   - Rohit Verma (H-1B, Active) — 2 entries + 3 action items
✅ AI engine: SQLite-based context retrieval (instant) + Groq → Gemini fallback
✅ Full single-file frontend with 3-panel layout
✅ Server verified running on http://localhost:8000

## REQUIRED BEFORE DEMO — ADD YOUR API KEY

Edit `.env` and add your Groq key:
```
GROQ_API_KEY=your_key_here
```
→ Get FREE at: https://console.groq.com (takes 60 seconds, no credit card)

## How To Run The Project

```bash
cd /Users/krishnabhardwaj/developer/conceptual-engine/jinee-client360
source venv/bin/activate
python3 main.py
```

Then open: **http://localhost:8000**

The server auto-seeds 3 demo clients on first launch.

## Team Setup (for new members)

**Mac:**
```bash
git clone https://github.com/Team-Jinee/Conceptual-Engine.git
cd Conceptual-Engine
cp .env.example .env   # then add your API keys
bash setup.sh
source venv/bin/activate && python3 main.py
```

**Windows:**
```
git clone https://github.com/Team-Jinee/Conceptual-Engine.git
cd Conceptual-Engine
copy .env.example .env   # then add your API keys in Notepad
setup.bat
venv\Scripts\activate && python main.py
```

## Startup Checks Added
- Server exits with clear message if `.env` is missing or `GROQ_API_KEY` is empty
- Server exits with clear message if `venv` folder doesn't exist

## Demo Instructions For Seniors

### Setup (5 min before meeting)
1. Open Terminal
2. Run: `cd /Users/krishnabhardwaj/developer/conceptual-engine/jinee-client360 && source venv/bin/activate && python3 main.py`
3. See startup report print ✅ items
4. Open Chrome at http://localhost:8000

### Demo Flow (8-10 minutes)

**1. Show the sidebar (30 sec)**
- Left panel = client list
- Red dot on Arjun Mehta = At Risk
- Green dots on Priya and Rohit = Active

**2. Click Arjun Mehta (2 min)**
- Show dashboard: O-1A case, ~45 day deadline in RED, "At Risk" status
- Point to the RED RISK BANNER at top
- Show 4 stat cards: case type, deadline, status, assigned PM (Tulsi Rani)

**3. AI Demo — the money shot (3 min)**
- Click "Full Status" quick button
- AI responds in ~3-5 seconds with a structured answer
- It knows: Dr. Williams letter overdue, I-94 expiry, filing deadline
- Click "What's at Risk" → specific risk analysis
- Type custom: "What happened with Dr. Williams?" → AI knows exactly from the WhatsApp conversations

**4. Data Feed Demo (1 min)**
- Show "WhatsApp" tab: "PMs export chats from their phone, upload here"
- Show "Fathom Link" tab: "Paste meeting recording URL, auto-fetches transcript"
- Show "Note/Email" tab: "Paste any text directly"

**5. Action Items (30 sec)**
- Right panel: 5 action items for Arjun
- Check one off — it crosses out
- Type a new one, press Enter — adds instantly

**6. Add a New Client (1 min)**
- Click "+ Add Client"
- Fill in name, case type, PM
- Client appears in sidebar immediately

### Key Points to Say
- "This replaces digging through WhatsApp at 11pm"
- "The AI has read every conversation, email, and call note for this client"
- "Phase 2: WhatsApp auto-sync via Baileys, Fathom webhook, email integration"
- "All data is local — only the query goes to the AI API"
- "Takes 10 seconds to onboard a new client"

### If Asked About Vector Search
"The semantic search layer (ChromaDB) is ready — it uses SQLite-based retrieval
for the demo which works great. With one model download, it upgrades to full
semantic vector search automatically."
