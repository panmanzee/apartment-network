#!/bin/bash
# one-off setup on the WSL box (not the minipc)
set -e
url=$(curl -s https://api.github.com/repos/jgraph/drawio-desktop/releases/latest | grep browser_download_url | grep 'amd64.*\.deb' | head -1 | cut -d'"' -f4)
echo "deb: $url"
curl -sL -o /tmp/drawio.deb "$url"
S=""
if [ "$(id -u)" -ne 0 ]; then S="sudo -n"; fi
$S apt-get update -qq
$S apt-get install -y -qq xvfb /tmp/drawio.deb
ls -la /opt/drawio/ | head -3
