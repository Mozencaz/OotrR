"""Sync location name overrides from a Google Sheet to label_overrides.json.

The sheet must be published as CSV (File → Share → Publish to web → CSV).
Copy the published URL and paste it as SHEET_URL below, or pass it as the
first argument on the command line.

Expected sheet layout (header row required, extra columns are ignored):

    label                  | display_name
    DC_room10_chest_1      | DC Staircase Chest
    DC_room13_chest_2      | DC Bomb Flower Platform Chest
    ...

Rows with a blank label or display_name are skipped.
Rows whose display_name equals the label are also skipped (no-op overrides).

Usage:
    python tools/sync_label_overrides.py
    python tools/sync_label_overrides.py "https://docs.google.com/..."
"""

import csv
import io
import json
import sys
import urllib.request
from pathlib import Path

# Paste your published-CSV URL here if you don't want to pass it on the command line.
SHEET_URL = ""

OUTPUT = Path(__file__).parent.parent / "src" / "oot_rando" / "game" / "label_overrides.json"


def fetch_csv(url):
    with urllib.request.urlopen(url, timeout=15) as response:
        return response.read().decode("utf-8")


def parse_overrides(text):
    reader = csv.DictReader(io.StringIO(text))
    if "label" not in (reader.fieldnames or []) or "display_name" not in (reader.fieldnames or []):
        raise ValueError(
            f"Sheet must have 'label' and 'display_name' columns. "
            f"Found: {reader.fieldnames}"
        )
    overrides = {}
    for row in reader:
        label = row["label"].strip()
        display = row["display_name"].strip()
        if not label or not display or label == display:
            continue
        overrides[label] = display
    return overrides


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else SHEET_URL
    if not url:
        print("Error: no sheet URL provided.")
        print("  Set SHEET_URL in this script, or pass the URL as the first argument.")
        print("  python tools/sync_label_overrides.py \"https://docs.google.com/...\"")
        sys.exit(1)

    print("Fetching sheet...")
    try:
        text = fetch_csv(url)
    except Exception as e:
        print(f"Error fetching sheet: {e}")
        sys.exit(1)

    try:
        overrides = parse_overrides(text)
    except ValueError as e:
        print(f"Error parsing sheet: {e}")
        sys.exit(1)

    existing = {}
    if OUTPUT.exists():
        try:
            existing = json.loads(OUTPUT.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    OUTPUT.write_text(
        json.dumps(overrides, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    added = set(overrides) - set(existing)
    removed = set(existing) - set(overrides)
    changed = {k for k in overrides if k in existing and overrides[k] != existing[k]}

    print(f"Written to {OUTPUT}")
    print(f"  {len(overrides)} override(s) total")
    if added:
        print(f"  + {len(added)} added:   {', '.join(sorted(added))}")
    if removed:
        print(f"  - {len(removed)} removed: {', '.join(sorted(removed))}")
    if changed:
        print(f"  ~ {len(changed)} changed: {', '.join(sorted(changed))}")
    if not added and not removed and not changed:
        print("  (no changes)")


if __name__ == "__main__":
    main()
