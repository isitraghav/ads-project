#!/usr/bin/env bash
# Re-download all raw data for RebalanceIQ and StockIQ.
# Usage: bash scripts/download_all.sh   (run from the project root)
set -euo pipefail
cd "$(dirname "$0")/.."
TMP=$(mktemp -d)
curl -s -o "$TMP/ghcnd-stations.txt" https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-stations.txt
python3 scripts/make_download_lists.py "$TMP" "$TMP/ghcnd-stations.txt"
python3 scripts/fetch_bls.py StockIQ/data/raw
# bulk files: 8 parallel downloads, 8 connections each, resumable
aria2c -i <(cat "$TMP/bulk_rebalanceiq.txt" "$TMP/bulk_stockiq.txt") -j 8 -x 8 -s 8 -k 1M -c \
  --auto-file-renaming=false --max-tries=10 --retry-wait=10 --timeout=120
# Socrata API extracts: gentler concurrency, no ranged requests
aria2c -i "$TMP/api_rebalanceiq.txt" -j 6 -x 1 --auto-file-renaming=false \
  --max-tries=5 --retry-wait=30 --timeout=600 --connect-timeout=60
.venv/bin/python scripts/validate_raw.py
