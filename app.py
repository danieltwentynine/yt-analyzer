#!/usr/bin/env python3
"""YouTube Analyzer — Graphical interface for pipeline.py"""

import os
import sys
import json
import queue
import subprocess
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import pipeline

# ── Theme ─────────────────────────────────────────────────────────────
BG       = "#1e1e1e"
BG2      = "#252526"
BG3      = "#3c3c3c"
FG       = "#ffffff"
FG_DIM   = "#aaaaaa"
BLUE     = "#0078d4"
BLUE_HOV = "#005fa3"
RED      = "#c42b1c"
LOG_BG   = "#0d0d0d"
SEL_BG   = "#264f78"

FONT       = ("Segoe UI", 11)
FONT_TITLE = ("Segoe UI", 22, "bold")
FONT_MONO  = ("Consolas", 10)


def _btn(parent, text, command, bg=BLUE, fg=FG, **kw):
    kw.setdefault("padx", 16)
    kw.setdefault("pady", 8)
    return tk.Button(
        parent, text=text, command=command,
        bg=bg, fg=fg, activebackground=BLUE_HOV, activeforeground=fg,
        relief="flat", cursor="hand2", font=FONT,
        **kw,
    )


def _label(parent, text, **kw):
    return tk.Label(parent, text=text, bg=BG, fg=FG, font=FONT, **kw)


# ── Redirect pipeline's print() output to the GUI queue ───────────────
class _QueueStream:
    def __init__(self, q: queue.Queue):
        self._q = q

    def write(self, text: str):
        if text.strip():
            self._q.put(("log", text.rstrip()))

    def flush(self):
        pass


# ── Video-list helpers (modes not covered by pipeline.get_playlist_videos) ─
def _single_video(url: str) -> dict:
    r = subprocess.run(
        ["yt-dlp", "--no-playlist", "-j", url],
        capture_output=True, text=True, check=True,
    )
    d = json.loads(r.stdout)
    return {"index": 1, "id": d.get("id"),
            "title": d.get("title", "video_1"), "url": url}


def _videos_from_txt(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        urls = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    result = []
    for i, url in enumerate(urls, 1):
        try:
            r = subprocess.run(
                ["yt-dlp", "--no-playlist", "-j", url],
                capture_output=True, text=True, check=True,
            )
            d = json.loads(r.stdout)
            result.append({"index": i, "id": d.get("id"),
                            "title": d.get("title", f"video_{i}"), "url": url})
        except Exception:
            result.append({"index": i, "id": None,
                            "title": f"video_{i}", "url": url})
    return result


# ── Main application ──────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("YouTube Analyzer")
        self.geometry("860x640")
        self.minsize(720, 520)
        self.configure(bg=BG)

        self.mode      = tk.StringVar(value="video")
        self.url_var   = tk.StringVar()
        self.model_var = tk.StringVar(value="mistral")
        self.txt_path  = tk.StringVar()

        self._q:      queue.Queue    = queue.Queue()
        self._cancel: threading.Event = threading.Event()

        self._frames: dict[str, tk.Frame] = {}
        for name, cls in [
            ("home",     HomeFrame),
            ("config",   ConfigFrame),
            ("progress", ProgressFrame),
            ("results",  ResultsFrame),
        ]:
            f = cls(self)
            f.place(relx=0, rely=0, relwidth=1, relheight=1)
            self._frames[name] = f

        self.show("home")
        self.after(100, self._poll)

    # ── Navigation ──────────────────────────────────────────────────
    def show(self, name: str):
        self._frames[name].lift()

    # ── Analysis orchestration ───────────────────────────────────────
    def start_analysis(self):
        self._cancel.clear()
        self._frames["progress"].reset()
        self.show("progress")
        threading.Thread(
            target=self._run,
            args=(self.mode.get(), self.url_var.get().strip(),
                    self.model_var.get(), self.txt_path.get().strip()),
            daemon=True,
        ).start()

    def cancel(self):
        self._cancel.set()
        self._q.put(("log", "⚠️  Cancelamento solicitado — aguardando o vídeo atual terminar."))

    def _run(self, mode: str, url: str, model: str, txt: str):
        old = sys.stdout
        sys.stdout = _QueueStream(self._q)
        try:
            os.environ["OLLAMA_MODEL"] = model
            pipeline.OUTPUT_DIR.mkdir(exist_ok=True)

            # 1. Build video list
            self._q.put(("log", "🔍 Obtendo lista de vídeos..."))
            if mode == "video":
                videos = [_single_video(url)]
            elif mode in ("playlist", "channel"):
                videos = pipeline.get_playlist_videos(url)
            else:                                       # txt
                self._q.put(("log", f"📄 Lendo: {txt}"))
                videos = _videos_from_txt(txt)

            total = len(videos)
            self._q.put(("total", total))

            # 2. Process each video
            processed: list[tuple[str, Path]] = []
            for i, video in enumerate(videos, 1):
                if self._cancel.is_set():
                    self._q.put(("log", "🛑 Análise cancelada pelo usuário."))
                    break

                self._q.put(("log", f"\n{'─' * 52}"))
                self._q.put(("log", f"🎬 [{i}/{total}] {video['title']}"))

                folder = f"{video['index']:02d}_{pipeline.sanitize_filename(video['title'])}"
                vdir = pipeline.OUTPUT_DIR / folder
                vdir.mkdir(parents=True, exist_ok=True)

                meta = vdir / "meta.json"
                if not meta.exists():
                    meta.write_text(
                        json.dumps(video, ensure_ascii=False, indent=2), encoding="utf-8"
                    )

                try:
                    self._q.put(("log", "  ⬇️  Baixando áudio..."))
                    audio = pipeline.download_audio(video, vdir)

                    self._q.put(("log", "  🎙️  Transcrevendo..."))
                    transcript = pipeline.transcribe_audio(audio, vdir)

                    self._q.put(("log", "  🤖 Gerando análise..."))
                    pipeline.generate_analysis(video["title"], transcript, vdir)

                    self._q.put(("log", "  🗺️  Gerando mapa mental..."))
                    pipeline.generate_mindmap(video["title"], transcript, vdir)

                    self._q.put(("log", "  ✅ Concluído!"))
                    processed.append((video["title"], vdir))

                except Exception as exc:
                    self._q.put(("log", f"  ❌ Erro: {exc}"))
                    (vdir / "error.txt").write_text(str(exc), encoding="utf-8")
                    processed.append((video["title"], vdir))

                self._q.put(("progress", i))
                if i < total:
                    time.sleep(1)

            self._q.put(("done", processed))

        except Exception as exc:
            self._q.put(("log", f"❌ Erro fatal: {exc}"))
            self._q.put(("error", str(exc)))
        finally:
            sys.stdout = old

    # ── Queue polling (runs on main thread via after()) ─────────────
    def _poll(self):
        try:
            while True:
                kind, data = self._q.get_nowait()
                pf: ProgressFrame = self._frames["progress"]  # type: ignore[assignment]
                if kind in ("log", "total", "progress"):
                    pf.handle(kind, data)
                elif kind == "done":
                    self._frames["results"].populate(data)  # type: ignore[attr-defined]
                    self.show("results")
                elif kind == "error":
                    messagebox.showerror("Erro", data)
                    self.show("config")
        except queue.Empty:
            pass
        self.after(100, self._poll)


# ── Screen 1: Home ────────────────────────────────────────────────────
class HomeFrame(tk.Frame):
    _MODES = [
        ("Vídeo único",   "video"),
        ("Playlist",      "playlist"),
        ("Canal inteiro", "channel"),
        ("Arquivo .txt",  "txt"),
    ]

    def __init__(self, app: App):
        super().__init__(app, bg=BG)
        self._app = app

        tk.Label(self, text="YouTube Analyzer",
                    bg=BG, fg=FG, font=("Segoe UI", 28, "bold")).pack(pady=(90, 10))
        tk.Label(self, text="Selecione o modo de análise",
                    bg=BG, fg=FG_DIM, font=("Segoe UI", 13)).pack(pady=(0, 56))

        row = tk.Frame(self, bg=BG)
        row.pack()
        for label, mode in self._MODES:
            _btn(row, label, lambda m=mode: self._go(m), width=14).pack(side="left", padx=10)

    def _go(self, mode: str):
        self._app.mode.set(mode)
        self._app._frames["config"].refresh(mode)   # type: ignore[attr-defined]
        self._app.show("config")


# ── Screen 2: Config ──────────────────────────────────────────────────
class ConfigFrame(tk.Frame):
    _LABELS = {
        "video":   "Vídeo único",
        "playlist": "Playlist",
        "channel": "Canal inteiro",
        "txt":     "Arquivo .txt",
    }

    def __init__(self, app: App):
        super().__init__(app, bg=BG)
        self._app = app

        self._title = tk.Label(self, bg=BG, fg=FG, font=FONT_TITLE)
        self._title.pack(pady=(60, 40))

        # ── Input area (swapped per mode) ────────────────────────────
        self._input_area = tk.Frame(self, bg=BG)
        self._input_area.pack(fill="x", padx=80)

        # URL widget
        self._url_frame = tk.Frame(self._input_area, bg=BG)
        _label(self._url_frame, "URL:").pack(anchor="w")
        self._url_entry = tk.Entry(
            self._url_frame, textvariable=app.url_var,
            bg=BG3, fg=FG, insertbackground=FG, relief="flat", font=FONT,
        )
        self._url_entry.pack(fill="x", ipady=7, pady=(4, 0))

        # File widget
        self._file_frame = tk.Frame(self._input_area, bg=BG)
        _label(self._file_frame, "Arquivo .txt:").pack(anchor="w")
        file_row = tk.Frame(self._file_frame, bg=BG)
        file_row.pack(fill="x", pady=(4, 0))
        tk.Entry(file_row, textvariable=app.txt_path,
                    bg=BG3, fg=FG, insertbackground=FG,
                    relief="flat", font=FONT).pack(side="left", fill="x", expand=True, ipady=7)
        _btn(file_row, "Escolher…", self._pick,
                padx=10, pady=5).pack(side="left", padx=(8, 0))

        # Default: show URL input
        self._url_frame.pack(fill="x")

        # ── Model selector ───────────────────────────────────────────
        model_area = tk.Frame(self, bg=BG)
        model_area.pack(fill="x", padx=80, pady=(24, 0))
        _label(model_area, "Modelo Ollama:").pack(anchor="w")

        style = ttk.Style()
        style.theme_use("clam")
        for name, cfg in [
            ("D.TCombobox", dict(fieldbackground=BG3, background=BG3, foreground=FG,
                                    selectbackground=SEL_BG, selectforeground=FG,
                                    arrowcolor=FG, bordercolor=BG2)),
            ("B.Horizontal.TProgressbar", dict(troughcolor=BG3, background=BLUE,
                                                bordercolor=BG, lightcolor=BLUE,
                                                darkcolor=BLUE, thickness=18)),
        ]:
            style.configure(name, **cfg)
        style.map("D.TCombobox",
                    fieldbackground=[("readonly", BG3)],
                    foreground=[("readonly", FG)],
                    selectbackground=[("readonly", SEL_BG)])

        self._cb = ttk.Combobox(
            model_area, textvariable=app.model_var,
            values=["mistral", "llama3.2", "llama3", "gemma2", "phi3"],
            state="readonly", style="D.TCombobox", font=FONT, width=22,
        )
        self._cb.pack(anchor="w", pady=(4, 0))

        # ── Buttons ───────────────────────────────────────────────────
        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack(pady=(40, 0))
        _btn(btn_row, "← Voltar", lambda: app.show("home"),
                bg=BG2).pack(side="left", padx=8)
        _btn(btn_row, "Iniciar análise", self._start).pack(side="left", padx=8)

    def refresh(self, mode: str):
        self._title.config(text=self._LABELS.get(mode, ""))
        self._url_frame.pack_forget()
        self._file_frame.pack_forget()
        if mode == "txt":
            self._file_frame.pack(fill="x")
        else:
            self._url_frame.pack(fill="x")

    def _pick(self):
        p = filedialog.askopenfilename(
            title="Selecionar arquivo de URLs",
            filetypes=[("Texto", "*.txt"), ("Todos os arquivos", "*.*")],
        )
        if p:
            self._app.txt_path.set(p)

    def _start(self):
        mode = self._app.mode.get()
        if mode == "txt":
            if not self._app.txt_path.get().strip():
                messagebox.showwarning("Atenção", "Selecione um arquivo .txt.")
                return
        else:
            if not self._app.url_var.get().strip():
                messagebox.showwarning("Atenção", "Cole uma URL antes de continuar.")
                return
        self._app.start_analysis()


# ── Screen 3: Progress ────────────────────────────────────────────────
class ProgressFrame(tk.Frame):
    def __init__(self, app: App):
        super().__init__(app, bg=BG)
        self._app  = app
        self._total = 0

        tk.Label(self, text="Processando…",
                    bg=BG, fg=FG, font=FONT_TITLE).pack(pady=(40, 24))

        # Progress bar
        pb_area = tk.Frame(self, bg=BG)
        pb_area.pack(fill="x", padx=60)

        self._lbl = tk.Label(pb_area, text="0 / ? vídeos", bg=BG, fg=FG_DIM, font=FONT)
        self._lbl.pack(anchor="e")

        self._bar = ttk.Progressbar(
            pb_area, style="B.Horizontal.TProgressbar",
            orient="horizontal", mode="determinate",
        )
        self._bar.pack(fill="x", pady=(4, 0))

        # Real-time log
        log_area = tk.Frame(self, bg=BG)
        log_area.pack(fill="both", expand=True, padx=60, pady=(20, 0))

        self._log = tk.Text(
            log_area, bg=LOG_BG, fg=FG, insertbackground=FG,
            relief="flat", font=FONT_MONO, state="disabled", wrap="word",
        )
        sb = tk.Scrollbar(log_area, command=self._log.yview, bg=BG2, troughcolor=BG, relief="flat")
        self._log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._log.pack(side="left", fill="both", expand=True)

        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack(pady=(16, 24))
        _btn(btn_row, "Cancelar", app.cancel, bg=RED).pack(side="left", padx=8)
        _btn(btn_row, "← Menu", self._back, bg=BG2).pack(side="left", padx=8)

    def _back(self):
        self._app.cancel()
        self._app.show("home")

    def reset(self):
        self._total = 0
        self._bar["value"]   = 0
        self._bar["maximum"] = 1
        self._lbl.config(text="0 / ? vídeos")
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")

    def handle(self, kind: str, data):
        if kind == "log":
            self._log.config(state="normal")
            self._log.insert("end", data + "\n")
            self._log.see("end")
            self._log.config(state="disabled")
        elif kind == "total":
            self._total          = data
            self._bar["maximum"] = data or 1
            self._lbl.config(text=f"0 / {data} vídeos")
        elif kind == "progress":
            self._bar["value"] = data
            self._lbl.config(text=f"{data} / {self._total} vídeos")


# ── Screen 4: Results ─────────────────────────────────────────────────
class ResultsFrame(tk.Frame):
    def __init__(self, app: App):
        super().__init__(app, bg=BG)
        self._app = app

        tk.Label(self, text="Análise concluída!", bg=BG, fg=FG, font=FONT_TITLE).pack(pady=(40, 6))
        self._count = tk.Label(self, bg=BG, fg=FG_DIM, font=FONT)
        self._count.pack(pady=(0, 20))

        # Scrollable list of videos
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True, padx=60)

        self._canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        sb = tk.Scrollbar(outer, orient="vertical", command=self._canvas.yview, bg=BG2, troughcolor=BG, relief="flat")
        self._canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._inner  = tk.Frame(self._canvas, bg=BG)
        self._win_id = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")

        self._inner.bind("<Configure>", lambda e: self._canvas.configure(
            scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>", lambda e: self._canvas.itemconfig(
            self._win_id, width=e.width))
        # Mouse-wheel scroll (Windows)
        self._canvas.bind("<MouseWheel>", lambda e: self._canvas.yview_scroll(int(-1 * e.delta / 120), "units"))

        _btn(self, "Nova análise", lambda: app.show("home")).pack(pady=(16, 24))

    def populate(self, items: list[tuple[str, Path]]):
        for w in self._inner.winfo_children():
            w.destroy()

        self._count.config(text=f"{len(items)} vídeo(s) processado(s)")

        for title, path in items:
            row = tk.Frame(self._inner, bg=BG2, pady=8)
            row.pack(fill="x", padx=4, pady=4)

            short = title if len(title) <= 68 else title[:65] + "…"
            tk.Label(row, text=short, bg=BG2, fg=FG,
                font=FONT, anchor="w").pack(side="left", padx=12, fill="x", expand=True)

            _btn(row, "Abrir pasta", lambda p=path: self._open(p),
                font=("Segoe UI", 10), padx=10, pady=4).pack(side="right", padx=12)

    @staticmethod
    def _open(path: Path):
        resolved = str(path.resolve())
        if sys.platform == "win32":
            os.startfile(resolved)
        elif sys.platform == "darwin":
            subprocess.run(["open", resolved])
        else:
            subprocess.run(["xdg-open", resolved])


if __name__ == "__main__":
    App().mainloop()
