import json

from aifs.evidence_import import import_records
from aifs.evidence_store import EvidenceStore


def test_import_supports_jsonl_and_directories(tmp_path):
    record = {
        "record_id": "MREC-import",
        "source": {"doi": "10.1/import"},
        "context": {"system": "water", "calculation": "opt"},
        "method": {"functional": "PBE"},
        "experience": {"type": "reported_use", "summary": "used"},
        "evidence": [],
    }
    source = tmp_path / "records.jsonl"
    source.write_text(json.dumps(record) + "\n", encoding="utf-8")
    store = EvidenceStore(tmp_path / "db.sqlite3")
    assert import_records(source, store) == 1
    assert import_records(tmp_path, store) == 1
    assert store._connection.execute("SELECT COUNT(*) FROM records").fetchone()[0] == 1
    store.close()
