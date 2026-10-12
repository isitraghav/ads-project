#!/usr/bin/env bash
# Re-fetch Socrata extracts that were truncated: two MTA weeks (single query each)
# and NYC permitted events 2025 (paged by 50,000 rows, stable order).
# Usage: bash scripts/refetch_socrata.sh <url-list-file>   (list from make_download_lists.py)
set -uo pipefail
cd "$(dirname "$0")/../RebalanceIQ/data/raw"
LIST=$1
TMP=$(mktemp -d)

for w in 37 39; do
  f=mta_subway_hourly/mta_subway_hourly_2025_w$w.csv
  u=$(grep -B2 "out=mta_subway_hourly_2025_w$w.csv" "$LIST" | head -1)
  if curl -sf --retry 5 --retry-delay 10 -m 900 -o "$TMP/w$w.csv" "$u"; then
    mv "$TMP/w$w.csv" "$f"; echo "w$w ok: $(($(wc -l < "$f") - 1)) rows"
  else
    echo "w$w FAILED"
  fi
done

out=nyc_permitted_events/nyc_permitted_events_2025_bkfu-528j.csv
W="%24where=start_date_time%20between%20%272025-01-01T00%3A00%3A00%27%20and%20%272025-12-31T23%3A59%3A59%27"
: > "$TMP/events.csv"
off=0
while :; do
  if ! curl -sf --retry 5 --retry-delay 10 -m 600 -o "$TMP/page.csv" \
      "https://data.cityofnewyork.us/resource/bkfu-528j.csv?$W&%24order=event_id,start_date_time&%24limit=50000&%24offset=$off"; then
    echo "events page $off FAILED"; exit 1
  fi
  n=$(($(wc -l < "$TMP/page.csv") - 1))
  if [ $off -eq 0 ]; then cat "$TMP/page.csv" >> "$TMP/events.csv"; else tail -n +2 "$TMP/page.csv" >> "$TMP/events.csv"; fi
  echo "events page $off: $n lines"
  [ "$n" -lt 50000 ] && break
  off=$((off + 50000))
done
mv "$TMP/events.csv" "$out"
rm -rf "$TMP"
