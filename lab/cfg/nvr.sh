#!/bin/bash
# fake NVR services: https, rtsp, and a few ports that must stay closed to policy
for p in 443 554 80 22 8080; do
  nohup socat TCP-LISTEN:$p,fork,reuseaddr SYSTEM:"echo nvr:$p" >/dev/null 2>&1 &
done
