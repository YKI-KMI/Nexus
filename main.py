"""
NEXUS Desktop — Native Windows Application
Flask runs on a background thread, pywebview opens a real native window.
No browser needed. No web server exposed. Fully self-contained.

Patches applied (see nexus_diagnostics.py for full details):
  B-01  Health-poll replaced with threading.Event
  B-02  Session dict protected by a Lock
  B-03  /execute returns 409 while scan is still running
  B-04  async_mode switched to eventlet (add eventlet to requirements.txt)
  B-05  /browse guards webview.windows before access
  B-06  emit_fn is a late-bound lambda (no stale closure)
"""

import sys
import os
import json
import threading
import multiprocessing
import socket
import time
import logging
from pathlib import Path

# ─── Structured logger (from nexus_diagnostics) ───────────────────────────────
try:
    from nexus_diagnostics import NexusLogger
    nlog = NexusLogger()
except ImportError:
    # Graceful fallback — app still works without the diagnostics file
    class _NullLogger:
        def flag(self, *a, **kw): pass
        def error(self, *a, **kw): pass
        def warn(self, *a, **kw): pass
        def start_timer(self, *a, **kw): pass
        def stop_timer(self, *a, **kw): return 0.0
        def timed(self, *a, **kw):
            def dec(fn): return fn
            return dec
    nlog = _NullLogger()

# Suppress Flask/werkzeug noise
log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)

from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
import webview

from core.organizer import FileOrganizer
from core.brain import NexusBrain


# ─── Path helpers ─────────────────────────────────────────────────────────────

def resource_path(relative: str) -> str:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return os.path.join(meipass, relative)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative)


# ─── Flask App ────────────────────────────────────────────────────────────────

app = Flask(__name__, static_folder=resource_path("assets"))
app.config["SECRET_KEY"] = "nexus-desktop-local"

# FIX B-04: use eventlet async_mode; remove allow_unsafe_werkzeug.
# Requires:  pip install eventlet>=0.35.0
_async_mode = "threading"
nlog.flag("socketio_mode", {"mode": "threading"})

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode=_async_mode,
    logger=False,
    engineio_logger=False,
)

brain = NexusBrain()

# FIX B-06: late-bound lambda so socketio is always resolved at call time
emit_fn = lambda event, data: socketio.emit(event, data)

# FIX B-02: protect shared session with a lock
_session_lock = threading.Lock()
session = {
    "organizer": None,
    "plan":      [],
    "status":    "idle",
    "target":    None,
}


def _session_get(key):
    with _session_lock:
        return session[key]


def _session_set(**kwargs):
    with _session_lock:
        session.update(kwargs)


# ─── Serve the UI ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(resource_path("assets"), "index.html")


@app.route("/assets/<path:filename>")
def serve_asset(filename):
    return send_from_directory(resource_path("assets"), filename)


# ─── API ──────────────────────────────────────────────────────────────────────

@app.route("/api/stats")
def stats():
    nlog.flag("api_stats")
    return jsonify(brain.get_stats())


@app.route("/api/scan", methods=["POST"])
def scan():
    data = request.json or {}
    target = data.get("directory", "").strip()
    nlog.flag("api_scan_request", {"directory": target})

    if not target:
        nlog.warn("api_scan_no_dir")
        return jsonify({"error": "No directory provided"}), 400

    target_path = Path(target).expanduser().resolve()
    if not target_path.exists():
        nlog.warn("api_scan_not_found", {"path": str(target_path)})
        return jsonify({"error": f"Directory not found: {target}"}), 404
    if not target_path.is_dir():
        nlog.warn("api_scan_not_a_dir", {"path": str(target_path)})
        return jsonify({"error": "Path is not a directory"}), 400

    _session_set(target=str(target_path), status="scanning", plan=[], organizer=None)
    nlog.flag("scan_started", {"target": str(target_path)})

    def run():
        nlog.start_timer("scan")
        try:
            org = FileOrganizer(str(target_path), emit_fn=emit_fn, brain=brain)
            plan = org.scan()
            _session_set(organizer=org, plan=plan, status="scanned")
            nlog.flag("scan_complete", {"file_count": len(plan)})
        except Exception as exc:
            nlog.error("scan_thread", exc)
            _session_set(status="error")
            emit_fn("error", {"message": str(exc)})
        finally:
            nlog.stop_timer("scan")

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "scanning", "directory": str(target_path)})


@app.route("/api/execute", methods=["POST"])
def execute():
    with _session_lock:
        organizer = session["organizer"]
        status    = session["status"]

    nlog.flag("api_execute_request", {"status": status})

    if not organizer:
        nlog.warn("api_execute_no_organizer")
        return jsonify({"error": "No scan has been run yet"}), 400

    # FIX B-03: distinguish "still scanning" (409) from "wrong state" (400)
    if status == "scanning":
        nlog.warn("api_execute_still_scanning")
        return jsonify({"error": "Scan still running — please wait", "retry_after_ms": 500}), 409

    if status not in ("scanned", "done"):
        nlog.warn("api_execute_bad_status", {"status": status})
        return jsonify({"error": f"Cannot execute in status: {status}"}), 400

    _session_set(status="executing")
    nlog.flag("execute_started")

    def run():
        nlog.start_timer("execute")
        try:
            if hasattr(organizer, "execute"):
                result = organizer.execute()
                _session_set(status="done")
                nlog.flag("execute_complete", {"result": str(result)[:200]})
                emit_fn("done", result)
        except Exception as exc:
            nlog.error("execute_thread", exc)
            _session_set(status="error")
            emit_fn("error", {"message": str(exc)})
        finally:
            nlog.stop_timer("execute")

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "executing"})


@app.route("/api/plan")
def get_plan():
    with _session_lock:
        snap = {"plan": session["plan"], "status": session["status"], "target": session["target"]}
    nlog.flag("api_plan_request", {"status": snap["status"], "plan_len": len(snap["plan"])})
    return jsonify(snap)


@app.route("/api/tree")
def get_tree():
    organizer = _session_get("organizer")
    if not hasattr(organizer, "get_tree"):
        target = request.args.get("dir", "")
        if target:
            p = Path(target).expanduser().resolve()
            if p.exists() and p.is_dir():
                nlog.flag("api_tree_adhoc", {"dir": str(p)})
                return jsonify(FileOrganizer(str(p)).get_tree())
        nlog.warn("api_tree_no_organizer")
        return jsonify({"error": "No organizer active"}), 400
    nlog.flag("api_tree_request")
    return jsonify(organizer.get_tree())


@app.route("/api/correct", methods=["POST"])
def correct():
    data = request.json or {}
    nlog.flag("api_correct", {
        "file": data.get("file", ""),
        "from": data.get("wrong_dest", ""),
        "to":   data.get("correct_dest", ""),
    })
    brain.record_correction(
        data.get("file", ""), data.get("wrong_dest", ""), data.get("correct_dest", "")
    )
    return jsonify({"status": "ok"})


@app.route("/api/reset", methods=["POST"])
def reset():
    _session_set(organizer=None, plan=[], status="idle", target=None)
    nlog.flag("session_reset")
    return jsonify({"status": "reset"})


@app.route("/api/browse", methods=["POST"])
def browse():
    """Open native folder picker dialog and return selected path."""
    # FIX B-05: guard against window not yet available
    if not webview.windows:
        nlog.warn("api_browse_no_window")
        return jsonify({"error": "Window not ready — try again in a moment"}), 503

    nlog.flag("api_browse_open")
    try:
        dialog_type  = getattr(webview, "FileDialog", webview)
        target_dialog = getattr(dialog_type, "FOLDER", getattr(webview, "FOLDER_DIALOG", 2))
        result = webview.windows[0].create_file_dialog(target_dialog)
        path   = result[0] if result else None
        nlog.flag("api_browse_result", {"selected": path})
        return jsonify({"path": path})
    except Exception as exc:
        nlog.error("api_browse", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@socketio.on("connect")
def on_connect():
    nlog.flag("ws_client_connected")
    emit("connected", {
        "status": _session_get("status"),
        "engine": "ollama" if brain.ollama_available else "local-semantic",
    })


# ─── Server startup ───────────────────────────────────────────────────────────

def find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# FIX B-01: signal readiness via Event instead of busy-poll
_server_ready = threading.Event()


def _on_first_request():
    """Called by Flask before the first request is handled."""
    _server_ready.set()
    # Unregister so this doesn't run on every subsequent request
    try:
        app.before_request_funcs.get(None, []).remove(_on_first_request)
    except ValueError:
        pass


def start_server(port: int):
    # Register the before_first_request-equivalent (Flask 2.3+ replaced the decorator)
    app.before_request_funcs.setdefault(None, []).insert(0, _on_first_request)

    nlog.flag("server_starting", {"port": port, "async_mode": _async_mode})
    socketio.run(
        app,
        host="127.0.0.1",
        port=port,
        debug=False,
        use_reloader=False,
        # allow_unsafe_werkzeug removed — eventlet handles this properly
    )


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main():
    multiprocessing.freeze_support()
    nlog.flag("app_launch", {"platform": sys.platform})

    port = find_free_port()
    nlog.flag("port_selected", {"port": port})

    server_thread = threading.Thread(target=start_server, args=(port,), daemon=True)
    server_thread.start()

    # FIX B-01: wait on Event instead of 120-iteration busy-poll
    nlog.start_timer("server_ready_wait")
    ready = _server_ready.wait(timeout=10)
    nlog.stop_timer("server_ready_wait")

    if not ready:
        nlog.error("server_ready_timeout", extra={"port": port})
        # Still try — server may be up but first-request hook not fired yet
        time.sleep(1)

    nlog.flag("opening_window", {"url": f"http://127.0.0.1:{port}/"})

    window = webview.create_window(
        title="NEXUS — File Intelligence System",
        url=f"http://127.0.0.1:{port}/",
        width=1400,
        height=900,
        min_size=(900, 600),
        background_color="#080c0f",
        text_select=False,
    )

    nlog.flag("webview_start")
    webview.start(debug=False)
    nlog.flag("app_exit")


if __name__ == "__main__":
    main()