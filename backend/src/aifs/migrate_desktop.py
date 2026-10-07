"""Explicit SQLite snapshot migration; never overwrite source or destination."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def migrate(source: Path, destination: Path) -> dict[str, str]:
    names = ("aifs-workflow.sqlite3", "aifs-evidence.sqlite3")
    sources = [source / name for name in names if (source / name).is_file()]
    if not sources:
        raise ValueError("No AIFS databases found in the source directory")
    if source.resolve() == destination.resolve():
        raise ValueError("Source and destination must differ")
    if any((destination / path.name).exists() for path in sources):
        raise ValueError("Destination already contains a database; refusing to overwrite")
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = destination / "migration-backups" / stamp
    backup.mkdir(parents=True)
    for path in sources:
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as original:
            with sqlite3.connect(backup / path.name) as snapshot:
                original.backup(snapshot)
                if snapshot.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError(f"Invalid database: {path.name}")
    created: list[Path] = []
    try:
        for path in sources:
            target = destination / path.name
            with target.open("xb") as output, (backup / path.name).open("rb") as incoming:
                created.append(target)
                shutil.copyfileobj(incoming, output)
    except BaseException:
        for path in created:
            path.unlink()
        raise
    report = {
        "source": str(source.resolve()),
        "destination": str(destination.resolve()),
        "backup": str(backup),
        "created_at": stamp,
    }
    (backup / "migration.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(migrate(args.source, args.destination), indent=2))


if __name__ == "__main__":
    main()
