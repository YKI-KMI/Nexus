<div align="center">

# NEXUS Desktop
### AI File Organizer — Native App

**Double-click to run. No browser. No terminal. No setup.**  
Fully local AI that reads, understands, and organizes your files.

![Python](https://img.shields.io/badge/python-3.9%2B-blue?style=flat-square)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey?style=flat-square)
![No API Key](https://img.shields.io/badge/API%20key-none%20required-brightgreen?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)

</div>

---

## Quick Start for Users

1. **Launch the App:** Simply double-click the `NEXUS.exe` (Windows) or `NEXUS` (Mac/Linux) file. *Note: As it packages an entire intelligence engine locally without cloud reliance, it may take 5–10 seconds to launch the first time.*
2. **Select a Target:** Click the **Browse** icon on the screen to use your system's folder picker or manually paste the path of the messy folder directly into the input bar.
3. **Scan:** Click the **Scan** button. NEXUS will securely read through the files using natural language understanding extracting text from PDFs, code, and spreadsheets to conceptually categorize them. *It does not move anything yet!*
4. **Review & Execute:** Review the generated **Organization Plan** detailing the auto-created folders and classifications. If you like the plan, click **Execute** to instantly sort everything.

---

## For developers — building the .exe

### Prerequisites
- Python 3.9 or later → https://python.org
- Git (optional)

### Windows

```bat
git clone https://github.com/YOUR_USERNAME/nexus-desktop.git
cd nexus-desktop
build.bat
```

Output: `dist\NEXUS\NEXUS.exe`

### macOS / Linux

```bash
git clone https://github.com/YOUR_USERNAME/nexus-desktop.git
cd nexus-desktop
bash build.sh
```

Output: `dist/NEXUS/NEXUS`

### Distributing

Zip up the entire `dist/NEXUS/` folder — that's everything the user needs. The `.exe` alone won't run; it needs the folder alongside it.

> **One-file build (optional):** Edit `NEXUS.spec` and replace the `EXE + COLLECT` section with a onefile EXE. This makes a single `.exe` but startup is ~5s slower due to unpacking.

---

## How it works

NEXUS packages:
- A **Flask + SocketIO** backend (runs locally, binds to a random free port)
- A **pywebview** native window that points to it
- All AI logic (no internet required)

The app never exposes anything to your network — it binds to `127.0.0.1` only.

---

## What it organizes

| Format | How it reads it |
|--------|----------------|
| PDF | Full text, first 10 pages |
| Word (.docx) | Paragraphs + tables |
| Excel (.xlsx) | Sheet data |
| PowerPoint | All slide text |
| Code files | Full source |
| Text / Markdown | Full content |
| Images / Videos | Filename semantics |

---

## Upgrading AI quality (optional)

Install [Ollama](https://ollama.ai) for LLM-level reasoning:

```bash
# macOS/Linux
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull mistral
```

NEXUS auto-detects Ollama on startup. The engine badge in the top-right corner shows which engine is active.

- **Local-Semantic (Default):** The built-in neural engine. Incredibly fast, lightweight, and uses mathematical keyword vectors to categorize standard files accurately.
- **Ollama (Advanced):** If installed, NEXUS hooks into large language models (like Mistral or Llama) to perform deep, contextual reasoning on highly obscure files. *Requires more system resources.*

---

## Undoing an organization

Every run writes `.nexus/manifest.json` inside the organized directory.  
To restore everything to how it was:

```bash
python scripts/undo.py /path/to/organized/folder
```

---

## Safety & Security Guarantees

We built NEXUS so you never have to be afraid of losing your data.

- **Never Deletes:** NEXUS only creates folders and *moves* files. It never executes a delete command.
- **Collision Proof:** If you have three files named `invoice.pdf`, NEXUS won't overwrite them. It safely renames them to `invoice_1.pdf`, `invoice_2.pdf`, etc.
- **System Roots Protected:** NEXUS has built-in safeguards blocking it from reorganizing critical system drives (like `C:\Windows`), stopping accidental OS damage.
- **Fully Offline:** Network bound to `127.0.0.1` only — not remotely exposed. Skips `.git`, `node_modules`, and `__pycache__` automatically.

---

## License

MIT
