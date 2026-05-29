#!/usr/bin/env python3
"""
YouTube Playlist Analyzer
Baixa áudios, transcreve com Whisper e gera resumo, análise e mapa mental via Claude API.
"""

import os
import json
import shutil
import time
import re
import subprocess
from pathlib import Path
from dotenv import load_dotenv
import ollama
import whisper

load_dotenv()

OUTPUT_DIR = Path("output")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "medium")  # tiny | base | small | medium | large
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "pt")


def ensure_ffmpeg() -> bool:
    """Add ffmpeg to PATH if missing. Returns True if ffmpeg is available after the check."""
    if shutil.which("ffmpeg"):
        return True
    candidates = [
        Path(r"C:\ffmpeg\bin"),
        Path(r"C:\ffmpeg\ffmpeg-master-latest-win64-gpl\bin"),
        Path(r"C:\Program Files\ffmpeg\bin"),
        Path(r"C:\Program Files (x86)\ffmpeg\bin"),
        Path.home() / "ffmpeg" / "bin",
        Path.home() / "AppData" / "Local" / "ffmpeg" / "bin",
    ]
    for p in candidates:
        if (p / "ffmpeg.exe").exists():
            os.environ["PATH"] = str(p) + os.pathsep + os.environ.get("PATH", "")
            print(f"ℹ️  ffmpeg encontrado em: {p}")
            return True
    print("⚠️  ffmpeg não encontrado. Instale o ffmpeg e adicione ao PATH.")
    print("    Download: https://ffmpeg.org/download.html")
    return False


def call_llm(prompt: str) -> str:
    response = ollama.chat(
        model=os.getenv("OLLAMA_MODEL", "mistral"),
        messages=[{"role": "user", "content": prompt}]
    )
    return response["message"]["content"]


# ─────────────────────────────────────────────
# UTILIDADES
# ─────────────────────────────────────────────

def sanitize_filename(name: str) -> str:
    """Remove caracteres inválidos para nomes de arquivo."""
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()[:80]


def clean_json_response(text: str) -> str:
    """Remove backticks e blocos de código que o modelo possa adicionar."""
    return re.sub(r"```(?:json)?", "", text).strip().rstrip("`")


# ─────────────────────────────────────────────
# ETAPA 1 — LISTAR PLAYLIST
# ─────────────────────────────────────────────

def get_playlist_videos(playlist_url: str) -> list[dict]:
    """Obtém a lista de vídeos da playlist via yt-dlp."""
    print("📋 Obtendo lista de vídeos da playlist...")
    result = subprocess.run(
        ["yt-dlp", "--flat-playlist", "-J", playlist_url],
        capture_output=True, text=True, check=True
    )
    data = json.loads(result.stdout)
    videos = []
    for i, entry in enumerate(data.get("entries", []), 1):
        videos.append({
            "index": i,
            "id": entry.get("id"),
            "title": entry.get("title", f"video_{i}"),
            "url": f"https://www.youtube.com/watch?v={entry.get('id')}"
        })
    print(f"✅ {len(videos)} vídeos encontrados.\n")
    return videos


# ─────────────────────────────────────────────
# ETAPA 2 — DOWNLOAD DO ÁUDIO
# ─────────────────────────────────────────────

def download_audio(video: dict, output_dir: Path) -> Path:
    """Baixa apenas o áudio do vídeo em MP3."""
    audio_path = output_dir / "audio.mp3"
    if audio_path.exists():
        print("  ⏩ Áudio já baixado, pulando...")
        return audio_path

    print("  ⬇️  Baixando áudio...")
    audio_template = output_dir / "audio"  # sem extensão — yt-dlp adiciona .mp3
    result = subprocess.run(
        [
            "yt-dlp",
            "-x", "--audio-format", "mp3",
            "-o", str(audio_template),
            "--no-playlist",
            video["url"],
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp falhou:\n{result.stderr.strip()}")
    return audio_path


# ─────────────────────────────────────────────
# ETAPA 3 — TRANSCRIÇÃO COM WHISPER
# ─────────────────────────────────────────────

def transcribe_audio(audio_path: Path, output_dir: Path) -> str:
    """Transcreve o áudio com Whisper (roda localmente)."""
    transcript_path = output_dir / "transcript.txt"
    if transcript_path.exists():
        print("  ⏩ Transcrição já existe, pulando...")
        return transcript_path.read_text(encoding="utf-8")

    print(f"  🎙️  Transcrevendo com Whisper (modelo: {WHISPER_MODEL})...")
    model = whisper.load_model(WHISPER_MODEL)
    result = model.transcribe(str(audio_path), language=WHISPER_LANGUAGE)
    transcript = result["text"]
    transcript_path.write_text(transcript, encoding="utf-8")
    return transcript


# ─────────────────────────────────────────────
# ETAPA 4 — RESUMO + ANÁLISE COM CLAUDE
# ─────────────────────────────────────────────

def generate_analysis(title: str, transcript: str, output_dir: Path) -> str:
    """Gera resumo e análise crítica com Claude."""
    analysis_path = output_dir / "resumo_analise.md"
    if analysis_path.exists():
        print("  ⏩ Análise já existe, pulando...")
        return analysis_path.read_text(encoding="utf-8")

    print("  🤖 Gerando resumo e análise com Ollama...")

    prompt = f"""Você é um analista especializado em síntese de conteúdo educacional e informativo.

Abaixo está a transcrição do vídeo: **{title}**

---
{transcript[:14000]}
---

Produza um documento Markdown bem estruturado com as seguintes seções:

## 📋 Resumo Executivo
3 a 5 parágrafos concisos cobrindo os pontos centrais do vídeo.

## 🎯 Pontos-Chave
Lista com os 7 a 10 insights ou ideias mais importantes apresentadas.

## 📊 Análise Crítica
Avaliação da qualidade das informações: pontos fortes, limitações, possíveis vieses, coerência dos argumentos.

## 💡 Conclusões e Aplicações Práticas
Como o conteúdo pode ser aplicado na prática. O que o espectador deve levar para a vida real.

## 🔗 Temas Relacionados para Aprofundamento
5 tópicos ou referências para quem quiser se aprofundar.
"""

    analysis = call_llm(prompt)
    analysis_path.write_text(analysis, encoding="utf-8")
    return analysis


# ─────────────────────────────────────────────
# ETAPA 5 — MAPA MENTAL EM JSON
# ─────────────────────────────────────────────

def generate_mindmap(title: str, transcript: str, output_dir: Path) -> dict:
    """Gera mapa mental hierárquico em JSON (compatível com XMind e Miro)."""
    mindmap_path = output_dir / "mapa_mental.json"
    if mindmap_path.exists():
        print("  ⏩ Mapa mental já existe, pulando...")
        return json.loads(mindmap_path.read_text(encoding="utf-8"))

    print("  🗺️  Gerando mapa mental com Ollama...")

    prompt = f"""Você é um especialista em organização visual do conhecimento.

Analise a transcrição do vídeo "{title}" e crie um mapa mental hierárquico completo.

Transcrição:
---
{transcript[:12000]}
---

Responda APENAS com JSON válido. Sem texto antes ou depois. Sem backticks. Sem markdown.

Use exatamente este formato:
{{
    "title": "{title}",
    "children": [
    {{
        "title": "Tema Principal 1",
        "children": [
        {{
            "title": "Subtópico 1.1",
            "children": [
                {{"title": "Detalhe 1.1.1", "children": []}}
            ]
        }},
        {{
            "title": "Subtópico 1.2",
            "children": []
        }}
        ]
    }}
    ]
}}

Regras obrigatórias:
- Entre 4 e 6 temas principais
- Máximo 3 níveis de profundidade
- Títulos concisos (no máximo 7 palavras)
- Cobrir os conceitos e argumentos mais importantes
- Todos os campos "children" presentes (use [] se não tiver filhos)
"""

    raw = clean_json_response(call_llm(prompt))

    try:
        mindmap = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  ⚠️  Erro ao parsear JSON do mapa mental: {e}")
        mindmap = {"title": title, "children": [], "error": str(e), "raw": raw}

    mindmap_path.write_text(json.dumps(mindmap, ensure_ascii=False, indent=2), encoding="utf-8")
    return mindmap


# ─────────────────────────────────────────────
# ORQUESTRADOR
# ─────────────────────────────────────────────

def process_video(video: dict, index: int, total: int):
    """Processa um vídeo completo passo a passo."""
    print(f"\n{'═'*60}")
    print(f"🎬 [{index}/{total}] {video['title']}")
    print(f"{'═'*60}")

    folder_name = f"{index:02d}_{sanitize_filename(video['title'])}"
    video_dir = OUTPUT_DIR / folder_name
    video_dir.mkdir(parents=True, exist_ok=True)

    # Salva metadados do vídeo
    meta_path = video_dir / "meta.json"
    if not meta_path.exists():
        meta_path.write_text(json.dumps(video, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        audio_path = download_audio(video, video_dir)
        transcript = transcribe_audio(audio_path, video_dir)
        generate_analysis(video["title"], transcript, video_dir)
        generate_mindmap(video["title"], transcript, video_dir)

        print(f"\n  ✅ Concluído com sucesso!")

    except Exception as e:
        print(f"\n  ❌ Erro: {e}")
        (video_dir / "error.txt").write_text(str(e), encoding="utf-8")


def main():
    print("╔══════════════════════════════════════════════╗")
    print("║      YouTube Playlist Analyzer — Claude      ║")
    print("╚══════════════════════════════════════════════╝\n")

    ensure_ffmpeg()
    playlist_url = input("🔗 Cole a URL da playlist do YouTube: ").strip()
    OUTPUT_DIR.mkdir(exist_ok=True)

    try:
        videos = get_playlist_videos(playlist_url)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
        print(f"❌ Erro ao obter playlist: {e}")
        return

    print(f"🚀 Iniciando processamento de {len(videos)} vídeo(s)...\n")

    for i, video in enumerate(videos, 1):
        process_video(video, i, len(videos))
        if i < len(videos):
            time.sleep(2)  # Pausa entre vídeos para não sobrecarregar as APIs

    print(f"\n{'═'*60}")
    print(f"🎉 Processamento concluído!")
    print(f"📁 Resultados salvos em: {OUTPUT_DIR.resolve()}")
    print(f"{'═'*60}")


if __name__ == "__main__":
    main()
