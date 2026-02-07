# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for FiscFox Desktop Application

Build commands:
    pyinstaller fiscfox.spec                    # Standard build
    pyinstaller fiscfox.spec --clean            # Clean build

Output:
    dist/FiscFox (Linux)
    dist/FiscFox.app (macOS)
    dist/FiscFox.exe (Windows)
"""

import platform
from pathlib import Path

# Paths
ROOT = Path(SPECPATH)
SRC = ROOT / "src"

# Platform-specific settings
system = platform.system()

if system == "Darwin":
    icon_file = ROOT / "assets" / "icon.icns"
    bundle_name = "FiscFox"
elif system == "Windows":
    icon_file = ROOT / "assets" / "icon.ico"
    bundle_name = "FiscFox"
else:
    icon_file = ROOT / "assets" / "icon.png"
    bundle_name = "fiscfox"

# Use default icon if custom not found
icon = str(icon_file) if icon_file.exists() else None

# Hidden imports that PyInstaller might miss
hidden_imports = [
    # FastAPI and dependencies
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "fastapi",
    "starlette",
    "pydantic",
    "jinja2",
    "aiosqlite",
    # WebView backends
    "webview",
    # Linux GTK/WebKit backend (pywebview)
    "webview.platforms.gtk",
    "gi",
    "gi.repository.Gtk",
    "gi.repository.Gdk",
    "gi.repository.GLib",
    "gi.repository.WebKit2",
]

# Data files to include
datas = [
    # Templates
    (str(SRC / "web" / "templates"), "src/web/templates"),
    # Static assets (CSS, JS, fonts, logos)
    (str(SRC / "web" / "static"), "src/web/static"),
    # Database schema
    (str(SRC / "db" / "schema.sql"), "src/db"),
    # Translations
    (str(SRC / "core" / "i18n.py"), "src/core"),
    # App icons
    (str(ROOT / "assets"), "assets"),
]

# Analysis
a = Analysis(
    ["desktop.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude dev/test dependencies
        "pytest",
        "mypy",
        "ruff",
        # Exclude unused tkinter
        "tkinter",
        "_tkinter",
    ],
    noarchive=False,
    optimize=1,
)

# Create single executable
pyz = PYZ(a.pure, a.zipped_data)

# Executable configuration
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=bundle_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)

# macOS app bundle
if system == "Darwin":
    app = BUNDLE(
        exe,
        name="FiscFox.app",
        icon=icon,
        bundle_identifier="com.fiscfox.app",
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleShortVersionString": "0.1.0",
            "CFBundleVersion": "1",
            "NSRequiresAquaSystemAppearance": False,  # Support dark mode
        },
    )
