"""
NEXUS Desktop — Native Windows Application
Flask runs on a background thread, pywebview opens a real native window.
No browser needed. No web server exposed. Fully self-contained.
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

# Suppress Flask/werkzeug output
log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)

from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
import webview

from core.organizer import FileOrganizer
from core.brain import NexusBrain

# ─── Path helpers (works both dev and PyInstaller bundle) ─────────────────────

def resource_path(relative: str) -> str:
    """Get absolute path — works in dev and PyInstaller .exe"""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return os.path.join(meipass, relative)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative)


# ─── Flask App ────────────────────────────────────────────────────────────────

app = Flask(__name__, static_folder=resource_path("assets"))
app.config["SECRET_KEY"] = "nexus-desktop-local"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading", logger=False, engineio_logger=False)

brain = NexusBrain()

session = {
    "organizer": None,
    "plan": [],
    "status": "idle",
    "target": None,
}


def emit_fn(event, data):
    socketio.emit(event, data)


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
    return jsonify(brain.get_stats())


@app.route("/api/scan", methods=["POST"])
def scan():
    data = request.json or {}
    target = data.get("directory", "").strip()

    if not target:
        return jsonify({"error": "No directory provided"}), 400

    target_path = Path(target).expanduser().resolve()
    if not target_path.exists():
        return jsonify({"error": f"Directory not found: {target}"}), 404
    if not target_path.is_dir():
        return jsonify({"error": "Path is not a directory"}), 400

    session["target"] = str(target_path)
    session["status"] = "scanning"
    session["plan"] = []
    session["organizer"] = None

    def run():
        org = FileOrganizer(str(target_path), emit_fn=emit_fn)
        session["organizer"] = org
        session["plan"] = org.scan()
        session["status"] = "scanned"

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "scanning", "directory": str(target_path)})


@app.route("/api/execute", methods=["POST"])
def execute():
    if not session.get("organizer"):
        return jsonify({"error": "No scan has been run yet"}), 400
    if session["status"] not in ("scanned", "done"):
        return jsonify({"error": "Scan still running"}), 400

    session["status"] = "executing"

    def run():
        organizer = session.get("organizer")
        if hasattr(organizer, "execute"):
            result = organizer.execute()
            session["status"] = "done"
            socketio.emit("done", result)

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "executing"})


@app.route("/api/plan")
def get_plan():
    return jsonify({
        "plan": session["plan"],
        "status": session["status"],
        "target": session["target"],
    })


@app.route("/api/tree")
def get_tree():
    organizer = session.get("organizer")
    if not hasattr(organizer, "get_tree"):
        target = request.args.get("dir", "")
        if target:
            p = Path(target).expanduser().resolve()
            if p.exists() and p.is_dir():
                return jsonify(FileOrganizer(str(p)).get_tree())
        return jsonify({"error": "No organizer active"}), 400
    return jsonify(organizer.get_tree())


@app.route("/api/correct", methods=["POST"])
def correct():
    data = request.json or {}
    brain.record_correction(
        data.get("file", ""), data.get("wrong_dest", ""), data.get("correct_dest", "")
    )
    return jsonify({"status": "ok"})


@app.route("/api/reset", methods=["POST"])
def reset():
    session.update({"organizer": None, "plan": [], "status": "idle", "target": None})
    return jsonify({"status": "reset"})


@app.route("/api/browse", methods=["POST"])
def browse():
    """Open native folder picker dialog and return selected path."""
    dialog_type = getattr(webview, "FileDialog", webview)
    target_dialog = getattr(dialog_type, "FOLDER", getattr(webview, "FOLDER_DIALOG", 2))
    result = webview.windows[0].create_file_dialog(target_dialog)
    if result and len(result) > 0:
        return jsonify({"path": result[0]})
    return jsonify({"path": None})


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@socketio.on("connect")
def on_connect():
    emit("connected", {
        "status": session["status"],
        "engine": "ollama" if brain.ollama_available else "local-semantic",
    })


# ─── Server startup ───────────────────────────────────────────────────────────

def find_free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(port):
    socketio.run(app, host="127.0.0.1", port=port, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main():
    # Required for Windows PyInstaller built executables to not spawn infinite processes 
    # or freeze when using threads/multiprocessing
    multiprocessing.freeze_support()

    port = find_free_port()

    # Start Flask on background thread
    server_thread = threading.Thread(
        target=start_server, args=(port,), daemon=True
    )
    server_thread.start()

    # Wait for server to be ready
    for _ in range(120):
        try:
            import urllib.request
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
            break
        except Exception:
            time.sleep(0.1)

    # Open native window
    window = webview.create_window(
        title="NEXUS — File Intelligence System",
        url=f"http://127.0.0.1:{port}/",
        width=1400,
        height=900,
        min_size=(900, 600),
        background_color="#080c0f",
        text_select=False,
    )

    webview.start(debug=False)


if __name__ == "__main__":
    main()
