"""Workflow database upgrades and version-dispatched immutable snapshot reads."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from aifs.workflow_models import PlanDraft

DATABASE_VERSION = 1
PLAN_SCHEMA_VERSION = 1


class WorkflowError(Exception):
    def __init__(self, code: str, message: str, status: int = 404) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


TABLE_SQL = (
    "CREATE TABLE plans (plan_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, "
    "updated_at TEXT NOT NULL)",
    "CREATE TABLE plan_versions (plan_id TEXT NOT NULL REFERENCES plans(plan_id), "
    "version INTEGER NOT NULL, snapshot_json TEXT NOT NULL, change_reason TEXT NOT NULL, "
    "created_at TEXT NOT NULL, schema_version INTEGER NOT NULL, PRIMARY KEY(plan_id,version))",
    "CREATE TABLE cards (card_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, "
    "version INTEGER NOT NULL, "
    "task_id TEXT NOT NULL, filename TEXT NOT NULL, content TEXT NOT NULL, sha256 TEXT NOT NULL, "
    "request_json TEXT NOT NULL, render_json TEXT NOT NULL, validation_json TEXT NOT NULL, "
    "catalog_source_date TEXT NOT NULL, catalog_source_url TEXT NOT NULL, "
    "created_at TEXT NOT NULL, "
    "FOREIGN KEY(plan_id,version) REFERENCES plan_versions(plan_id,version), "
    "UNIQUE(plan_id,version,task_id))",
)
LEGACY_COLUMNS = {
    "plans": {"plan_id", "created_at", "updated_at"},
    "plan_versions": {"plan_id", "version", "snapshot_json", "change_reason", "created_at"},
    "cards": {
        "card_id",
        "plan_id",
        "version",
        "task_id",
        "filename",
        "content",
        "sha256",
        "request_json",
        "render_json",
        "validation_json",
        "catalog_source_date",
        "catalog_source_url",
        "created_at",
    },
}


def upgrade_legacy(connection: sqlite3.Connection) -> None:
    # Version 0 is the pre-versioned plan format; preserve JSON and card bytes.
    connection.execute(
        "ALTER TABLE plan_versions ADD COLUMN schema_version INTEGER NOT NULL DEFAULT 0"
    )


def initialize_database(connection: sqlite3.Connection, path: Path) -> None:
    """Serialize upgrades; backup committed data including WAL before any DDL."""
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version > DATABASE_VERSION:
        raise WorkflowError("database_too_new", "Workflow database is newer than AIFS", 409)
    if version == DATABASE_VERSION:
        _check_structure(connection, current=True)
        return
    try:
        connection.execute("BEGIN IMMEDIATE")
        # Another request may have upgraded while this connection waited.
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version > DATABASE_VERSION:
            raise WorkflowError("database_too_new", "Workflow database is newer than AIFS", 409)
        if version == DATABASE_VERSION:
            _check_structure(connection, current=True)
            connection.commit()
            return
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        if tables:
            _check_structure(connection, current=False)
            directory = path.parent / "schema-backups"
            directory.mkdir(exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            backup_path = directory / f"{path.name}.v0-{stamp}-{uuid.uuid4().hex[:8]}.sqlite3"
            # A separate reader avoids sqlite backup hanging on this write transaction.
            with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as reader:
                with sqlite3.connect(backup_path) as backup:
                    reader.backup(backup)
                    if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise ValueError("Workflow backup integrity check failed")
            upgrade_legacy(connection)
        else:
            for statement in TABLE_SQL:
                connection.execute(statement)
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Workflow upgrade integrity check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("Workflow upgrade has broken references")
        connection.execute(f"PRAGMA user_version={DATABASE_VERSION}")
        connection.commit()
    except Exception as exc:
        connection.rollback()
        if isinstance(exc, WorkflowError):
            raise
        raise WorkflowError(
            "database_upgrade_failed", f"Workflow database upgrade failed: {exc}", 409
        ) from exc


def _check_structure(connection: sqlite3.Connection, *, current: bool) -> None:
    for table, legacy in LEGACY_COLUMNS.items():
        actual = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        expected = legacy | ({"schema_version"} if current and table == "plan_versions" else set())
        if actual != expected:
            raise WorkflowError(
                "unrecognized_database", f"Unrecognized workflow database structure: {table}", 409
            )


def require_writable(connection: sqlite3.Connection) -> None:
    if connection.execute("PRAGMA user_version").fetchone()[0] != DATABASE_VERSION:
        raise WorkflowError("database_too_new", "Workflow database is newer or incompatible", 409)
    if connection.execute(
        "SELECT 1 FROM plan_versions WHERE schema_version NOT IN (0, ?) LIMIT 1",
        (PLAN_SCHEMA_VERSION,),
    ).fetchone():
        raise WorkflowError(
            "plan_schema_too_new", "Saved plan format is newer or incompatible", 409
        )


def _legacy_snapshot(data: dict) -> dict:
    """Known compatibility only; never infer coordinates, units or decisions."""
    for task in data.get("tasks", []):
        decision = task.get("decision")
        if isinstance(decision, dict) and isinstance(decision.get("basis"), str):
            if not decision["basis"].strip():
                decision["basis"] = None
    return data


def load_snapshot(raw: str, schema_version: int) -> PlanDraft:
    # Future versions must register explicit adapters here and fixture their history.
    adapters = {0: _legacy_snapshot, PLAN_SCHEMA_VERSION: lambda data: data}
    if schema_version not in adapters:
        raise WorkflowError(
            "plan_schema_too_new", "Saved plan format is newer or incompatible", 409
        )
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("plan snapshot must be an object")
        return PlanDraft.model_validate(adapters[schema_version](data))
    except (ValueError, TypeError, AttributeError, ValidationError) as exc:
        raise WorkflowError(
            "invalid_plan_snapshot", "Saved plan is incompatible; original data was preserved", 409
        ) from exc
