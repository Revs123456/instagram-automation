#!/usr/bin/env bash
# Word-level transcript of a clip (for captions + cutting silences/fillers).
#   ./scripts/transcribe.sh "Raw Footage/raw_footage.mp4" [model]
# Output: projects/transcripts/<name>.json / .srt
set -euo pipefail
cd "$(dirname "$0")/.."
in="$1"; model="${2:-small}"
mkdir -p projects/transcripts
whisper "$in" --model "$model" --word_timestamps True \
  --output_format all --output_dir projects/transcripts
