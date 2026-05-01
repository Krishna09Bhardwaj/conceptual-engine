# JineeGreenCard — Client 360 Intelligence Engine

Internal tool for JineeGreenCard Program Managers to track client immigration cases, feed conversation data, and get AI-powered answers about any client.

---

## Setup — Mac

**Step 1: Clone the repo**
```bash
git clone https://github.com/Team-Jinee/Conceptual-Engine.git
cd Conceptual-Engine
```

**Step 2: Create your `.env` file**
```bash
cp .env.example .env
```
Open the `.env` file and add your API keys:
```
GROQ_API_KEY=your_key_here
GEMINI_API_KEY=your_key_here
```
Get a free Groq key at: https://console.groq.com

**Step 3: Run setup**
```bash
bash setup.sh
```

**Step 4: Start the server**
```bash
source venv/bin/activate
python3 main.py
```

**Step 5: Open in browser**
```
http://localhost:8000
```

---

## Setup — Windows

**Step 1: Clone the repo**
```
git clone https://github.com/Team-Jinee/Conceptual-Engine.git
cd Conceptual-Engine
```

**Step 2: Create your `.env` file**

Copy `.env.example`, rename it to `.env`, open it in Notepad and add your API keys:
```
GROQ_API_KEY=your_key_here
GEMINI_API_KEY=your_key_here
```
Get a free Groq key at: https://console.groq.com

**Step 3: Run setup**
```
setup.bat
```

**Step 4: Start the server**
```
venv\Scripts\activate
python main.py
```

**Step 5: Open in browser**
```
http://localhost:8000
```

---

## Features

- Multi-user login — PMs see only their own clients, admin sees all
- Feed WhatsApp exports, Fathom transcripts, PDFs, emails, notes
- Ask natural language questions — AI answers using full client history
- Auto risk flagging for urgent cases
- Action items tracker per client
- Bulk client import from PDF/DOCX/TXT

## Tech Stack

- Backend: FastAPI + Python
- Database: SQLite
- AI: Groq llama-3.3-70b (Gemini 2.5 Flash fallback)
- Frontend: Single-file vanilla HTML/CSS/JS
