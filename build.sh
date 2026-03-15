#!/usr/bin/env bash
# NEXUS Desktop — macOS/Linux Build Script
# Produces a native app bundle
set -e

echo ""
echo "  ============================================="
echo "    NEXUS Desktop  Building app"
echo "  ============================================="
echo ""

# Venv
if [ ! -d ".venv" ]; then
    echo "[1/4] Creating virtual environment..."
    python3 -m venv .venv
fi
source .venv/bin/activate

echo "[2/4] Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "[3/4] Building executable..."
pyinstaller NEXUS.spec --clean --noconfirm

echo "[4/4] Done!"
echo ""
echo "  Output: dist/NEXUS/NEXUS"
echo "  On macOS, you can also run: open dist/NEXUS/NEXUS"
echo ""
