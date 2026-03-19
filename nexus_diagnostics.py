"""
NEXUS Diagnostics — Flag Checker & Runtime Logger
==================================================
Drop this file next to main.py. Run it standalone to test your environment,
or import NexusLogger into main.py for live session tracing.

Usage:
    python nexus_diagnostics.py              → full environment pre-flight check
    python nexus_diagnostics.py --live       → attach to a running NEXUS session
    python nexus_diagnostics.py --log <file> → replay and parse an existing log
"""

import sys
import os
import time
import json
import socket
import logging
import argparse
import threading
import traceback
import importlib
from datetime import datetime
from pathlib import Path
from functools import wraps

# ─── ANSI colours (safe on Windows 10+, macOS, Linux) ────────────────────────
RED    = "\033[91m"
YELLOW = "\033[93m"
GREEN  = "\033[92m"
CYAN   = "\033[96m"
DIM    = "\033[2m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def _c(colour, text): return f"{colour}{text}{RESET}"

# ══════════════════════════════════════════════════════════════════════════════
#  NexusLogger  — import this into main.py for live session tracing
# ══════════════════════════════════════════════════════════════════════════════

class NexusLogger:
    """
    Structured, thread-safe logger that writes to both the console and a
    rotating JSON-lines log file. Attach it to main.py like so:

        from nexus_diagnostics import NexusLogger
        nlog = NexusLogger()          # call once near top of main()

    Then sprinkle throughout your code:
        nlog.flag("scan_start",  {"directory": str(target_path)})
        nlog.flag("scan_done",   {"file_count": len(plan)})
        nlog.flag("exec_start",  {})
        nlog.flag("exec_done",   {"moved": n})
        nlog.error("scan_fail",  exc)
    """

    LOG_DIR = Path.home() / ".nexus" / "logs"

    def __init__(self, session_id: str | None = None):
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.log_path = self.LOG_DIR / f"nexus_{self.session_id}.jsonl"
        self._lock = threading.Lock()
        self._timers: dict[str, float] = {}

        # Python stdlib logger (also writes to the jsonl file)
        self._logger = logging.getLogger(f"nexus.{self.session_id}")
        self._logger.setLevel(logging.DEBUG)
        if not self._logger.handlers:
            fh = logging.FileHandler(self.LOG_DIR / f"nexus_{self.session_id}.log")
            fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
            self._logger.addHandler(fh)

        self.flag("session_start", {"pid": os.getpid(), "python": sys.version})

    # ── Public API ────────────────────────────────────────────────────────────

    def flag(self, event: str, data: dict = None):
        """Record a named checkpoint with optional payload."""
        self._write("FLAG", event, data or {})

    def start_timer(self, label: str):
        """Start a named stopwatch."""
        self._timers[label] = time.perf_counter()
        self.flag(f"timer_start:{label}")

    def stop_timer(self, label: str) -> float:
        """Stop a named stopwatch and log elapsed ms."""
        elapsed = (time.perf_counter() - self._timers.pop(label, time.perf_counter())) * 1000
        self.flag(f"timer_stop:{label}", {"elapsed_ms": round(elapsed, 2)})
        return elapsed

    def error(self, context: str, exc: Exception | None = None, extra: dict = None):
        """Record an error with full traceback."""
        payload = extra or {}
        if exc:
            payload["exception"] = type(exc).__name__
            payload["message"]   = str(exc)
            payload["traceback"] = traceback.format_exc()
        self._write("ERROR", context, payload)

    def warn(self, event: str, data: dict = None):
        self._write("WARN", event, data or {})

    # ── Decorator helpers ─────────────────────────────────────────────────────

    def timed(self, label: str | None = None):
        """Decorator: auto-time a function and log FLAG on entry/exit."""
        def decorator(fn):
            name = label or fn.__name__
            @wraps(fn)
            def wrapper(*args, **kwargs):
                self.start_timer(name)
                try:
                    result = fn(*args, **kwargs)
                    self.stop_timer(name)
                    return result
                except Exception as exc:
                    self.error(name, exc)
                    self.stop_timer(name)
                    raise
            return wrapper
        return decorator

    # ── Internal ──────────────────────────────────────────────────────────────

    def _write(self, level: str, event: str, data: dict):
        record = {
            "ts":      datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
            "level":   level,
            "event":   event,
            "session": self.session_id,
            **data,
        }
        line = json.dumps(record)
        with self._lock:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        # Mirror to stdlib logger
        getattr(self._logger, {"FLAG": "info", "WARN": "warning", "ERROR": "error"}.get(level, "debug"))(
            f"[{event}] {json.dumps(data)}"
        )

    def summary(self) -> str:
        """Pretty-print a summary of the current session log."""
        return parse_log(self.log_path)


# ══════════════════════════════════════════════════════════════════════════════
#  Pre-flight environment checks
# ══════════════════════════════════════════════════════════════════════════════

REQUIRED_PACKAGES = [
    ("flask",          "flask"),
    ("flask_socketio", "flask-socketio"),
    ("webview",        "pywebview"),
    ("fitz",           "pymupdf"),
    ("docx",           "python-docx"),
    ("openpyxl",       "openpyxl"),
    ("pptx",           "python-pptx"),
    ("chardet",        "chardet"),
    ("PyInstaller",    "pyinstaller"),
]

OPTIONAL_PACKAGES = [
    ("sentence_transformers", "sentence-transformers (optional – richer AI)"),
    ("sklearn",               "scikit-learn (optional)"),
]

CORE_MODULES = ["core.brain", "core.organizer"]


def check_python_version():
    print(_c(BOLD, "\n── Python Version ──────────────────────────────"))
    major, minor = sys.version_info[:2]
    ok = major == 3 and minor >= 9
    status = _c(GREEN, "✓ OK") if ok else _c(RED, "✗ FAIL — need 3.9+")
    print(f"  Python {major}.{minor}  {status}")
    return ok


def check_packages():
    print(_c(BOLD, "\n── Required Packages ───────────────────────────"))
    all_ok = True
    for import_name, pip_name in REQUIRED_PACKAGES:
        try:
            mod = importlib.import_module(import_name)
            ver = getattr(mod, "__version__", "?")
            print(f"  {_c(GREEN,'✓')} {pip_name:<30} {_c(DIM, ver)}")
        except ImportError:
            print(f"  {_c(RED,'✗')} {pip_name:<30} {_c(RED,'NOT INSTALLED')}  →  pip install {pip_name}")
            all_ok = False

    print(_c(BOLD, "\n── Optional Packages ───────────────────────────"))
    for import_name, pip_name in OPTIONAL_PACKAGES:
        try:
            importlib.import_module(import_name)
            print(f"  {_c(GREEN,'✓')} {pip_name}")
        except ImportError:
            print(f"  {_c(YELLOW,'–')} {pip_name}  {_c(DIM,'(not installed)')}")
    return all_ok


def check_core_modules():
    print(_c(BOLD, "\n── Core Modules ────────────────────────────────"))
    all_ok = True
    for mod_name in CORE_MODULES:
        try:
            importlib.import_module(mod_name)
            print(f"  {_c(GREEN,'✓')} {mod_name}")
        except ImportError as e:
            print(f"  {_c(RED,'✗')} {mod_name}  →  {e}")
            all_ok = False
        except Exception as e:
            print(f"  {_c(YELLOW,'!')} {mod_name}  loaded with warning: {e}")
    return all_ok


def check_assets():
    print(_c(BOLD, "\n── Assets ──────────────────────────────────────"))
    base = Path(__file__).parent
    required = ["assets/index.html"]
    all_ok = True
    for rel in required:
        p = base / rel
        if p.exists():
            print(f"  {_c(GREEN,'✓')} {rel}")
        else:
            print(f"  {_c(RED,'✗')} {rel}  {_c(RED,'MISSING')}")
            all_ok = False
    return all_ok


def check_port_binding():
    print(_c(BOLD, "\n── Port Binding ────────────────────────────────"))
    try:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        print(f"  {_c(GREEN,'✓')} Can bind to 127.0.0.1:{port}")
        return True
    except OSError as e:
        print(f"  {_c(RED,'✗')} Cannot bind: {e}")
        return False


def check_disk_write():
    print(_c(BOLD, "\n── Write Permissions ───────────────────────────"))
    path = Path.home() / ".nexus" / "_diag_test"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ok")
        path.unlink()
        print(f"  {_c(GREEN,'✓')} Can write to {path.parent}")
        return True
    except Exception as e:
        print(f"  {_c(RED,'✗')} Write failed: {e}")
        return False


def check_ollama():
    print(_c(BOLD, "\n── Ollama (optional) ───────────────────────────"))
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
        print(f"  {_c(GREEN,'✓')} Ollama is running → advanced AI mode available")
        return True
    except Exception:
        print(f"  {_c(YELLOW,'–')} Ollama not detected (fallback to local-semantic)")
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  Log parser / replay
# ══════════════════════════════════════════════════════════════════════════════

def parse_log(log_path: Path | str) -> str:
    """Parse a .jsonl session log and print a human-readable timeline."""
    path = Path(log_path)
    if not path.exists():
        return f"Log file not found: {path}"

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    records = []
    for line in lines:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if not records:
        return "Empty log file."

    out = [_c(BOLD, f"\n══ Session Log: {path.name} ({len(records)} events) ══\n")]

    errors  = [r for r in records if r["level"] == "ERROR"]
    warns   = [r for r in records if r["level"] == "WARN"]
    timers  = {}

    for r in records:
        ts    = r.get("ts", "")
        event = r.get("event", "")
        level = r.get("level", "FLAG")

        # Collect timer pairs
        if event.startswith("timer_start:"):
            timers[event[12:]] = r.get("ts")
        if event.startswith("timer_stop:"):
            label = event[11:]
            ms = r.get("elapsed_ms", "?")
            slow = isinstance(ms, (int, float)) and ms > 2000
            colour = RED if slow else (YELLOW if isinstance(ms, (int,float)) and ms > 500 else GREEN)
            out.append(f"  {_c(DIM, ts[11:19])}  ⏱  {label:<30} {_c(colour, str(ms)+' ms')}" +
                       (_c(RED, "  ← SLOW") if slow else ""))
            continue

        # Colour by level
        if level == "ERROR":
            icon  = _c(RED, "✗ ERROR")
            extra = r.get("exception","") + ": " + r.get("message","")
        elif level == "WARN":
            icon  = _c(YELLOW, "! WARN ")
            extra = json.dumps({k:v for k,v in r.items() if k not in ("ts","level","event","session")})
        else:
            icon  = _c(GREEN,  "● FLAG ")
            extra = json.dumps({k:v for k,v in r.items() if k not in ("ts","level","event","session")})

        out.append(f"  {_c(DIM, ts[11:19])}  {icon}  {event:<35} {_c(DIM, extra[:80])}")

    # Summary
    out.append(_c(BOLD, "\n── Summary ─────────────────────────────────────"))
    out.append(f"  Total events : {len(records)}")
    out.append(f"  Errors       : {_c(RED if errors else GREEN, str(len(errors)))}")
    out.append(f"  Warnings     : {_c(YELLOW if warns else GREEN, str(len(warns)))}")
    if errors:
        out.append(_c(RED, "\n── Error Details ────────────────────────────────"))
        for e in errors:
            out.append(f"  [{e.get('ts','')}] {e.get('event','')} → {e.get('exception','')}: {e.get('message','')}")
            tb = e.get("traceback", "")
            if tb:
                for tl in tb.strip().splitlines()[-4:]:
                    out.append(f"    {_c(DIM, tl)}")

    return "\n".join(out)


def tail_log(log_path: Path | str):
    """Live-tail a log file (like `tail -f`)."""
    path = Path(log_path)
    print(_c(CYAN, f"\nLive-tailing {path} — Ctrl-C to stop\n"))
    with open(path, "r", encoding="utf-8") as f:
        f.seek(0, 2)          # jump to end
        while True:
            line = f.readline()
            if line:
                try:
                    r = json.loads(line)
                    level = r.get("level", "FLAG")
                    colour = RED if level == "ERROR" else (YELLOW if level == "WARN" else GREEN)
                    print(f"  {_c(DIM, r.get('ts','')[11:19])}  {_c(colour, level)}  {r.get('event','')}")
                except json.JSONDecodeError:
                    print(line.rstrip())
            else:
                time.sleep(0.3)


def find_latest_log() -> Path | None:
    log_dir = Path.home() / ".nexus" / "logs"
    logs = sorted(log_dir.glob("nexus_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return logs[0] if logs else None


# ══════════════════════════════════════════════════════════════════════════════
#  Bottleneck report (static analysis of known hotspots in main.py)
# ══════════════════════════════════════════════════════════════════════════════

BOTTLENECKS = [
    {
        "id":       "B-01",
        "severity": "HIGH",
        "location": "main.py → main() — server health-poll loop",
        "issue":    "Polling /health every 100 ms for up to 12 seconds burns CPU spin during launch.",
        "fix":      "Use a threading.Event set by the server on first successful bind:\n"
                    "    ready = threading.Event()\n"
                    "    # in start_server: call ready.set() after socketio.run() returns first request\n"
                    "    ready.wait(timeout=10)",
    },
    {
        "id":       "B-02",
        "severity": "HIGH",
        "location": "main.py → session dict — shared mutable state",
        "issue":    "The global `session` dict is mutated from both Flask route threads and worker threads "
                    "with no locking. Under concurrent /scan → /execute calls this is a data race.",
        "fix":      "Guard all reads/writes with a threading.Lock():\n"
                    "    _session_lock = threading.Lock()\n"
                    "    with _session_lock:\n"
                    "        session['status'] = 'scanning'",
    },
    {
        "id":       "B-03",
        "severity": "MEDIUM",
        "location": "main.py → /api/scan — FileOrganizer created inside a daemon thread",
        "issue":    "If the client fires /api/execute before the scan thread finishes setting "
                    "session['organizer'], execute() sees None and returns a 400 even though a scan is running.",
        "fix":      "The /api/execute endpoint should check status == 'scanning' explicitly and "
                    "return a 409 Conflict with a retry-after hint instead of a 400.",
    },
    {
        "id":       "B-04",
        "severity": "MEDIUM",
        "location": "main.py → start_server() — allow_unsafe_werkzeug=True",
        "issue":    "This flag silences Werkzeug's production-server warning but it also suppresses "
                    "important startup errors. The underlying issue is using Werkzeug directly; "
                    "the correct fix is switching to eventlet/gevent as the async transport.",
        "fix":      "In requirements.txt add: eventlet>=0.35.0\n"
                    "In main.py change socketio init:\n"
                    "    socketio = SocketIO(app, async_mode='eventlet', ...)\n"
                    "    # remove allow_unsafe_werkzeug=True",
    },
    {
        "id":       "B-05",
        "severity": "MEDIUM",
        "location": "main.py → /api/browse — webview.windows[0]",
        "issue":    "Accessing windows[0] without checking len(webview.windows) will raise an "
                    "IndexError if called before the window is fully initialised.",
        "fix":      "    if not webview.windows:\n"
                    "        return jsonify({'error': 'Window not ready'}), 503\n"
                    "    result = webview.windows[0].create_file_dialog(...)",
    },
    {
        "id":       "B-06",
        "severity": "LOW",
        "location": "main.py → emit_fn closure",
        "issue":    "emit_fn is a module-level closure over `socketio`. If socketio is not yet "
                    "initialised when NexusBrain/FileOrganizer is constructed the reference is stale.",
        "fix":      "Pass emit_fn as a late-bound lambda:\n"
                    "    emit_fn = lambda e, d: socketio.emit(e, d)",
    },
    {
        "id":       "B-07",
        "severity": "LOW",
        "location": "NEXUS.spec — UPX compression enabled",
        "issue":    "UPX on Python extension DLLs (.pyd) frequently causes false-positive AV "
                    "detections and occasionally corrupts pywebview's CEF/WKWebView binaries.",
        "fix":      "Add the webview binaries to upx_exclude or set upx=False.",
    },
]


def print_bottlenecks():
    print(_c(BOLD, "\n══ Known Bottlenecks & Bugs ══\n"))
    for b in BOTTLENECKS:
        sev = b["severity"]
        colour = RED if sev == "HIGH" else (YELLOW if sev == "MEDIUM" else DIM)
        b_id = b["id"]
        loc = b["location"]
        tag = f"[{b_id}] {sev:<7}"
        print(f"  {_c(colour, tag)}  {_c(BOLD, loc)}")
        print(f"  {'':14}Issue: {b['issue']}")
        print(f"  {'':14}Fix  : {b['fix']}\n")


# ══════════════════════════════════════════════════════════════════════════════
#  CLI entry point
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="NEXUS Diagnostics")
    parser.add_argument("--live",       action="store_true", help="Tail the latest session log live")
    parser.add_argument("--log",        metavar="FILE",      help="Parse a specific .jsonl log file")
    parser.add_argument("--bottlenecks",action="store_true", help="Print bottleneck analysis only")
    parser.add_argument("--no-checks",  action="store_true", help="Skip environment checks")
    args = parser.parse_args()

    print(_c(BOLD + CYAN, "\n╔══════════════════════════════════════════╗"))
    print(_c(BOLD + CYAN,   "║        NEXUS Diagnostics v1.0            ║"))
    print(_c(BOLD + CYAN,   "╚══════════════════════════════════════════╝"))

    if args.bottlenecks:
        print_bottlenecks()
        return

    if args.log:
        print(parse_log(args.log))
        return

    if args.live:
        log = find_latest_log()
        if not log:
            print(_c(RED, "\nNo NEXUS logs found in ~/.nexus/logs/ — run NEXUS first."))
            return
        tail_log(log)
        return

    if not args.no_checks:
        results = {
            "python":  check_python_version(),
            "packages":check_packages(),
            "core":    check_core_modules(),
            "assets":  check_assets(),
            "port":    check_port_binding(),
            "disk":    check_disk_write(),
        }
        check_ollama()
        print_bottlenecks()

        passed = sum(results.values())
        total  = len(results)
        colour = GREEN if passed == total else (YELLOW if passed >= total - 1 else RED)
        print(_c(BOLD, "\n── Overall ─────────────────────────────────────"))
        print(f"  {_c(colour, f'{passed}/{total} checks passed')}\n")

        log_dir = Path.home() / ".nexus" / "logs"
        existing = sorted(log_dir.glob("nexus_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if existing:
            print(_c(BOLD, "── Recent Session Logs ─────────────────────────"))
            for p in existing[:5]:
                mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                print(f"  {_c(DIM, mtime)}  {p.name}")
            print(f"\n  Run:  python nexus_diagnostics.py --log {existing[0]}")
            print(f"  Run:  python nexus_diagnostics.py --live\n")


if __name__ == "__main__":
    main()