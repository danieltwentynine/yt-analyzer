"""PyInstaller runtime hook — suppress child-process console windows.

The GUI is built windowed (no console). Whisper and yt-dlp both shell out to
ffmpeg via subprocess; without this hook each call flashes a black console
window on screen. We default `creationflags` to CREATE_NO_WINDOW for any
subprocess that doesn't set it explicitly.
"""
import sys

if sys.platform == "win32":
    import subprocess

    _CREATE_NO_WINDOW = 0x08000000
    _orig_init = subprocess.Popen.__init__

    def _init(self, *args, **kwargs):
        if not kwargs.get("creationflags"):
            kwargs["creationflags"] = _CREATE_NO_WINDOW
        _orig_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = _init
