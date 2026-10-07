import json
import sqlite3
from pathlib import Path

import pytest

from aifs.desktop_launcher import configure_data
from aifs.migrate_desktop import migrate


def test_desktop_data_is_absolute_and_optional_retrieval_is_disabled(tmp_path, monkeypatch):
    from aifs.config import get_settings

    monkeypatch.setenv("AIFS_EMBEDDING_MODEL", "must-not-download")
    for key in ("AIFS_WORKFLOW_DB", "AIFS_EVIDENCE_DB", "AIFS_BASIS_SET_POOL"):
        monkeypatch.setenv(key, "original")
    configure_data(tmp_path)
    settings = get_settings()
    assert settings.workflow_db == str(tmp_path / "aifs-workflow.sqlite3")
    assert settings.evidence_db == str(tmp_path / "aifs-evidence.sqlite3")
    assert settings.embedding_model == ""
    assert (tmp_path / "logs").is_dir()


def test_migration_snapshots_wal_and_preserves_source_and_existing_destination(tmp_path):
    source = tmp_path / "old"
    source.mkdir()
    database = source / "aifs-workflow.sqlite3"
    with sqlite3.connect(database) as original:
        original.execute("PRAGMA journal_mode=WAL")
        original.execute("CREATE TABLE records(value TEXT)")
        original.execute("INSERT INTO records VALUES ('saved-plan')")
        original.commit()
        target = tmp_path / "new"
        report = migrate(source, target)
        with sqlite3.connect(target / database.name) as migrated:
            assert migrated.execute("SELECT value FROM records").fetchone()[0] == "saved-plan"
        with pytest.raises(ValueError, match="already contains"):
            migrate(source, target)
        assert original.execute("SELECT value FROM records").fetchone()[0] == "saved-plan"
    assert json.loads((Path(report["backup"]) / "migration.json").read_text())
