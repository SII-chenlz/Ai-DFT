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
    assert settings.basis_set_pool == "."
    assert settings.embedding_model == ""
    assert (tmp_path / "logs").is_dir()
    assert not (tmp_path / "basis_set_pool").exists()


def test_desktop_direct_card_uses_rest_basis_name_not_dsh_data_directory(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from aifs.api import app
    from aifs.rest import tomllib
    from aifs.rest.validator import validate_rest_input

    for key in (
        "AIFS_WORKFLOW_DB", "AIFS_EVIDENCE_DB", "AIFS_BASIS_SET_POOL", "AIFS_EMBEDDING_MODEL"
    ):
        monkeypatch.setenv(key, "original")
    configure_data(tmp_path)
    response = TestClient(app).post(
        "/v1/rest-inputs/prepare",
        json={
            "system_name": "H2",
            "position": "H 0 0 0\nH 0 0 0.74",
            "position_unit": "angstrom",
            "charge": 0,
            "spin": 1,
            "xc": "PBE",
            "basis": "aug-cc-pVTZ",
            "job_type": "energy",
        },
    )
    assert response.status_code == 200
    card = response.json()
    assert tomllib.loads(card["rest_input"])["ctrl"]["basis_path"] == "aug-cc-pVTZ"
    assert str(tmp_path) not in card["rest_input"]
    assert card["validation"]["valid"]
    assert validate_rest_input(card["rest_input"]).valid


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
