"""Fetch BLS LAUS (Iowa counties) and CPI alcohol series via BLS public API v1 (no key)."""
import csv
import json
import os
import sys
import time
import urllib.request

OUT = sys.argv[1]
API = "https://api.bls.gov/publicAPI/v1/timeseries/data/"

# Iowa county FIPS codes are the odd numbers 001-197 (99 counties)
counties = [f"{c:03d}" for c in range(1, 198, 2)]
# measure 03 = unemployment rate, 06 = labor force
laus = [f"LAUCN19{c}000000000{m}" for c in counties for m in ("3", "6")]
cpi = ["CUUR0000SAF116", "CUUR0000SEFW", "CUUR0000SEFW01", "CUUR0000SEFW02", "CUUR0000SEFW03"]


def fetch(series, start="2020", end="2025"):
    body = json.dumps({"seriesid": series, "startyear": start, "endyear": end}).encode()
    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def run(name, series):
    os.makedirs(f"{OUT}/{name}", exist_ok=True)
    rows = []
    for i in range(0, len(series), 25):
        batch = series[i:i + 25]
        d = fetch(batch)
        with open(f"{OUT}/{name}/raw_batch_{i // 25 + 1:02d}.json", "w") as fh:
            json.dump(d, fh)
        if d.get("status") != "REQUEST_SUCCEEDED":
            print(name, "batch", i // 25 + 1, d.get("status"), d.get("message"))
        for s in d.get("Results", {}).get("series", []):
            for p in s["data"]:
                rows.append([s["seriesID"], p["year"], p["period"], p["periodName"], p["value"]])
        time.sleep(2)
    with open(f"{OUT}/{name}/{name}.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["series_id", "year", "period", "period_name", "value"])
        w.writerows(rows)
    print(name, len(rows), "rows")


run("bls_laus_iowa_counties", laus)
run("bls_cpi_alcohol", cpi)
