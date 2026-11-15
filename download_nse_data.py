#!/usr/bin/env python3
"""
download_nse_data.py  --  LIVEQUANT-AI

Downloads recent NSE CM-UDiFF Common Bhavcopy Final daily ZIP files into
<project root>/data/raw  (the project root is the folder this script lives in).

What it does
  * Walks backwards from today, one calendar day at a time.
  * Skips Saturdays and Sundays without making a request.
  * Treats HTTP 404 as "no file for that date" (exchange holiday or not yet published).
  * Validates every ZIP in memory BEFORE saving it (valid ZIP, contains a CSV,
    expected Bhavcopy columns, at least one data row).
  * Stops once 30 sessions are collected (default) or the look-back limit is reached.
  * Never overwrites or deletes anything. Files already in data/raw are re-checked
    and counted, not downloaded again.
  * Handles network errors (timeouts, DNS, 5xx, 429) with retries and keeps going.

Only Python standard-library modules are used.

Usage (from the project root):
    python download_nse_data.py
    python download_nse_data.py --sessions 30 --max-days 90
"""

import argparse
import io
import sys
import time
import zipfile
from datetime import date, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = "https://nsearchives.nseindia.com/content/cm/"
FILE_TEMPLATE = "BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip"

# Columns every CM-UDiFF Common Bhavcopy CSV is expected to contain.
REQUIRED_COLUMNS = {"TckrSymb", "SctySrs", "OpnPric", "HghPric", "LwPric", "ClsPric"}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/all-reports",
}

TIMEOUT_SECONDS = 30
MAX_ATTEMPTS = 3
POLITE_DELAY_SECONDS = 1.0
MAX_CONSECUTIVE_BLOCKS = 3  # stop early if NSE keeps answering 401/403


def validate_zip_bytes(data):
    """Return (ok, reason, data_rows). Nothing is written to disk here."""
    if not data or data[:2] != b"PK":
        return False, "response is not a ZIP file", 0
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            bad_member = zf.testzip()
            if bad_member is not None:
                return False, "corrupt ZIP member: " + bad_member, 0
            csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not csv_names:
                return False, "ZIP contains no CSV file", 0
            raw = zf.read(csv_names[0])
    except zipfile.BadZipFile:
        return False, "bad or truncated ZIP file", 0
    except Exception as exc:  # defensive: never crash on a strange file
        return False, "could not read ZIP: " + str(exc), 0

    lines = raw.decode("utf-8-sig", errors="replace").splitlines()
    lines = [ln for ln in lines if ln.strip()]
    if len(lines) < 2:
        return False, "CSV has no data rows", 0
    header = {col.strip() for col in lines[0].split(",")}
    missing = REQUIRED_COLUMNS - header
    if missing:
        return False, "CSV is missing columns: " + ", ".join(sorted(missing)), 0
    return True, "ok", len(lines) - 1


def fetch(url):
    """
    Download url. Returns (status, payload):
      ("ok", bytes) | ("missing", None) | ("blocked", message) | ("error", message)
    """
    last_error = "unknown error"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            req = Request(url, headers=HEADERS)
            with urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                return "ok", resp.read()
        except HTTPError as exc:
            if exc.code == 404:
                return "missing", None
            if exc.code in (401, 403):
                return "blocked", "HTTP %d (access refused by NSE)" % exc.code
            last_error = "HTTP %d" % exc.code
            if exc.code != 429 and exc.code < 500:
                return "error", last_error  # other 4xx: retrying will not help
        except (URLError, TimeoutError, ConnectionError, OSError) as exc:
            last_error = "network error: " + str(getattr(exc, "reason", exc))
        if attempt < MAX_ATTEMPTS:
            time.sleep(2 * attempt)
    return "error", last_error


def save_atomically(dest, data):
    """Write to a temporary file, then rename, so a half-written ZIP is never left behind."""
    tmp = dest.with_name(dest.name + ".part")
    try:
        tmp.write_bytes(data)
        tmp.replace(dest)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def main():
    parser = argparse.ArgumentParser(description="Download NSE CM-UDiFF Common Bhavcopy Final ZIP files.")
    parser.add_argument("--sessions", type=int, default=30, help="trading sessions to collect (default 30)")
    parser.add_argument("--max-days", type=int, default=90, help="how many calendar days to look back (default 90)")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    raw_dir = project_root / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    print("LIVEQUANT-AI : NSE CM-UDiFF Common Bhavcopy Final downloader")
    print("Save folder  : %s" % raw_dir)
    print("Target       : %d trading sessions (looking back up to %d days)\n" % (args.sessions, args.max_days))

    downloaded, already_present, unavailable, failed, invalid_existing = [], [], [], [], []
    weekends = 0
    consecutive_blocks = 0
    stopped_reason = None
    sessions = 0
    today = date.today()

    try:
        for offset in range(args.max_days + 1):
            if sessions >= args.sessions:
                break
            day = today - timedelta(days=offset)
            if day.weekday() >= 5:
                weekends += 1
                continue

            ymd = day.strftime("%Y%m%d")
            name = FILE_TEMPLATE.format(ymd=ymd)
            dest = raw_dir / name
            label = day.isoformat()

            if dest.exists():
                ok, reason, rows = validate_zip_bytes(dest.read_bytes())
                if ok:
                    already_present.append(day)
                    sessions += 1
                    print("%s  already saved (%d rows)  [%d/%d]" % (label, rows, sessions, args.sessions))
                else:
                    invalid_existing.append((day, reason))
                    print("%s  existing file is invalid (%s) - left untouched" % (label, reason))
                continue

            status, payload = fetch(BASE_URL + name)
            time.sleep(POLITE_DELAY_SECONDS)

            if status == "blocked":
                consecutive_blocks += 1
                failed.append((day, payload))
                print("%s  blocked: %s" % (label, payload))
                if consecutive_blocks >= MAX_CONSECUTIVE_BLOCKS:
                    stopped_reason = (
                        "NSE refused %d requests in a row. Open https://www.nseindia.com in a browser, "
                        "wait a few minutes (or try another network) and run the script again."
                        % consecutive_blocks
                    )
                    break
                continue
            consecutive_blocks = 0

            if status == "missing":
                unavailable.append(day)
                print("%s  not available (holiday or not published yet)" % label)
            elif status == "error":
                failed.append((day, payload))
                print("%s  download failed: %s" % (label, payload))
            else:
                ok, reason, rows = validate_zip_bytes(payload)
                if not ok:
                    failed.append((day, "validation failed: " + reason))
                    print("%s  rejected, not saved (%s)" % (label, reason))
                else:
                    try:
                        save_atomically(dest, payload)
                    except OSError as exc:
                        failed.append((day, "could not save file: " + str(exc)))
                        print("%s  could not save file: %s" % (label, exc))
                    else:
                        downloaded.append(day)
                        sessions += 1
                        print("%s  downloaded (%d rows, %d KB)  [%d/%d]" % (label, rows, len(payload) // 1024, sessions, args.sessions))
    except KeyboardInterrupt:
        stopped_reason = "Interrupted by user (Ctrl+C). Files saved so far were kept."

    collected = sorted(downloaded + already_present)
    print("\n" + "=" * 60)
    print("DOWNLOAD SUMMARY")
    print("=" * 60)
    print("Trading sessions collected : %d of %d requested" % (len(collected), args.sessions))
    print("  newly downloaded         : %d" % len(downloaded))
    print("  already in data/raw      : %d" % len(already_present))
    print("Weekend days skipped       : %d" % weekends)
    print("Unavailable dates (404)    : %d" % len(unavailable))
    print("Failed / rejected          : %d" % len(failed))
    if invalid_existing:
        print("Existing invalid files     : %d (not modified)" % len(invalid_existing))
    if collected:
        print("Date range collected       : %s to %s" % (collected[0].isoformat(), collected[-1].isoformat()))
    print("Saved in                   : %s" % raw_dir)
    for day, why in failed:
        print("  - %s : %s" % (day.isoformat(), why))
    if stopped_reason:
        print("\nStopped early: " + stopped_reason)
    elif len(collected) < args.sessions:
        print("\nFewer sessions than requested were found within %d days. "
              "Run again with a larger --max-days if needed." % args.max_days)
    print("=" * 60)
    return 0 if collected else 1


if __name__ == "__main__":
    sys.exit(main())