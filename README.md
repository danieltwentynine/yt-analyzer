# YouTube Analyzer

Baixa automaticamente vídeos do YouTube, transcreve com Whisper e gera **resumo**, **análise crítica** e **mapa mental em JSON** para cada vídeo — tudo rodando localmente via Ollama, sem depender de APIs externas pagas.

Disponível como **interface gráfica** (`app.py`) e como **script de linha de comando** (`pipeline.py`).

---

## Interface gráfica (recomendado)

```bash
python app.py
```

A interface guia você por quatro telas:

| Tela | Descrição |
|---|---|
| **Menu inicial** | Escolha o modo: Vídeo único, Playlist, Canal inteiro ou Arquivo .txt |
| **Configuração** | Cole a URL (ou selecione o arquivo), escolha o modelo Ollama e inicie |
| **Progresso** | Barra de progresso geral + log em tempo real de cada etapa |
| **Resultados** | Lista dos vídeos processados com botão "Abrir pasta" para cada um |

> O `app.py` é o entry point principal e chama as funções do `pipeline.py` internamente.

---

## CLI (linha de comando)

```bash
python pipeline.py
```

Cole a URL quando solicitado. Útil para automação ou ambientes sem interface gráfica.

---

## Executável Windows (.exe)

Gere um aplicativo Windows autônomo (não exige Python instalado no computador do usuário final):

```powershell
# 1. Crie o ambiente virtual e instale as dependências de runtime
py -3.14 -m venv venv
venv\Scripts\pip install -r requirements.txt

# 2. Gere o executável
.\build.ps1        # ou dê duplo-clique em build.bat
```

O resultado fica em `dist\YouTube Analyzer\`. **Distribua a pasta inteira** — o `.exe` depende dos arquivos ao lado dele, não apenas do próprio `.exe`.

O build é controlado por [`yt-analyzer.spec`](yt-analyzer.spec) (PyInstaller), que:

- Empacota PyTorch + Whisper, os extratores do yt-dlp, numba/llvmlite e o `ffmpeg.exe` encontrado no PATH — o app fica autossuficiente.
- Produz uma pasta de ~2–3 GB (o PyTorch é grande; isso é esperado).

### O que o usuário final ainda precisa

O `.exe` embute tudo, **exceto** o Ollama, que é um servidor separado:

- Instale o [Ollama](https://ollama.com/download) e deixe-o rodando.
- Baixe um modelo: `ollama pull mistral`.
- Na primeira análise, o Whisper baixa automaticamente os pesos do modelo (~1.5 GB para `medium`) em `~/.cache/whisper` — requer internet nessa primeira vez.

> Os resultados são salvos na pasta `output/` criada **ao lado do `.exe`**.

---

## Estrutura de saída

Após a execução, a pasta `output/` terá:

```
output/
├── 01_Titulo-do-Video/
│   ├── meta.json            ← metadados do vídeo (título, URL, id)
│   ├── audio.mp3            ← áudio baixado
│   ├── transcript.txt       ← transcrição completa
│   ├── resumo_analise.md    ← resumo + análise crítica (Markdown)
│   └── mapa_mental.json     ← mapa mental hierárquico (JSON)
├── 02_Outro-Video/
│   └── ...
```

---

## Instalação

### 1. Pré-requisitos

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/download.html) instalado no sistema (necessário para Whisper e yt-dlp)
- [Ollama](https://ollama.com) instalado e rodando localmente

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
Baixe o ffmpeg em https://ffmpeg.org/download.html e o Ollama em https://ollama.com/download. Adicione o ffmpeg ao PATH.

---

### 2. Baixe um modelo Ollama

O modelo padrão é o `mistral`. Baixe-o antes de executar o pipeline:

```bash
ollama pull mistral
```

Outros modelos compatíveis: `llama3`, `gemma2`, `phi3`. Qualquer modelo de instrução funciona.

---

### 3. Clone / copie os arquivos

Coloque `app.py`, `pipeline.py`, `requirements.txt` e `.env` em uma pasta.

---

### 4. Crie o ambiente virtual e instale dependências

```bash
python -m venv venv

# Ativar (macOS/Linux):
source venv/bin/activate

# Ativar (Windows):
venv\Scripts\activate

pip install -r requirements.txt
```

---

### 5. Configure as variáveis de ambiente

Crie um arquivo `.env` na raiz do projeto com as variáveis abaixo (todas opcionais — os valores mostrados são os padrões):

```env
WHISPER_MODEL=medium
WHISPER_LANGUAGE=pt
OLLAMA_MODEL=mistral
```

---

### 6. Execute

Certifique-se de que o Ollama está rodando (`ollama serve` ou via app), então:

**Interface gráfica:**
```bash
python app.py
```

**Linha de comando:**
```bash
python pipeline.py
```

Cole a URL quando solicitado. Exemplos de URLs suportadas:
```
https://www.youtube.com/watch?v=xxxxxxxxxxx          # vídeo único
https://www.youtube.com/playlist?list=PLxxxxxxxxxxxx # playlist
https://www.youtube.com/@canal/videos                # canal inteiro
```

---

## Importando o mapa mental

### XMind
1. Abra o XMind
2. File → Import → JSON (ou use o xmind-cli para converter)
3. Selecione o arquivo `mapa_mental.json`

### Miro
1. Crie um novo board
2. Import → JSON
3. Selecione o arquivo `mapa_mental.json`

### Markmap (visualização rápida no browser)
1. Acesse https://markmap.js.org/repl
2. Cole o conteúdo do `resumo_analise.md` e visualize como mapa mental

---

## Performance

| Situação | Whisper Model Recomendado |
|---|---|
| Vídeos curtos / teste rápido | `tiny` ou `base` |
| Uso geral / bom equilíbrio | `medium` (padrão) |
| Máxima precisão em PT-BR | `large` |

| Situação | Ollama Model Recomendado |
|---|---|
| Hardware limitado (RAM < 8GB) | `phi3` ou `gemma2:2b` |
| Uso geral | `mistral` (padrão) |
| Máxima qualidade | `llama3` ou `gemma2` |

> O modelo Whisper é baixado automaticamente na primeira execução (~1.5GB para `medium`).
> O modelo Ollama precisa ser baixado manualmente com `ollama pull <modelo>`.

---

## Retomada automática

O script **não reprocessa** arquivos que já existem. Se a execução for interrompida, basta rodar novamente que ela continua de onde parou.

---

## Troubleshooting

**Erro ao baixar vídeo (yt-dlp)**
O yt-dlp é usado como **biblioteca Python** (instalado via `requirements.txt`), não como comando externo. Se o download falhar, atualize-o:
```bash
pip install -U yt-dlp
```

**`ffmpeg not found`**
Instale o ffmpeg conforme as instruções acima. No executável (`.exe`) o ffmpeg já vem embutido.

**`ollama: connection refused`**
O servidor Ollama não está rodando. Execute `ollama serve` em outro terminal ou abra o app Ollama.

**Modelo não encontrado**
```bash
ollama pull mistral
```
Ou defina outro modelo em `.env` com `OLLAMA_MODEL=nome-do-modelo`.

---

## Alterações recentes

### Suporte a executável Windows (`.exe`)

- Novo build **PyInstaller** — arquivos [`yt-analyzer.spec`](yt-analyzer.spec), [`build.ps1`](build.ps1), [`build.bat`](build.bat) e [`requirements-build.txt`](requirements-build.txt) — que empacota o app numa pasta autônoma `dist\YouTube Analyzer\`. Veja a seção [Executável Windows (.exe)](#executável-windows-exe).
- O `ffmpeg.exe` é **embutido automaticamente** no build (a partir do PATH da máquina de build) e localizado em tempo de execução — o usuário final não precisa instalar ffmpeg.
- Hook de runtime (`pyi_rthooks/no_console.py`) que **suprime as janelas de console** que piscavam a cada chamada do ffmpeg (download/transcrição).

### yt-dlp via API Python (em vez de comando externo)

- `pipeline.py` e `app.py` agora usam o `yt_dlp` como **biblioteca** (`yt_dlp.YoutubeDL`), não mais `subprocess.run(["yt-dlp", ...])`. Isso faz o download funcionar dentro do `.exe`, onde não existe o comando `yt-dlp` no PATH.
- Novo helper `pipeline.get_video_info()` centraliza a extração de metadados de um único vídeo (usado pelos modos **Vídeo único** e **Arquivo .txt**).

### Caminhos cientes de empacotamento

- A pasta `output/` é criada **ao lado do executável** (ou na raiz do projeto, ao rodar via Python), em vez de depender do diretório de trabalho atual.
- Descoberta automática do ffmpeg: PATH do sistema → binário embutido no build.

### Correção do ambiente virtual

- O `venv/pyvenv.cfg` apontava para um Python-base inexistente (`C:\Python314`), o que quebrava o `pip`. Corrigido para o caminho real do interpretador.

### `.gitignore`

- Passa a ignorar os artefatos de build do PyInstaller (`/build`, `/dist`).
