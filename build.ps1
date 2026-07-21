#Requires -Version 5
<#
    build.ps1 — Build the Windows .exe for YouTube Analyzer with PyInstaller.

    Usage:
        .\build.ps1

    Produces:
        dist\YouTube Analyzer\YouTube Analyzer.exe   (a self-contained one-folder app)

    Notes:
      * Bundles ffmpeg.exe found on PATH. To bundle a specific copy, set
        $env:YTA_FFMPEG = "C:\path\to\ffmpeg.exe" before running.
      * The end user still needs Ollama installed and running, plus a pulled
        model (e.g. `ollama pull mistral`). Whisper model weights download on
        first run.
#>
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$python = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "venv\Scripts\python.exe not found. Create the venv first: py -3.14 -m venv venv; then pip install -r requirements.txt"
}

Write-Host "==> Installing build dependencies (PyInstaller)..." -ForegroundColor Cyan
& $python -m pip install --upgrade pip
& $python -m pip install -r (Join-Path $PSScriptRoot "requirements-build.txt")

Write-Host "==> Building with PyInstaller (bundles PyTorch/Whisper — this takes several minutes)..." -ForegroundColor Cyan
& $python -m PyInstaller --noconfirm --clean "yt-analyzer.spec"

$exe = Join-Path $PSScriptRoot "dist\YouTube Analyzer\YouTube Analyzer.exe"
if (Test-Path $exe) {
    Write-Host "`n==> Build complete:" -ForegroundColor Green
    Write-Host "    $exe"
    Write-Host "Distribute the whole 'dist\YouTube Analyzer' folder (not just the .exe)." -ForegroundColor Yellow
} else {
    Write-Error "Build finished but the .exe was not found at the expected path."
}
