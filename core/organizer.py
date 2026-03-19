"""
NEXUS Organizer — Scans directories, plans moves, and executes them.
Fully autonomous. Never deletes files. Never touches system paths.
"""

import os
import shutil
import json
from pathlib import Path
from datetime import datetime
from typing import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from core.brain import NexusBrain, is_protected_path
from core.parser import extract_text, get_file_metadata, is_binary_only, describe_binary

# Files/dirs to always skip
ALWAYS_SKIP = {
    ".git", ".svn", ".hg", "node_modules", "__pycache__", ".venv", "venv",
    ".env", ".tox", "dist", "build", ".next", ".nuxt", ".cargo", ".rustup",
    ".npm", ".yarn", "site-packages", ".DS_Store", "Thumbs.db", "desktop.ini",
    ".nexus"  # our own metadata dir
}

# Max file size to parse (10 MB)
MAX_PARSE_SIZE = 10 * 1024 * 1024


class FileOrganizer:
    """
    Main organizer class. Call `scan()` first to preview decisions,
    then `execute()` to apply them.
    """

    def __init__(self, target_dir: str, emit_fn: Callable = None, brain: "NexusBrain" = None):
        self.target_dir = Path(target_dir).resolve()
        self.brain = brain or NexusBrain()
        self.emit = emit_fn or (lambda event, data: None)
        self.plan = []  # List of planned moves
        self.log = []   # Execution log

    def _emit(self, event: str, data: dict):
        self.emit(event, data)

    def scan(self) -> list:
        """
        Phase 1: Scan directory tree, analyze each file, build a move plan.
        Returns list of planned actions without executing anything.
        """
        self.plan = []
        
        if is_protected_path(str(self.target_dir)):
            self._emit("error", {"message": f"🚫 Protected path: {self.target_dir}. Aborting."})
            return []

        self._emit("scan_start", {
            "directory": str(self.target_dir),
            "message": f"🔍 Scanning {self.target_dir}..."
        })

        all_files = self._collect_files()
        total = len(all_files)

        self._emit("scan_count", {"total": total, "message": f"Found {total} files to analyze"})

        with ThreadPoolExecutor(max_workers=1) as pool:
            for i, file_path in enumerate(all_files):
                try:
                    future = pool.submit(self._analyze_file, file_path)
                    plan_item = future.result(timeout=10)
                    if plan_item:
                        self.plan.append(plan_item)
                        self._emit("file_analyzed", {
                            "index": i + 1,
                            "total": total,
                            "file": file_path.name,
                            "destination": plan_item["destination_rel"],
                            "category": plan_item["category"],
                            "confidence": plan_item["confidence"],
                            "reasoning": plan_item["reasoning"],
                            "engine": plan_item.get("engine", "local")
                        })
                except FuturesTimeoutError:
                    self._emit("file_error", {"file": str(file_path), "error": "Analysis timed out (>10s) — skipped"})
                except Exception as e:
                    self._emit("file_error", {"file": str(file_path), "error": str(e)})

        # Summarize structure
        structure = self.brain.suggest_directory_structure(self.plan)
        self._emit("scan_complete", {
            "total_files": total,
            "plan_count": len(self.plan),
            "structure": structure,
            "message": f"✅ Analysis complete. {len(self.plan)} files planned."
        })

        return self.plan

    def execute(self) -> dict:
        """
        Phase 2: Execute the move plan.
        Creates directories, moves files, writes a manifest.
        """
        if not self.plan:
            return {"moved": 0, "errors": 0}

        moved = 0
        errors = 0
        created_dirs = set()

        self._emit("execute_start", {
            "total": len(self.plan),
            "message": "🚀 Starting file organization..."
        })

        for item in self.plan:
            try:
                src = Path(item["source"])
                dest = Path(item["destination"])

                if not src.exists():
                    continue

                # Create destination directory
                dest.parent.mkdir(parents=True, exist_ok=True)
                if str(dest.parent) not in created_dirs:
                    created_dirs.add(str(dest.parent))
                    self._emit("dir_created", {
                        "path": str(dest.parent.relative_to(self.target_dir))
                    })

                # Handle name collisions
                dest = self._resolve_collision(dest)

                # Move the file
                shutil.move(str(src), str(dest))
                moved += 1

                # Record decision
                self.brain.record_decision(
                    str(src), str(dest),
                    item["category"], item["reasoning"]
                )

                self._emit("file_moved", {
                    "file": src.name,
                    "from": str(src.parent.relative_to(self.target_dir)),
                    "to": str(dest.parent.relative_to(self.target_dir)),
                    "category": item["category"],
                })

                self.log.append({
                    "action": "moved",
                    "file": src.name,
                    "from": str(src),
                    "to": str(dest),
                    "category": item["category"],
                    "timestamp": datetime.now().isoformat()
                })

            except Exception as e:
                errors += 1
                self._emit("move_error", {"file": item.get("source", "?"), "error": str(e)})

        # Write manifest
        self._write_manifest()

        # Cleanup empty source directories
        self._cleanup_empty_dirs()

        # Flush learned decisions to disk in one write (Fix #4)
        self.brain.save_memory()

        result = {
            "moved": moved,
            "errors": errors,
            "dirs_created": len(created_dirs)
        }

        self._emit("execute_complete", {
            **result,
            "message": f"✅ Done! Moved {moved} files into {len(created_dirs)} directories."
        })

        return result

    def _collect_files(self) -> list:
        """Walk the directory tree and collect files to process."""
        files = []
        
        for root, dirs, filenames in os.walk(self.target_dir):
            root_path = Path(root)

            # Skip protected and ignored directories (modify dirs in-place to prune walk)
            dirs[:] = [
                d for d in dirs
                if d not in ALWAYS_SKIP
                and not d.startswith(".")
                and not is_protected_path(str(root_path / d))
            ]

            for filename in filenames:
                if filename.startswith(".") or filename in ALWAYS_SKIP:
                    continue
                file_path = root_path / filename
                # Don't re-organize already-organized files in subdirs we just created
                files.append(file_path)

        return files

    def _analyze_file(self, file_path: Path) -> dict | None:
        """Analyze a single file and return a planned move."""
        meta = get_file_metadata(str(file_path))
        ext = meta["extension"]
        size = meta["size_bytes"]

        # Extract content
        if is_binary_only(ext):
            content = describe_binary(str(file_path))
            content += " " + meta["name_hints"]
        elif size > MAX_PARSE_SIZE:
            content = meta["name_hints"]  # Too large, use filename only
        else:
            content = extract_text(str(file_path))
            if not content.strip():
                content = meta["name_hints"]

        # Combine content with filename hints for better signal
        full_signal = f"{meta['name_hints']} {content}"

        # Ask the brain
        result = self.brain.analyze_content(full_signal, meta["name"], ext)

        folder = result["suggested_folder"]

        # Build destination path
        if folder == "_bin":
            dest_dir = self.target_dir / "_bin"
        else:
            dest_dir = self.target_dir / folder

        dest = dest_dir / file_path.name

        # Don't move if already in the right place
        if file_path.parent == dest_dir:
            return None

        return {
            "source": str(file_path),
            "destination": str(dest),
            "destination_rel": str(dest.relative_to(self.target_dir)),
            "category": result["category"],
            "subcategory": result.get("subcategory"),
            "confidence": result["confidence"],
            "reasoning": result["reasoning"],
            "engine": result.get("engine", "local"),
            "filename": file_path.name,
        }

    def _resolve_collision(self, dest: Path) -> Path:
        """If destination file exists, add a numeric suffix."""
        if not dest.exists():
            return dest
        stem = dest.stem
        suffix = dest.suffix
        parent = dest.parent
        counter = 1
        while dest.exists():
            dest = parent / f"{stem}_{counter}{suffix}"
            counter += 1
        return dest

    def _cleanup_empty_dirs(self):
        """Remove empty directories left after moving files (not the root)."""
        for root, dirs, files in os.walk(self.target_dir, topdown=False):
            root_path = Path(root)
            if root_path == self.target_dir:
                continue
            try:
                if not any(root_path.iterdir()):
                    root_path.rmdir()
            except Exception:
                pass

    def _write_manifest(self):
        """Write a human-readable manifest of what was done."""
        manifest_path = self.target_dir / ".nexus" / "manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        
        manifest = {
            "organized_at": datetime.now().isoformat(),
            "target": str(self.target_dir),
            "total_moved": len(self.log),
            "actions": self.log
        }
        
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

    def get_tree(self) -> dict:
        """Return current directory tree as a nested dict for the dashboard."""
        def _build(path: Path, depth=0) -> dict:
            if depth > 4:
                return {}
            node = {"name": path.name, "type": "dir", "children": [], "file_count": 0}
            try:
                for item in sorted(path.iterdir()):
                    if item.name.startswith(".") or item.name in ALWAYS_SKIP:
                        continue
                    if item.is_dir():
                        child = _build(item, depth + 1)
                        node["children"].append(child)
                        node["file_count"] += child["file_count"]
                    else:
                        node["children"].append({
                            "name": item.name,
                            "type": "file",
                            "ext": item.suffix.lower()
                        })
                        node["file_count"] += 1
            except PermissionError:
                pass
            return node

        return _build(self.target_dir)
