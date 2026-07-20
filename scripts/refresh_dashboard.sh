#!/bin/bash
# Dashboard 10min 高频刷新 — 仅采集+重建面板，不做git push
cd "$(dirname "$0")/.."
python fifa-dashboard/collector.py --once 2>&1 | tail -1
python fifa-dashboard/build_static.py 2>&1 | tail -1
echo "[$(date +%H:%M)] dashboard refreshed"
