"""Real legacy SQLite files, including WAL, rollback and immutable old cards."""

import hashlib
import json
import sqlite3

import pytest

from aifs.workflow_models import PlanDraft, PlanPatch
from aifs.workflow_store import WorkflowError, WorkflowStore

LEGACY_SQL = """
CREATE TABLE plans(plan_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE plan_versions(plan_id TEXT NOT NULL REFERENCES plans(plan_id),
version INTEGER NOT NULL,
snapshot_json TEXT NOT NULL, change_reason TEXT NOT NULL, created_at TEXT NOT NULL,
PRIMARY KEY(plan_id, version));
CREATE TABLE cards(card_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, version INTEGER NOT NULL,
task_id TEXT NOT NULL, filename TEXT NOT NULL, content TEXT NOT NULL, sha256 TEXT NOT NULL,
request_json TEXT NOT NULL, render_json TEXT NOT NULL, validation_json TEXT NOT NULL,
catalog_source_date TEXT NOT NULL, catalog_source_url TEXT NOT NULL, created_at TEXT NOT NULL,
FOREIGN KEY(plan_id, version) REFERENCES plan_versions(plan_id, version),
UNIQUE(plan_id,version,task_id));
"""


def legacy_database(path):
    raw = json.dumps(
        {
            "question": "old calculation",
            "goal": "other",
            "tasks": [
                {
                    "task_id": "old",
                    "title": "H2",
                    "purpose": "Energy",
                    "kind": "rest",
                    "job_type": "energy",
                    "system_name": "H2",
                    "inputs": {
                        "position": "H 0 0 0\nH 0 0 0.74",
                        "position_source": "user",
                        "charge": 0,
                        "charge_source": "user",
                        "spin": 1,
                        "spin_source": "user",
                    },
                    "decision": {
                        "xc": "PBE",
                        "basis": "",
                        "source": "user",
                        "rationale": "old choice",
                    },
                }
            ],
        }
    )
    content = '[geom]\nname = "old"\nposition = "H 0 0 0"\n'
    digest = hashlib.sha256(content.encode()).hexdigest()
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript(LEGACY_SQL)
    connection.execute("INSERT INTO plans VALUES ('p', 'then', 'then')")
    connection.execute("INSERT INTO plan_versions VALUES ('p',1,?,'initial','then')", (raw,))
    connection.execute(
        "INSERT INTO cards VALUES "
        "('c','p',1,'old','old.in',?,?, '{}','{}','{}','old','url','then')",
        (content, digest),
    )
    connection.commit()
    return connection, raw, content, digest


def test_legacy_upgrade_backs_up_wal_preserves_history_and_is_idempotent(tmp_path):
    path = tmp_path / "workflow.sqlite3"
    original, raw, content, digest = legacy_database(path)
    try:
        store = WorkflowStore(path)
        assert store.connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert (
            store.connection.execute("SELECT schema_version FROM plan_versions").fetchone()[0] == 0
        )
        assert (
            store.connection.execute("SELECT snapshot_json FROM plan_versions").fetchone()[0] == raw
        )
        plan = store.get("p")
        assert plan["plan"]["tasks"][0]["decision"]["basis"] is None
        assert plan["plan"]["tasks"][0]["inputs"]["position_unit"] is None
        assert plan["statuses"][0]["state"] == "needs_input"
        card = store.get_card("p", "c")
        assert (card["content"], card["sha256"]) == (content, digest)
        store.close()
        backups = list((tmp_path / "schema-backups").glob("*.sqlite3"))
        assert len(backups) == 1
        with sqlite3.connect(backups[0]) as backup:
            assert backup.execute("PRAGMA user_version").fetchone()[0] == 0
            assert backup.execute("SELECT snapshot_json FROM plan_versions").fetchone()[0] == raw
        reopened = WorkflowStore(path)
        draft = plan["plan"]
        draft["tasks"][0]["inputs"]["position_unit"] = "angstrom"
        draft["tasks"][0]["decision"]["basis"] = "def2-TZVP"
        revised = reopened.revise(
            "p", 1, "Confirmed missing inputs", PlanDraft.model_validate(draft)
        )
        assert revised["version"] == 2
        assert (
            reopened.connection.execute(
                "SELECT schema_version FROM plan_versions WHERE version=2"
            ).fetchone()[0]
            == 1
        )
        assert reopened.get_card("p", "c")["content"] == content
        reopened.close()
        assert list((tmp_path / "schema-backups").glob("*.sqlite3")) == backups
    finally:
        original.close()


def test_failed_upgrade_rolls_back_and_retains_backup(tmp_path, monkeypatch):
    import aifs.workflow_schema as schema

    path = tmp_path / "workflow.sqlite3"
    original, raw, _, _ = legacy_database(path)
    original.close()
    real_upgrade = schema.upgrade_legacy

    def fail(connection):
        real_upgrade(connection)
        raise RuntimeError("simulated interruption")

    monkeypatch.setattr(schema, "upgrade_legacy", fail)
    with pytest.raises(WorkflowError, match="upgrade"):
        WorkflowStore(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
        assert "schema_version" not in [
            row[1] for row in conn.execute("PRAGMA table_info(plan_versions)")
        ]
        assert conn.execute("SELECT snapshot_json FROM plan_versions").fetchone()[0] == raw
    assert len(list((tmp_path / "schema-backups").glob("*.sqlite3"))) == 1


def test_future_database_is_rejected_without_writes(tmp_path):
    path = tmp_path / "workflow.sqlite3"
    store = WorkflowStore(path)
    store.connection.execute("PRAGMA user_version=99")
    store.close()
    before = path.read_bytes()
    with pytest.raises(WorkflowError, match="newer"):
        WorkflowStore(path)
    assert path.read_bytes() == before


def test_future_snapshot_refuses_read_and_all_new_writes(tmp_path):
    path = tmp_path / "workflow.sqlite3"
    original, _, _, _ = legacy_database(path)
    original.close()
    store = WorkflowStore(path)
    draft = PlanDraft.model_validate(store.get("p")["plan"])
    store.connection.execute("UPDATE plan_versions SET schema_version=99")
    store.connection.commit()
    before = path.read_bytes()
    for action in (
        lambda: store.get("p"),
        lambda: store.create(draft),
        lambda: store.revise("p", 1, "attempt", draft),
        lambda: store.generate_card("p", "old"),
    ):
        with pytest.raises(WorkflowError, match="newer"):
            action()
    store.close()
    assert path.read_bytes() == before


def test_fresh_database_needs_no_backup(tmp_path):
    store = WorkflowStore(tmp_path / "new.sqlite3")
    assert store.connection.execute("PRAGMA user_version").fetchone()[0] == 1
    store.close()
    assert not (tmp_path / "schema-backups").exists()


def test_future_database_returns_a_structured_api_error(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from aifs.api import app
    from aifs.config import get_settings

    path = tmp_path / "future.sqlite3"
    store = WorkflowStore(path)
    store.connection.execute("PRAGMA user_version=99")
    store.close()
    monkeypatch.setenv("AIFS_WORKFLOW_DB", str(path))
    get_settings.cache_clear()
    response = TestClient(app).get("/v1/plans")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "database_too_new"


def test_invalid_stored_snapshot_returns_a_structured_error_without_changes(tmp_path):
    path = tmp_path / "workflow.sqlite3"
    original, _, _, _ = legacy_database(path)
    original.close()
    store = WorkflowStore(path)
    store.connection.execute("UPDATE plan_versions SET snapshot_json='[]'")
    store.connection.commit()
    with pytest.raises(WorkflowError) as failure:
        store.get("p")
    assert failure.value.code == "invalid_plan_snapshot"
    assert store.connection.execute("SELECT snapshot_json FROM plan_versions").fetchone()[0] == "[]"
    store.close()


@pytest.mark.parametrize("operation", ["create", "revise", "revise_patch", "generate_card"])
def test_future_format_written_during_preparation_blocks_the_transaction(
    tmp_path, monkeypatch, operation
):
    import aifs.workflow_store as module

    path = tmp_path / "workflow.sqlite3"
    store = WorkflowStore(path)
    draft = PlanDraft.model_validate(
        {
            "question": "H2 energy",
            "goal": "other",
            "tasks": [
                {
                    "task_id": "h2",
                    "title": "H2",
                    "purpose": "Energy",
                    "kind": "rest",
                    "job_type": "energy",
                    "system_name": "H2",
                    "inputs": {
                        "position": "H 0 0 0\nH 0 0 0.74",
                        "position_unit": "angstrom",
                        "position_source": "user",
                        "charge": 0,
                        "charge_source": "user",
                        "spin": 1,
                        "spin_source": "user",
                    },
                    "decision": {
                        "xc": "PBE",
                        "basis": "def2-TZVP",
                        "source": "user",
                        "rationale": "confirmed",
                    },
                }
            ],
        }
    )
    plan = store.create(draft)

    def newer_program_writes():
        with sqlite3.connect(path) as other:
            other.execute("PRAGMA user_version=99")

    if operation == "generate_card":
        render = module.render_rest_input

        def prepare(request):
            newer_program_writes()
            return render(request)

        monkeypatch.setattr(module, "render_rest_input", prepare)

        def action():
            return store.generate_card(plan["plan_id"], "h2")
    elif operation == "create":
        monkeypatch.setattr(store, "_check_evidence", lambda _: newer_program_writes())

        def action():
            return store.create(draft)
    else:
        # Revision now checks evidence while holding BEGIN IMMEDIATE. Inject
        # the newer format before acquiring the lock, not through a writer
        # that SQLite correctly blocks inside the transaction.
        from contextlib import contextmanager

        transaction = store._write_transaction

        @contextmanager
        def before_transaction():
            newer_program_writes()
            with transaction() as connection:
                yield connection

        monkeypatch.setattr(store, "_write_transaction", before_transaction)

        def action():
            if operation == "revise_patch":
                return store.revise(plan["plan_id"], 1, "attempt", patch=PlanPatch(question="new"))
            return store.revise(plan["plan_id"], 1, "attempt", draft)

    with pytest.raises(WorkflowError, match="newer"):
        action()
    assert store.connection.execute("SELECT COUNT(*) FROM plans").fetchone()[0] == 1
    assert store.connection.execute("SELECT COUNT(*) FROM plan_versions").fetchone()[0] == 1
    assert store.connection.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 0
    store.close()


@pytest.mark.parametrize("partial", [False, True])
def test_revision_lock_prevents_a_competing_format_write(tmp_path, monkeypatch, partial):
    path = tmp_path / "workflow.sqlite3"
    original, _, content, _ = legacy_database(path)
    original.close()
    store = WorkflowStore(path)
    before = store.get("p")
    evidence_check = store._check_evidence
    attempts = []

    def check_while_locked(draft):
        with sqlite3.connect(path, timeout=0) as other:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                other.execute("PRAGMA user_version=99")
            attempts.append(True)
        evidence_check(draft)

    monkeypatch.setattr(store, "_check_evidence", check_while_locked)
    try:
        if partial:
            result = store.revise("p", 1, "new question", patch=PlanPatch(question="updated"))
        else:
            draft = PlanDraft.model_validate(before["plan"])
            draft.question = "updated"
            result = store.revise("p", 1, "new question", draft)
        assert attempts == [True]
        assert result["version"] == 2
        assert result["plan"]["question"] == "updated"
        assert result["plan"]["tasks"] == before["plan"]["tasks"]
        assert store.get("p", 1)["plan"] == before["plan"]
        assert store.get_card("p", "c")["content"] == content
        assert store.connection.execute("PRAGMA user_version").fetchone()[0] == 1
    finally:
        store.close()
