# One-command setup for the AI Video Editor folder (Windows, PowerShell).
# Run:  powershell -ExecutionPolicy Bypass -File .\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

New-Item -ItemType Directory -Force -Path "Raw Footage","Reference","Export","projects" | Out-Null

Write-Host "`n==> Installing FFmpeg, Node.js, Python (winget)" -ForegroundColor Yellow
winget install -e --id Gyan.FFmpeg        --accept-source-agreements --accept-package-agreements
winget install -e --id OpenJS.NodeJS.LTS  --accept-source-agreements --accept-package-agreements
winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements

# Refresh PATH for this session
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("Path","User")

Write-Host "`n==> yt-dlp + Whisper" -ForegroundColor Yellow
py -m pip install --upgrade pip
py -m pip install --upgrade yt-dlp openai-whisper

Write-Host "`n==> HyperFrames" -ForegroundColor Yellow
npm install -g hyperframes
hyperframes skills
hyperframes doctor

Write-Host "`nDone. Open this folder in the Claude desktop app." -ForegroundColor Green
