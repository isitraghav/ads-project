"""Validate and profile raw downloads for RebalanceIQ and StockIQ.

For every file under <project>/data/raw it records: size, whether the download
is complete (no leftover .aria2 control file, archive integrity), row and column
counts, and the column names. Results are written to
<project>/data/raw/_inventory.csv and printed as a summary.

Usage: .venv/bin/python scripts/validate_raw.py [RebalanceIQ|StockIQ ...]
"""
import csv
import gzip
import io
import json
import sys
import zipfile
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
con = duckdb.connect()


def csv_shape(path_expr):
    """Row/column count of a CSV via DuckDB (handles large files without loading into memory).

    Falls back to Latin-1 for files that are not valid UTF-8 (e.g. Census population estimates).
    """
    for enc in ("utf-8", "latin-1"):
        src = f"read_csv_auto({path_expr!r}, sample_size=20000, all_varchar=true, encoding='{enc}')"
        try:
            cols = con.execute(f"DESCRIBE SELECT * FROM {src}").fetchall()
            n = con.execute(f"SELECT count(*) FROM {src}").fetchone()[0]
            return n, [c[0] for c in cols]
        except duckdb.InvalidInputException:
            if enc == "latin-1":
                raise


def zip_shape(path):
    """Row/column count across all CSV members of a zip archive."""
    total, cols, members = 0, None, 0
    with zipfile.ZipFile(path) as z:
        bad = z.testzip()
        if bad:
            raise ValueError(f"corrupt member {bad}")
        for info in z.infolist():
            if not info.filename.lower().endswith(".csv") or info.filename.startswith("__MACOSX"):
                continue
            members += 1
            with z.open(info) as fh:
                text = io.TextIOWrapper(fh, encoding="utf-8", errors="replace", newline="")
                reader = csv.reader(text)
                header = next(reader)
                cols = cols or header
                total += sum(1 for _ in reader)
    return total, cols, members


def profile(path):
    suf = "".join(path.suffixes[-2:]).lower()
    name = path.name.lower()
    if suf.endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            has_csv = any(i.filename.lower().endswith(".csv") for i in z.infolist())
        if has_csv:
            n, cols, members = zip_shape(path)
            return n, cols, f"{members} csv member(s)"
        with zipfile.ZipFile(path) as z:
            if z.testzip():
                raise ValueError("corrupt zip")
            return None, None, f"{len(z.infolist())} files (shapefile/archive)"
    if suf.endswith(".csv.gz"):
        with gzip.open(path, "rt", errors="replace") as fh:
            r = csv.reader(fh)
            cols = next(r)
            return sum(1 for _ in r), cols, ""
    if name.endswith(".csv"):
        n, cols = csv_shape(str(path))
        return n, cols, ""
    if name.endswith(".dat"):  # ACS summary files are pipe-delimited
        n = con.execute(f"SELECT count(*) FROM read_csv({str(path)!r}, delim='|', header=true, all_varchar=true)").fetchone()[0]
        cols = [c[0] for c in con.execute(f"DESCRIBE SELECT * FROM read_csv({str(path)!r}, delim='|', header=true, all_varchar=true)").fetchall()]
        return n, cols, "pipe-delimited"
    if name.endswith(".parquet"):
        n = con.execute(f"SELECT count(*) FROM read_parquet({str(path)!r})").fetchone()[0]
        cols = [c[0] for c in con.execute(f"DESCRIBE SELECT * FROM read_parquet({str(path)!r})").fetchall()]
        return n, cols, ""
    if name.endswith(".geojson"):
        d = json.loads(path.read_text())
        feats = d.get("features", [])
        cols = list(feats[0]["properties"].keys()) if feats else []
        return len(feats), cols, "geojson features"
    if name.endswith(".json"):
        d = json.loads(path.read_text())
        if isinstance(d, list):
            return len(d), list(d[0].keys()) if d and isinstance(d[0], dict) else [], "json list"
        if isinstance(d, dict) and isinstance(d.get("data"), dict):
            inner = next(iter(d["data"].values()))
            if isinstance(inner, list):
                return len(inner), list(inner[0].keys()) if inner and isinstance(inner[0], dict) else [], "gbfs feed"
        return None, list(d.keys()) if isinstance(d, dict) else None, "json object"
    if name.endswith(".txt"):
        with open(path, errors="replace") as fh:
            first = fh.readline()
            n = sum(1 for _ in fh)
        delim = "|" if "|" in first else None
        return n, first.strip().split(delim) if delim else None, "text"
    return None, None, "not profiled"


def run(project):
    raw = ROOT / project / "data" / "raw"
    rows = []
    for path in sorted(p for p in raw.rglob("*") if p.is_file()):
        if path.name.startswith("_") or path.suffix == ".aria2":
            continue
        rel = path.relative_to(raw)
        incomplete = path.with_name(path.name + ".aria2").exists()
        status, n, cols, note = "OK", None, None, ""
        if incomplete:
            status = "INCOMPLETE"
        else:
            try:
                n, cols, note = profile(path)
            except Exception as e:  # noqa: BLE001 - record any read failure as a data-quality finding
                status, note = "ERROR", str(e)[:200]
        rows.append({
            "source_folder": rel.parts[0], "file": str(rel), "size_mb": round(path.stat().st_size / 1e6, 2),
            "status": status, "rows": n, "n_columns": len(cols) if cols else None,
            "columns": "|".join(cols) if cols else "", "note": note,
        })
        print(f"{status:10s} {str(rel):60s} rows={n!s:>12s} cols={len(cols) if cols else '-'}")
    out = raw / "_inventory.csv"
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    by_src = {}
    for r in rows:
        s = by_src.setdefault(r["source_folder"], [0, 0, 0])
        s[0] += 1
        is_meta = "_columns.json" in r["file"] or "raw_batch_" in r["file"]
        s[1] += 0 if is_meta else (r["rows"] or 0)
        s[2] += r["status"] != "OK"
    print(f"\n{project} summary -> {out}")
    for k, (files, nrows, bad) in by_src.items():
        print(f"  {k:35s} files={files:<4d} rows={nrows:>13,d} problems={bad}")


if __name__ == "__main__":
    for p in sys.argv[1:] or ["RebalanceIQ", "StockIQ"]:
        run(p)
