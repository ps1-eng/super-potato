from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def normalize_purchase_source(value: str) -> str:
    source = value.strip()
    if not source:
        return source
    lower = " ".join(source.lower().split())
    replacements = {
        "fb": "Facebook Marketplace",
        "facebook": "Facebook Marketplace",
        "facebook m": "Facebook Marketplace",
        "home": "Home",
        "adverts": "Adverts",
        "vinted": "Vinted",
        "tk max": "TK Maxx",
        "tk maxx": "TK Maxx",
        "temu": "Temu",
        "charity shop": "Charity Shop",
        "free": "Free",
        "dump": "Dump",
    }
    if lower in replacements:
        return replacements[lower]

    def format_location(prefix: str, location: str) -> str:
        return f"{prefix} - {location.title()}"

    if lower.startswith("svp "):
        return format_location("SVP", lower.replace("svp", "", 1).strip())
    if lower.startswith("vision ireland "):
        return format_location("Vision Ireland", lower.replace("vision ireland", "", 1).strip())
    if lower.startswith("vision "):
        return format_location("Vision Ireland", lower.replace("vision", "", 1).strip())
    if lower.startswith("sue ryder "):
        return format_location("Sue Ryder", lower.replace("sue ryder", "", 1).strip())
    if lower.startswith("cancer research "):
        return format_location("Cancer Research", lower.replace("cancer research", "", 1).strip())
    if lower.startswith("cancer "):
        return format_location("Cancer Research", lower.replace("cancer", "", 1).strip())
    if "car boot" in lower or "carboot" in lower:
        location = lower.replace("car boot", "").replace("carboot", "").strip()
        return format_location("Car Boot", location or "Other")
    if "auction" in lower:
        if "lockes" in lower:
            return "Auction - Lockes"
        if "matthews" in lower:
            return "Auction - Matthews"
        if "south dublin" in lower:
            return "Auction - South Dublin"
        if "downs" in lower:
            return "Auction - Downs"
        return "Auction - Other"
    if "wholesale" in lower:
        if "italian vintage" in lower:
            return "Wholesale - Italian Vintage"
        if "vintage" in lower:
            return "Wholesale - Vintage"
        return "Wholesale - Other"
    if "thrift" in lower:
        location = lower.replace("thrift", "").strip()
        return format_location("Thrift", location or "Other")
    if lower.startswith("oxfam "):
        return format_location("Oxfam", lower.replace("oxfam", "", 1).strip())
    if lower.startswith("jack and jill "):
        return format_location("Jack and Jill", lower.replace("jack and jill", "", 1).strip())
    if lower.startswith("enable "):
        return format_location("Enable Ireland", lower.replace("enable", "", 1).strip())
    if lower.startswith("barnardos "):
        return format_location("Barnardos", lower.replace("barnardos", "", 1).strip())
    if lower.startswith("ark "):
        return format_location("Ark", lower.replace("ark", "", 1).strip())
    if lower == "ark":
        return "Ark - Bray"
    return source


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize purchase_source values.")
    parser.add_argument(
        "--db",
        default="data/resale.db",
        help="Path to the SQLite database (default: data/resale.db)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes to the database (default: dry run)",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"Database not found at {db_path}")

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT id, purchase_source FROM items").fetchall()

    changes = []
    for item_id, source in rows:
        normalized = normalize_purchase_source(source or "")
        if source != normalized:
            changes.append((normalized, item_id, source))

    print(f"Found {len(changes)} rows to normalize.")
    for normalized, item_id, source in changes[:20]:
        print(f"{item_id}: '{source}' -> '{normalized}'")

    if not changes or not args.apply:
        print("Dry run only. Re-run with --apply to update the database.")
        return

    conn.executemany(
        "UPDATE items SET purchase_source = ? WHERE id = ?",
        [(normalized, item_id) for normalized, item_id, _ in changes],
    )
    conn.commit()
    print(f"Updated {len(changes)} rows.")


if __name__ == "__main__":
    main()
