"""Extract every auto-generated check label from a seed catalogue or tracking.json.

Outputs a two-column CSV ready to paste into your Google Sheet:

    label,display_name
    DC_room10_chest_1,
    KF_pot_2 (child),
    ...

The display_name column is left blank so you can fill it in the sheet.
Rows that already have an override in label_overrides.json are pre-filled.

IMPORTANT: labels are used exactly as they appear in the name field, including
any " (child)" or " (adult)" suffix. Your override keys in label_overrides.json
and in the Google Sheet must match exactly, suffix and all.

Two input formats are supported:

  Catalogue JSON  — a list of check objects each with a "name" field, as
                    exported by the app (checks.json / catalogue.json).

  tracking.json   — the seed artifact file; labels are read from the
                    "location" field of each check row ("Remake|<label>").

The script detects the format automatically.

Usage:
    # Point at a catalogue or tracking.json file directly:
    python tools/extract_labels.py PATH_TO_FILE

    # Point at a seed folder (tracking.json inside it):
    python tools/extract_labels.py PATH_TO_SEED_FOLDER

    # Scan all seeds in the default data/seeds folder:
    python tools/extract_labels.py

    # Write output to a CSV file instead of stdout:
    python tools/extract_labels.py PATH --out labels.csv

Auto-generated labels follow the zone_place_kind_n pattern
(e.g. DC_room10_chest_1, KF_midos_house_chest_2, KF_pot_2 (child)).
Human-readable AP names that contain spaces but no underscore structure
(e.g. "Dodongos Cavern Map Chest") are excluded — they don't need overrides.
"""

import csv
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
OVERRIDES_PATH = ROOT / "src" / "oot_rando" / "game" / "label_overrides.json"
DEFAULT_SEEDS = ROOT / "data" / "seeds"

# Auto-generated labels start with a zone code followed by underscore-separated
# parts, e.g. DC_room10_chest_1 or KF_pot_2 (child).
# They always have at least one underscore and start with a capital zone code.
# AP names like "Dodongos Cavern Map Chest" have spaces but no underscores.
AUTO_LABEL = re.compile(r'^[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+')


def load_overrides():
    try:
        return json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def extract_from_catalogue(data):
    """Extract labels from a catalogue list [{..., "name": "...", ...}, ...]."""
    labels = set()
    for entry in data:
        name = entry.get("name", "")
        if AUTO_LABEL.match(name):
            labels.add(name)
    return labels


def extract_from_tracking(data):
    """Extract labels from a tracking.json {checks: {gid: {location: "Remake|label"}}}."""
    labels = set()
    checks = data.get("checks", {})
    for row in checks.values():
        location = row.get("location", "")
        if location.startswith("Remake|"):
            label = location[len("Remake|"):]
            if AUTO_LABEL.match(label):
                labels.add(label)
    return labels


def extract_labels(path):
    """Return a set of auto-generated label strings from one file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    # Catalogue: top-level list of check objects.
    if isinstance(data, list):
        return extract_from_catalogue(data)
    # Catalogue wrapped in an object: {"checks": [...]}
    if isinstance(data, dict) and isinstance(data.get("checks"), list):
        return extract_from_catalogue(data["checks"])
    # tracking.json: {"checks": {gid: row}}
    if isinstance(data, dict) and isinstance(data.get("checks"), dict):
        return extract_from_tracking(data)
    raise ValueError(f"Unrecognised format in {path}")


def find_input_files(path):
    """Return a list of files to process given a path argument."""
    path = Path(path)
    if path.is_file():
        return [path]
    if path.is_dir():
        direct = path / "tracking.json"
        if direct.exists():
            return [direct]
        found = sorted(path.glob("*/tracking.json"))
        if found:
            return found
    return []


def main():
    out_arg = None
    raw_args = sys.argv[1:]
    positional = []
    i = 0
    while i < len(raw_args):
        if raw_args[i] == "--out" and i + 1 < len(raw_args):
            out_arg = raw_args[i + 1]
            i += 2
        elif raw_args[i].startswith("--"):
            i += 1
        else:
            positional.append(raw_args[i])
            i += 1

    if positional:
        path = Path(positional[0])
    elif DEFAULT_SEEDS.exists():
        path = DEFAULT_SEEDS
    else:
        print("No path given and no data/seeds folder found.")
        print("Usage: python tools/extract_labels.py PATH [--out labels.csv]")
        sys.exit(1)

    input_files = find_input_files(path)
    if not input_files:
        if path.is_file():
            input_files = [path]
        else:
            print(f"No recognisable input found at: {path}")
            sys.exit(1)

    all_labels = set()
    for f in input_files:
        try:
            all_labels.update(extract_labels(f))
        except (OSError, ValueError, KeyError) as e:
            print(f"Warning: could not read {f}: {e}", file=sys.stderr)

    if not all_labels:
        print("No auto-generated labels found.")
        sys.exit(0)

    overrides = load_overrides()

    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["label", "display_name"])
    for label in sorted(all_labels):
        writer.writerow([label, overrides.get(label, "")])

    result = out.getvalue()

    if out_arg:
        Path(out_arg).write_text(result, encoding="utf-8")
        pre_filled = sum(1 for lbl in all_labels if lbl in overrides)
        print(f"Written {len(all_labels)} label(s) to {out_arg}")
        if pre_filled:
            print(f"  {pre_filled} already have overrides pre-filled")
    else:
        print(result, end="")


if __name__ == "__main__":
    main()
