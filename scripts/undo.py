#!/usr/bin/env python3
"""
NEXUS Undo — reverse a NEXUS organization using the manifest.
Usage: python scripts/undo.py /path/to/organized/directory
"""
import sys, json, shutil
from pathlib import Path

def undo(directory):
    manifest_path = Path(directory) / ".nexus" / "manifest.json"
    if not manifest_path.exists():
        print(f"❌  No manifest found at {manifest_path}")
        sys.exit(1)
    with open(manifest_path) as f:
        manifest = json.load(f)
    actions = manifest.get("actions", [])
    if not actions:
        print("ℹ️  Nothing to undo.")
        sys.exit(0)
    print(f"📂  Organization from: {manifest['organized_at']}")
    print(f"🔁  Reversing {len(actions)} moves...\n")
    ok, fail = 0, 0
    for action in reversed(actions):
        src, dst = Path(action["to"]), Path(action["from"])
        if not src.exists():
            print(f"  ⚠️  Missing: {src.name}"); fail += 1; continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            print(f"  ↩  {src.name}"); ok += 1
        except Exception as e:
            print(f"  ❌  {src.name}: {e}"); fail += 1
    print(f"\n✅  Restored {ok}  ❌  Failed {fail}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/undo.py /path/to/directory")
        sys.exit(1)
    undo(sys.argv[1])
