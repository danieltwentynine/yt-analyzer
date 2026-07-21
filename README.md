# YouTube Analyzer

Automatically downloads YouTube videos, transcribes them with Whisper, and generates a **summary**, a **critical analysis**, and a **mind map in JSON** for each video — all running locally via Ollama, with no dependency on paid external APIs.

Available as a **graphical interface** (`app.py`) and as a **command-line script** (`pipeline.py`).

---

## Graphical interface (recommended)

```bash
python app.py
```

The interface walks you through four screens:

| Screen | Description |
| --- | --- |
| **Home** | Choose the mode: Single video, Playlist, Entire channel, or .txt file |
| **Config** | Paste the URL (or select the file), choose the Ollama model, and start |
| **Progress** | Overall progress bar + real-time log of each step |
| **Results** | List of processed videos with an "Open folder" button for each |

> `app.py` is the main entry point and calls the functions in `pipeline.py` internally.

---

## CLI (command line)

```bash
python pipeline.py
```

Paste the URL when prompted. Useful for automation or environments without a GUI.

---

## Windows executable (.exe)

Build a standalone Windows app (no Python required on the end user's machine):

```powershell
# 1. Create the virtual environment and install the runtime dependencies
py -3.14 -m venv venv
venv\Scripts\pip install -r requirements.txt

# 2. Build the executable
.\build.ps1        # or double-click build.bat
```

The result lands in `dist\YouTube Analyzer\`. **Distribute the whole folder** — the `.exe` depends on the files next to it, not just the `.exe` itself.

The build is driven by [`yt-analyzer.spec`](yt-analyzer.spec) (PyInstaller), which:

- Bundles PyTorch + Whisper, the yt-dlp extractors, numba/llvmlite, and the `ffmpeg.exe` found on PATH — the app is self-contained.
- Produces a ~2–3 GB folder (PyTorch is large; this is expected).

### What the end user still needs

The `.exe` embeds everything **except** Ollama, which is a separate server:

- Install [Ollama](https://ollama.com/download) and keep it running.
- Pull a model: `ollama pull mistral`.
- On the first analysis, Whisper automatically downloads the model weights (~1.5 GB for `medium`) to `~/.cache/whisper` — this requires internet the first time.

> Results are saved to an `output/` folder created **next to the `.exe`**.

---

## Output structure

After a run, the `output/` folder contains:

```text
output/
├── 01_Video-Title/
│   ├── meta.json             ← video metadata (title, URL, id)
│   ├── audio.mp3             ← downloaded audio
│   ├── transcript.txt        ← full transcript
│   ├── summary_analysis.md   ← summary + critical analysis (Markdown)
│   └── mind_map.json         ← hierarchical mind map (JSON)
├── 02_Another-Video/
│   └── ...
```

---

## Installation

### 1. Prerequisites

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/download.html) installed on the system (required by Whisper and yt-dlp)
- [Ollama](https://ollama.com) installed and running locally

**macOS:**

```bash
brew install ffmpeg
brew install ollama
```

**Linux (Ubuntu/Debian):**

```bash
sudo apt install ffmpeg
curl -fsSL https://ollama.com/install.sh | sh
```

**Windows:**
Download ffmpeg from <https://ffmpeg.org/download.html> and Ollama from <https://ollama.com/download>. Add ffmpeg to your PATH.

---

### 2. Pull an Ollama model

The default model is `mistral`. Pull it before running the pipeline:

```bash
ollama pull mistral
```

Other compatible models: `llama3`, `gemma2`, `phi3`. Any instruction-tuned model works.

---

### 3. Clone / copy the files

Place `app.py`, `pipeline.py`, `requirements.txt`, and `.env` in a folder.

---

### 4. Create the virtual environment and install dependencies

```bash
python -m venv venv

# Activate (macOS/Linux):
source venv/bin/activate

# Activate (Windows):
venv\Scripts\activate

pip install -r requirements.txt
```

---

### 5. Configure the environment variables

Create a `.env` file in the project root with the variables below (all optional — the values shown are the defaults):

```env
WHISPER_MODEL=medium
WHISPER_LANGUAGE=pt
OLLAMA_MODEL=mistral
```

> `WHISPER_LANGUAGE` is the spoken language of the videos you transcribe (e.g. `en`, `pt`, `es`). Leave it empty for automatic detection.

---

### 6. Run

Make sure Ollama is running (`ollama serve` or via the app), then:

**Graphical interface:**

```bash
python app.py
```

**Command line:**

```bash
python pipeline.py
```

Paste the URL when prompted. Examples of supported URLs:

```text
https://www.youtube.com/watch?v=xxxxxxxxxxx          # single video
https://www.youtube.com/playlist?list=PLxxxxxxxxxxxx # playlist
https://www.youtube.com/@channel/videos              # entire channel
```

---

## Importing the mind map

### XMind

1. Open XMind
2. File → Import → JSON (or use xmind-cli to convert)
3. Select the `mind_map.json` file

### Miro

1. Create a new board
2. Import → JSON
3. Select the `mind_map.json` file

### Markmap (quick visualization in the browser)

1. Go to <https://markmap.js.org/repl>
2. Paste the contents of `summary_analysis.md` and visualize it as a mind map

---

## Performance

| Situation | Recommended Whisper Model |
| --- | --- |
| Short videos / quick test | `tiny` or `base` |
| General use / good balance | `medium` (default) |
| Maximum accuracy | `large` |

| Situation | Recommended Ollama Model |
| --- | --- |
| Limited hardware (RAM < 8GB) | `phi3` or `gemma2:2b` |
| General use | `mistral` (default) |
| Maximum quality | `llama3` or `gemma2` |

> The Whisper model is downloaded automatically on the first run (~1.5GB for `medium`).
> The Ollama model must be pulled manually with `ollama pull <model>`.

---

## Automatic resume

The script **does not reprocess** files that already exist. If a run is interrupted, just run it again and it continues where it left off.

---

## Troubleshooting

**Video download error (yt-dlp)**
yt-dlp is used as a **Python library** (installed via `requirements.txt`), not as an external command. If a download fails, update it:

```bash
pip install -U yt-dlp
```

**`ffmpeg not found`**
Install ffmpeg following the instructions above. In the executable (`.exe`) ffmpeg is already bundled.

**`ollama: connection refused`**
The Ollama server is not running. Run `ollama serve` in another terminal or open the Ollama app.

**Model not found**

```bash
ollama pull mistral
```

Or set a different model in `.env` with `OLLAMA_MODEL=model-name`.

---

## Changelog

### English migration

- The entire project — GUI, console/log messages, comments, and the LLM prompts — is now in **English**. The generated `summary_analysis.md` / `mind_map.json` are produced in English.
- Output files were renamed: `resumo_analise.md` → `summary_analysis.md`, `mapa_mental.json` → `mind_map.json`.

### Windows executable (`.exe`) support

- New **PyInstaller** build — [`yt-analyzer.spec`](yt-analyzer.spec), [`build.ps1`](build.ps1), [`build.bat`](build.bat), and [`requirements-build.txt`](requirements-build.txt) — that packages the app into a standalone `dist\YouTube Analyzer\` folder. See the [Windows executable (.exe)](#windows-executable-exe) section.
- `ffmpeg.exe` is **bundled automatically** at build time (from the build machine's PATH) and located at runtime — the end user does not need to install ffmpeg.
- A runtime hook (`pyi_rthooks/no_console.py`) **suppresses the console windows** that used to flash on every ffmpeg call (download/transcription).

### yt-dlp via the Python API (instead of an external command)

- `pipeline.py` and `app.py` now use `yt_dlp` as a **library** (`yt_dlp.YoutubeDL`), no longer `subprocess.run(["yt-dlp", ...])`. This makes downloads work inside the `.exe`, where there is no `yt-dlp` command on PATH.
- New `pipeline.get_video_info()` helper centralizes single-video metadata extraction (used by the **Single video** and **.txt file** modes).

### Packaging-aware paths

- The `output/` folder is created **next to the executable** (or the project root when running via Python), instead of depending on the current working directory.
- Automatic ffmpeg discovery: system PATH → binary bundled in the build.

### `.gitignore`

- Now ignores the PyInstaller build artifacts (`/build`, `/dist`).
