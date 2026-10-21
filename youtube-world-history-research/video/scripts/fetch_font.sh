#!/usr/bin/env bash
# Download Noto Sans JP Black (OFL) into public/fonts/ so rendering needs no
# network access for fonts. Re-run anytime; the file is gitignored.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p public/fonts
out=public/fonts/NotoSansJP-Black.ttf
if [ -s "$out" ]; then echo "already exists: $out"; exit 0; fi
# A non-browser User-Agent makes Google Fonts return a single full TTF URL.
url=$(curl -fsS -A "curl" "https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@900" \
  | grep -o 'https://fonts.gstatic.com/[^)]*\.ttf' | head -1)
echo "downloading $url"
curl -fsSL "$url" -o "$out"
ls -la "$out"
