# -*- mode: python ; coding: utf-8 -*-
"""
NEXUS Desktop — PyInstaller build spec
Produces a single-folder dist with NEXUS.exe
"""

import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect all hidden imports needed by Flask/SocketIO
hiddenimports = [
    'engineio',
    'engineio.async_drivers.threading',
    'socketio',
    'socketio.async_namespace',
    'flask_socketio',
    'flask',
    'werkzeug',
    'jinja2',
    'click',
    'itsdangerous',
    'chardet',
    'fitz',  # PyMuPDF
    'docx',
    'openpyxl',
    'pptx',
    'core.brain',
    'core.organizer',
    'core.parser',
]

# Data files to bundle
datas = [
    ('assets', 'assets'),
    ('core', 'core'),
]

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'pandas', 'scipy', 'PIL', 'tkinter', 'PyQt5', 'PyQt6'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NEXUS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,        # No console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,            # Add icon.ico here if you have one
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='NEXUS',
)
