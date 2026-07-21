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
      * Bundles deno.exe (the JS runtime yt-dlp needs to download YouTube). If
        deno is not on PATH it is downloaded automatically into the project.
        To bundle a specific copy, set $env:YTA_DENO = "C:\path\to\deno.exe".
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

# ── Ensure a deno.exe is available to bundle ──────────────────────────
Write-Host "==> Checking for deno (JS runtime for yt-dlp)..." -ForegroundColor Cyan
if (-not $env:YTA_DENO) {
    $onPath = (Get-Command deno -ErrorAction SilentlyContinue).Source
    $local  = Join-Path $PSScriptRoot "deno.exe"
    if ($onPath) {
        $env:YTA_DENO = $onPath
        Write-Host "    Using deno on PATH: $onPath"
    } elseif (Test-Path $local) {
        $env:YTA_DENO = $local
        Write-Host "    Using bundled deno: $local"
    } else {
        Write-Host "    deno not found — downloading the official Windows build..." -ForegroundColor Yellow
        $url = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"
        $zip = Join-Path $env:TEMP "deno-download.zip"
        $ext = Join-Path $env:TEMP "deno-extract"
        Invoke-WebRequest -Uri $url -OutFile $zip
        if (Test-Path $ext) { Remove-Item -Recurse -Force $ext }
        Expand-Archive -Path $zip -DestinationPath $ext -Force
        Copy-Item (Join-Path $ext "deno.exe") $local -Force
        Remove-Item -Force $zip
        Remove-Item -Recurse -Force $ext
        $env:YTA_DENO = $local
        Write-Host "    deno downloaded to: $local"
    }
}

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
