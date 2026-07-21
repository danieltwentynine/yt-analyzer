#!/usr/bin/env python3
"""
YouTube Playlist Analyzer
Downloads audio, transcribes it with Whisper and generates a summary, analysis
and mind map for each video via Ollama.
"""

import os
import sys
import json
import shutil
import re
from pathlib import Path
from dotenv import load_dotenv
import ollama
import whisper
import yt_dlp

load_dotenv()


# ─────────────────────────────────────────────
# PATHS (aware of PyInstaller packaging)
# ─────────────────────────────────────────────

def app_base_dir() -> Path:
    """Application base directory (next to the .exe when packaged)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def _bundle_dir() -> Path:
    """Folder where PyInstaller extracts data/binaries (ffmpeg, assets)."""
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) if meipass else app_base_dir()


OUTPUT_DIR = app_base_dir() / "output"
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "medium")  # tiny | base | small | medium | large
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "pt")


# ─────────────────────────────────────────────
# FFMPEG
# ─────────────────────────────────────────────

def _find_ffmpeg() -> str | None:
    """Locate ffmpeg: the system PATH or the binary bundled with the app."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    for cand in (
        _bundle_dir() / "ffmpeg.exe",
        _bundle_dir() / "ffmpeg" / "bin" / "ffmpeg.exe",
        app_base_dir() / "ffmpeg.exe",
    ):
        if cand.exists():
            return str(cand)
    return None


def _ffmpeg_location() -> str | None:
    """ffmpeg folder to pass to yt-dlp (the ffmpeg_location option)."""
    ffmpeg = _find_ffmpeg()
    return str(Path(ffmpeg).parent) if ffmpeg else None


def ensure_ffmpeg() -> bool:
    """Ensure ffmpeg is reachable; add the bundled binary to PATH."""
    ffmpeg = _find_ffmpeg()
    if ffmpeg:
        # Prepend to PATH so Whisper (which calls ffmpeg via subprocess) finds it.
        ffmpeg_dir = str(Path(ffmpeg).parent)
        if ffmpeg_dir not in os.environ.get("PATH", "").split(os.pathsep):
            os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
        return True
    print("⚠️  ffmpeg not found. Install ffmpeg and add it to your PATH.")
    print("    Download: https://ffmpeg.org/download.html")
    return False


# ─────────────────────────────────────────────
# YT-DLP (Python API — works when packaged, no PATH command required)
# ─────────────────────────────────────────────

def _ydl(opts: dict) -> "yt_dlp.YoutubeDL":
    """Create a YoutubeDL with default options + the ffmpeg location."""
    base = {"quiet": True, "no_warnings": True, "noprogress": True}
    base.update(opts)
    loc = _ffmpeg_location()
    if loc:
        base.setdefault("ffmpeg_location", loc)
    return yt_dlp.YoutubeDL(base)


def get_video_info(url: str, index: int = 1) -> dict:
    """Extract metadata for a single video, without downloading."""
    with _ydl({"skip_download": True, "noplaylist": True}) as ydl:
        d = ydl.extract_info(url, download=False)
    return {
        "index": index,
        "id": d.get("id"),
        "title": d.get("title") or f"video_{index}",
        "url": url,
    }


def call_llm(prompt: str) -> str:
    response = ollama.chat(
        model=os.getenv("OLLAMA_MODEL", "mistral"),
        messages=[{"role": "user", "content": prompt}]
    )
    return response["message"]["content"]


# ─────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────

def sanitize_filename(name: str) -> str:
    """Remove characters that are invalid in file names."""
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()[:80]


def clean_json_response(text: str) -> str:
    """Strip backticks and code fences the model might add."""
    return re.sub(r"```(?:json)?", "", text).strip().rstrip("`")


# ─────────────────────────────────────────────
# STEP 1 — LIST PLAYLIST
# ─────────────────────────────────────────────

def get_playlist_videos(playlist_url: str) -> list[dict]:
    """Get the list of videos from the playlist/channel via yt-dlp (Python API)."""
    print("📋 Fetching the list of videos from the playlist...")
    with _ydl({"extract_flat": True, "skip_download": True}) as ydl:
        data = ydl.extract_info(playlist_url, download=False)

    videos = []
    for i, entry in enumerate(data.get("entries") or [], 1):
        vid = entry.get("id")
        videos.append({
            "index": i,
            "id": vid,
            "title": entry.get("title") or f"video_{i}",
            "url": f"https://www.youtube.com/watch?v={vid}" if vid else entry.get("url"),
        })
    print(f"✅ {len(videos)} videos found.\n")
    return videos


# ─────────────────────────────────────────────
# STEP 2 — DOWNLOAD AUDIO
# ─────────────────────────────────────────────

def download_audio(video: dict, output_dir: Path) -> Path:
    """Download only the video's audio as MP3 (via the yt-dlp API)."""
    audio_path = output_dir / "audio.mp3"
    if audio_path.exists():
        print("  ⏩ Audio already downloaded, skipping...")
        return audio_path

    print("  ⬇️  Downloading audio...")
    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(output_dir / "audio.%(ext)s"),
        "noplaylist": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
        }],
    }
    try:
        with _ydl(opts) as ydl:
            ydl.download([video["url"]])
    except yt_dlp.utils.DownloadError as e:
        raise RuntimeError(f"yt-dlp failed: {e}") from e

    if not audio_path.exists():
        raise RuntimeError("yt-dlp did not produce the audio.mp3 file.")
    return audio_path


# ─────────────────────────────────────────────
# STEP 3 — TRANSCRIBE WITH WHISPER
# ─────────────────────────────────────────────

def transcribe_audio(audio_path: Path, output_dir: Path) -> str:
    """Transcribe the audio with Whisper (runs locally)."""
    transcript_path = output_dir / "transcript.txt"
    if transcript_path.exists():
        print("  ⏩ Transcript already exists, skipping...")
        return transcript_path.read_text(encoding="utf-8")

    print(f"  🎙️  Transcribing with Whisper (model: {WHISPER_MODEL})...")
    model = whisper.load_model(WHISPER_MODEL)
    result = model.transcribe(str(audio_path), language=WHISPER_LANGUAGE)
    transcript = result["text"]
    transcript_path.write_text(transcript, encoding="utf-8")
    return transcript


# ─────────────────────────────────────────────
# STEP 4 — SUMMARY + ANALYSIS WITH OLLAMA
# ─────────────────────────────────────────────

def generate_analysis(title: str, transcript: str, output_dir: Path) -> str:
    """Generate a summary and critical analysis with Ollama."""
    analysis_path = output_dir / "summary_analysis.md"
    if analysis_path.exists():
        print("  ⏩ Analysis already exists, skipping...")
        return analysis_path.read_text(encoding="utf-8")

    print("  🤖 Generating summary and analysis with Ollama...")

    prompt = f"""You are an analyst specialized in synthesizing educational and informative content.

Below is the transcript of the video: **{title}**

---
{transcript[:14000]}
---

Produce a well-structured Markdown document with the following sections:

## 📋 Executive Summary
3 to 5 concise paragraphs covering the core points of the video.

## 🎯 Key Points
A list of the 7 to 10 most important insights or ideas presented.

## 📊 Critical Analysis
An assessment of the quality of the information: strengths, limitations, possible biases, and coherence of the arguments.

## 💡 Conclusions and Practical Applications
How the content can be applied in practice. What the viewer should take away for real life.

## 🔗 Related Topics for Further Study
5 topics or references for anyone who wants to dive deeper.
"""

    analysis = call_llm(prompt)
    analysis_path.write_text(analysis, encoding="utf-8")
    return analysis


# ─────────────────────────────────────────────
# STEP 5 — MIND MAP AS JSON
# ─────────────────────────────────────────────

def generate_mindmap(title: str, transcript: str, output_dir: Path) -> dict:
    """Generate a hierarchical mind map as JSON (compatible with XMind and Miro)."""
    mindmap_path = output_dir / "mind_map.json"
    if mindmap_path.exists():
        print("  ⏩ Mind map already exists, skipping...")
        return json.loads(mindmap_path.read_text(encoding="utf-8"))

    print("  🗺️  Generating mind map with Ollama...")

    prompt = f"""You are an expert in visual knowledge organization.

Analyze the transcript of the video "{title}" and create a complete hierarchical mind map.

Transcript:
---
{transcript[:12000]}
---

Respond ONLY with valid JSON. No text before or after. No backticks. No markdown.

Use exactly this format:
{{
    "title": "{title}",
    "children": [
    {{
        "title": "Main Theme 1",
        "children": [
        {{
            "title": "Subtopic 1.1",
            "children": [
                {{"title": "Detail 1.1.1", "children": []}}
            ]
        }},
        {{
            "title": "Subtopic 1.2",
            "children": []
        }}
        ]
    }}
    ]
}}

Mandatory rules:
- Between 4 and 6 main themes
- At most 3 levels of depth
- Concise titles (7 words maximum)
- Cover the most important concepts and arguments
- All "children" fields present (use [] when there are no children)
"""

    raw = clean_json_response(call_llm(prompt))

    try:
        mindmap = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  ⚠️  Error parsing the mind map JSON: {e}")
        mindmap = {"title": title, "children": [], "error": str(e), "raw": raw}

    mindmap_path.write_text(json.dumps(mindmap, ensure_ascii=False, indent=2), encoding="utf-8")
    return mindmap


# ─────────────────────────────────────────────
# ORCHESTRATOR
# ─────────────────────────────────────────────

def process_video(video: dict, index: int, total: int) -> Path:
    """Process one full video step by step. Returns the output folder."""
    print(f"\n{'═'*60}")
    print(f"🎬 [{index}/{total}] {video['title']}")
    print(f"{'═'*60}")

    folder_name = f"{video['index']:02d}_{sanitize_filename(video['title'])}"
    video_dir = OUTPUT_DIR / folder_name
    video_dir.mkdir(parents=True, exist_ok=True)

    # Save the video metadata
    meta_path = video_dir / "meta.json"
    if not meta_path.exists():
        meta_path.write_text(json.dumps(video, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        audio_path = download_audio(video, video_dir)
        transcript = transcribe_audio(audio_path, video_dir)
        generate_analysis(video["title"], transcript, video_dir)
        generate_mindmap(video["title"], transcript, video_dir)

        print(f"\n  ✅ Completed successfully!")

    except Exception as e:
        print(f"\n  ❌ Error: {e}")
        (video_dir / "error.txt").write_text(str(e), encoding="utf-8")

    return video_dir


def main():
    print("╔══════════════════════════════════════════════╗")
    print("║      YouTube Playlist Analyzer — Ollama      ║")
    print("╚══════════════════════════════════════════════╝\n")

    ensure_ffmpeg()
    playlist_url = input("🔗 Paste the YouTube playlist URL: ").strip()
    OUTPUT_DIR.mkdir(exist_ok=True)

    try:
        videos = get_playlist_videos(playlist_url)
    except (yt_dlp.utils.DownloadError, json.JSONDecodeError) as e:
        print(f"❌ Error fetching the playlist: {e}")
        return

    print(f"🚀 Starting processing of {len(videos)} video(s)...\n")

    for i, video in enumerate(videos, 1):
        process_video(video, i, len(videos))

    print(f"\n{'═'*60}")
    print(f"🎉 Processing complete!")
    print(f"📁 Results saved to: {OUTPUT_DIR.resolve()}")
    print(f"{'═'*60}")


if __name__ == "__main__":
    main()
