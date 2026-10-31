#!/usr/bin/env bash
# Download reference reels into ./Reference with yt-dlp.
#   ./scripts/download_reels.sh https://www.instagram.com/reel/XXXX/ https://www.instagram.com/reel/YYYY/
# Private/age-gated reels: add --cookies-from-browser chrome (or safari/firefox) via YTDLP_ARGS.
set -euo pipefail
cd "$(dirname "$0")/.."
[[ $# -ge 1 ]] || { echo "usage: $0 <reel-url> [reel-url ...]" >&2; exit 1; }
yt-dlp ${YTDLP_ARGS:-} \
  -f "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b" --merge-output-format mp4 \
  -o "Reference/%(uploader)s_%(id)s.%(ext)s" \
  --write-info-json --no-playlist "$@"
ls -1 Reference
