#!/usr/bin/env python3
"""
YouTube Playlist Analyzer
Baixa áudios, transcreve com Whisper e gera resumo, análise e mapa mental via Claude API.
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
# CAMINHOS (cientes de empacotamento PyInstaller)
# ─────────────────────────────────────────────

def app_base_dir() -> Path:
    """Diretório base da aplicação (ao lado do .exe quando empacotado)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def _bundle_dir() -> Path:
    """Pasta onde o PyInstaller extrai dados/binários (ffmpeg, assets)."""
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) if meipass else app_base_dir()


OUTPUT_DIR = app_base_dir() / "output"
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "medium")  # tiny | base | small | medium | large
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "pt")


# ─────────────────────────────────────────────
# FFMPEG
# ─────────────────────────────────────────────

def _find_ffmpeg() -> str | None:
    """Localiza o ffmpeg: PATH do sistema ou binário empacotado junto ao app."""
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
    """Pasta do ffmpeg para passar ao yt-dlp (opção ffmpeg_location)."""
    ffmpeg = _find_ffmpeg()
    return str(Path(ffmpeg).parent) if ffmpeg else None


def ensure_ffmpeg() -> bool:
    """Garante que o ffmpeg é acessível; adiciona o binário empacotado ao PATH."""
    ffmpeg = _find_ffmpeg()
    if ffmpeg:
        # Prepend ao PATH para o Whisper (que chama ffmpeg via subprocess) o encontrar.
        ffmpeg_dir = str(Path(ffmpeg).parent)
        if ffmpeg_dir not in os.environ.get("PATH", "").split(os.pathsep):
            os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
        return True
    print("⚠️  ffmpeg não encontrado. Instale o ffmpeg e adicione ao PATH.")
    print("    Download: https://ffmpeg.org/download.html")
    return False


# ─────────────────────────────────────────────
# YT-DLP (API Python — funciona empacotado, sem depender do comando no PATH)
# ─────────────────────────────────────────────

def _ydl(opts: dict) -> "yt_dlp.YoutubeDL":
    """Cria um YoutubeDL com opções padrão + localização do ffmpeg."""
    base = {"quiet": True, "no_warnings": True, "noprogress": True}
    base.update(opts)
    loc = _ffmpeg_location()
    if loc:
        base.setdefault("ffmpeg_location", loc)
    return yt_dlp.YoutubeDL(base)


def get_video_info(url: str, index: int = 1) -> dict:
    """Extrai metadados de um único vídeo, sem baixar."""
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
    """Obtém a lista de vídeos da playlist/canal via yt-dlp (API Python)."""
    print("📋 Obtendo lista de vídeos da playlist...")
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
    print(f"✅ {len(videos)} vídeos encontrados.\n")
    return videos


# ─────────────────────────────────────────────
# ETAPA 2 — DOWNLOAD DO ÁUDIO
# ─────────────────────────────────────────────

def download_audio(video: dict, output_dir: Path) -> Path:
    """Baixa apenas o áudio do vídeo em MP3 (via API do yt-dlp)."""
    audio_path = output_dir / "audio.mp3"
    if audio_path.exists():
        print("  ⏩ Áudio já baixado, pulando...")
        return audio_path

    print("  ⬇️  Baixando áudio...")
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
        raise RuntimeError(f"yt-dlp falhou: {e}") from e

    if not audio_path.exists():
        raise RuntimeError("yt-dlp não produziu o arquivo audio.mp3.")
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

def process_video(video: dict, index: int, total: int) -> Path:
    """Processa um vídeo completo passo a passo. Retorna a pasta de saída."""
    print(f"\n{'═'*60}")
    print(f"🎬 [{index}/{total}] {video['title']}")
    print(f"{'═'*60}")

    folder_name = f"{video['index']:02d}_{sanitize_filename(video['title'])}"
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

    return video_dir


def main():
    print("╔══════════════════════════════════════════════╗")
    print("║      YouTube Playlist Analyzer — Claude      ║")
    print("╚══════════════════════════════════════════════╝\n")

    ensure_ffmpeg()
    playlist_url = input("🔗 Cole a URL da playlist do YouTube: ").strip()
    OUTPUT_DIR.mkdir(exist_ok=True)

    try:
        videos = get_playlist_videos(playlist_url)
    except (yt_dlp.utils.DownloadError, json.JSONDecodeError) as e:
        print(f"❌ Erro ao obter playlist: {e}")
        return

    print(f"🚀 Iniciando processamento de {len(videos)} vídeo(s)...\n")

    for i, video in enumerate(videos, 1):
        process_video(video, i, len(videos))

    print(f"\n{'═'*60}")
    print(f"🎉 Processamento concluído!")
    print(f"📁 Resultados salvos em: {OUTPUT_DIR.resolve()}")
    print(f"{'═'*60}")


if __name__ == "__main__":
    main()
