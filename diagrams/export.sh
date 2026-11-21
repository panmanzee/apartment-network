#!/bin/bash
# run on the WSL box: renders every .drawio here to png
cd "$(dirname "$0")"
for f in *.drawio; do
  xvfb-run -a drawio --export --format png --scale 1.2 --border 20 --no-sandbox -o "${f%.drawio}.png" "$f"
done
ls -la *.png
