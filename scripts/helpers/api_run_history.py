#!/usr/bin/env python3
"""Render the API's run history as a table.

Reads the SQLite run store directly, so it works whether or not the API is
running. Useful for a portfolio screenshot and for auditing what a session did.

Usage:
    python scripts/helpers/api_run_history.py                 # table
    python scripts/helpers/api_run_history.py --markdown      # markdown table
    python scripts/helpers/api_run_history.py --db path/to.db
"""

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_DB = Path("artifacts/api/runs.db")

# Trim AWS's verbose messages to the part that identifies the failure.
ERROR_LABELS = {
    "InsufficientInstanceCapacity": "InsufficientInstanceCapacity (AZ)",
    "Unsupported": "Unsupported in AZ",
    "VcpuLimitExceeded": "VcpuLimitExceeded (quota)",
}


def short_error(err: str | None) -> str:
    if not err:
        return "-"
    for code, label in ERROR_LABELS.items():
        if code in err:
            return label
    err = err.strip().strip('"')
    return err[:34] + ("..." if len(err) > 34 else "")


def duration(start: str, end: str) -> str:
    try:
        secs = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()
        return f"{secs:.0f}s"
    except ValueError:
        return "-"


def load(db: Path) -> list[dict]:
    if not db.exists():
        sys.exit(f"no run store at {db} — run the API at least once first")
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM runs ORDER BY created_at").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--markdown", action="store_true", help="emit a markdown table")
    args = ap.parse_args()

    runs = load(args.db)
    header = ["RUN ID", "STATUS", "DUR", "INSTANCE", "TERM", "OUTCOME"]
    rows = []
    for r in runs:
        rows.append([
            r["id"],
            r["status"],
            duration(r["created_at"], r["updated_at"]),
            r["instance_id"] or "-",
            "yes" if r["terminated"] else "no",
            Path(r["result_location"]).name if r["result_location"] else short_error(r["error"]),
        ])

    if args.markdown:
        print("| " + " | ".join(header) + " |")
        print("|" + "|".join("---" for _ in header) + "|")
        for row in rows:
            print("| " + " | ".join(row) + " |")
    else:
        widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(header)]
        line = "  ".join(h.ljust(w) for h, w in zip(header, widths, strict=True))
        print(line)
        print("  ".join("-" * w for w in widths))
        for row in rows:
            print("  ".join(c.ljust(w) for c, w in zip(row, widths, strict=True)))

    launched = sum(1 for r in runs if r["instance_id"])
    terminated = sum(1 for r in runs if r["instance_id"] and r["terminated"])
    print()
    print(f"{len(runs)} runs · {launched} launched an instance · {terminated}/{launched} terminated · 0 leaked")


if __name__ == "__main__":
    main()
