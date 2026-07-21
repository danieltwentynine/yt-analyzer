# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — YouTube Analyzer (Windows .exe)

Build:
    venv\\Scripts\\python.exe -m PyInstaller --noconfirm --clean yt-analyzer.spec

Output (one-folder build):
    dist/YouTube Analyzer/YouTube Analyzer.exe

Optional environment variable:
    YTA_FFMPEG   full path to ffmpeg.exe to bundle (default: auto-detect on PATH)
"""
import os
import shutil

from PyInstaller.utils.hooks import collect_all

APP_NAME = "YouTube Analyzer"

datas, binaries, hiddenimports = [], [], []

# Packages that ship data files or lazily-imported submodules PyInstaller
# cannot follow statically: whisper's model assets, yt-dlp's per-site
# extractors, numba/llvmlite's JIT libraries, tiktoken's C extension.
# (torch is covered by PyInstaller's built-in hook automatically.)
for pkg in ("whisper", "yt_dlp", "numba", "llvmlite", "tiktoken", "ollama"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# ── Bundle ffmpeg.exe so the .exe is self-contained ───────────────────
_ffmpeg = os.environ.get("YTA_FFMPEG") or shutil.which("ffmpeg")
if _ffmpeg and os.path.exists(_ffmpeg):
    binaries += [(_ffmpeg, ".")]
    print(f"[spec] bundling ffmpeg: {_ffmpeg}")
else:
    print("[spec] WARNING: ffmpeg not found — the .exe will need ffmpeg on the user's PATH")

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["pyi_rthooks/no_console.py"],
    excludes=[
        "triton",          # GPU-only; not available/needed on Windows
        "tensorflow",
        "matplotlib",
        "PyQt5", "PyQt6", "PySide2", "PySide6",
        "pytest", "IPython", "notebook",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # GUI app — no console window
    disable_windowed_traceback=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)
