"""Import Record-Builder JSON and JSONL exports into the evidence store."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from aifs.evidence_store import EvidenceStore


def _iter_json(path: Path) -> Iterator[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                value = json.loads(line)
                if isinstance(value, dict):
                    yield value
        return
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, dict) and isinstance(value.get("records"), list):
        for item in value["records"]:
            if isinstance(item, dict):
                yield item
    elif isinstance(value, dict):
        yield value
    elif isinstance(value, list):
        yield from (item for item in value if isinstance(item, dict))


def _iter_records(path: Path) -> Iterator[dict[str, Any]]:
    if path.is_file():
        yield from _iter_json(path)
        return
    if not path.is_dir():
        raise FileNotFoundError(path)
    for child in sorted(path.iterdir()):
        if child.suffix.lower() in {".json", ".jsonl"} and child.is_file():
            yield from _iter_json(child)


def import_records(path: Path, store: EvidenceStore) -> int:
    count = 0
    for record in _iter_records(path):
        store.upsert_record(record)
        count += 1
    return count
