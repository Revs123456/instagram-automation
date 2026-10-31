#!/usr/bin/env bash
# One-command setup for the AI Video Editor folder (macOS / Linux).
# Installs the 4 free tools: HyperFrames, FFmpeg, Whisper, yt-dlp.
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '\n\033[1;33m==> %s\033[0m\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

mkdir -p "Raw Footage" Reference Export projects

# --- system packages: ffmpeg, node, python ---------------------------------
if [[ "$(uname)" == "Darwin" ]]; then
  if ! have brew; then
    say "Installing Homebrew"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv)"
  fi
  say "Installing FFmpeg, Node.js, Python (Homebrew)"
  brew install ffmpeg node python@3.12 pipx
elif have apt-get; then
  say "Installing FFmpeg, Node.js, Python (apt)"
  sudo apt-get update
  sudo apt-get install -y ffmpeg python3 python3-pip python3-venv pipx
  have node || sudo apt-get install -y nodejs npm
elif have dnf; then
  sudo dnf install -y ffmpeg python3 python3-pip pipx nodejs npm
else
  echo "Install ffmpeg, python3 and node 22+ with your package manager, then re-run." >&2
fi

have pipx || python3 -m pip install --user pipx
python3 -m pipx ensurepath >/dev/null 2>&1 || true
export PATH="$HOME/.local/bin:$PATH"

# --- 1. FFmpeg: cuts, trims, converts ---------------------------------------
say "1/4 FFmpeg"; ffmpeg -version | head -1

# --- 2. yt-dlp: download reference reels ------------------------------------
say "2/4 yt-dlp"
pipx install --force yt-dlp >/dev/null
yt-dlp --version

# --- 3. Whisper: transcripts / word timings for captions --------------------
say "3/4 Whisper (first run downloads the model)"
pipx install --force openai-whisper >/dev/null
whisper --help >/dev/null && echo "whisper OK"

# --- 4. HyperFrames: HTML in, motion graphics out ---------------------------
say "4/4 HyperFrames"
npm install -g hyperframes
hyperframes skills || echo "(Optional) run 'npx hyperframes skills' to give Claude the HyperFrames skills."
hyperframes doctor || true

say "Done. Open this folder in the Claude desktop app and say: \"Turn the reels in Reference into a style sheet\""
