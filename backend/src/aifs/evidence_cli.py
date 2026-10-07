"""Command-line import and smoke-search utility for the evidence store."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from aifs.evidence_import import import_records
from aifs.evidence_models import EvidenceSearchRequest
from aifs.evidence_store import EvidenceStore
from aifs.vector_index import FaissIndex, SentenceTransformerProvider


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m aifs.evidence_cli")
    parser.add_argument(
        "--db", type=Path, default=Path(os.getenv("AIFS_EVIDENCE_DB", "data/aifs-evidence.sqlite3"))
    )
    commands = parser.add_subparsers(dest="command", required=True)
    load = commands.add_parser("import")
    load.add_argument("--input", type=Path, required=True)
    search = commands.add_parser("search")
    search.add_argument("--system", required=True)
    search.add_argument("--calculation")
    search.add_argument("--functional", action="append", default=[])
    search.add_argument("--limit", type=int, default=8)
    return parser


def main() -> int:
    args = _parser().parse_args()
    model_name = os.getenv("AIFS_EMBEDDING_MODEL", "").strip()
    provider = SentenceTransformerProvider(model_name) if model_name else None
    index_path = Path(os.getenv("AIFS_FAISS_INDEX", str(args.db.with_suffix(".faiss"))))
    index = FaissIndex(index_path, provider) if provider else None
    store = EvidenceStore(args.db, faiss_index=index)
    try:
        if args.command == "import":
            print(json.dumps({"imported": import_records(args.input, store)}, ensure_ascii=False))
            return 0
        result = store.search(
            EvidenceSearchRequest(
                system_description=args.system,
                calculation_goal=args.calculation,
                candidate_functionals=args.functional,
                limit=args.limit,
            )
        )
        print(result.model_dump_json(indent=2))
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
