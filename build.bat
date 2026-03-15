@echo off
:: NEXUS Desktop — Windows Build Script
:: Run this on Windows to produce NEXUS.exe
:: Requirements: Python 3.9+, pip

echo.
echo  =============================================
echo    NEXUS Desktop Building .exe
echo  =============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install from https://python.org
    pause & exit /b 1
)

:: Create venv if needed
if not exist ".venv" (
    echo [1/4] Creating virtual environment...
    python -m venv .venv
)

:: Activate
call .venv\Scripts\activate.bat

:: Install deps
echo [2/4] Installing dependencies...
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

:: Build
echo [3/4] Building executable...
pyinstaller NEXUS.spec --clean --noconfirm

echo [4/4] Done!
echo.
echo  Output: dist\NEXUS\NEXUS.exe
echo  Share the entire dist\NEXUS\ folder or zip it up.
echo.
pause
