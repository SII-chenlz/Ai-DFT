"""Append-only plan revisions and immutable REST cards in a local SQLite database."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from aifs.config import get_settings
from aifs.evidence_store import EvidenceStore
from aifs.exports import saved_export_path
from aifs.models import DomainValidationError, RestInputRequest
from aifs.rest import tomllib
from aifs.rest.catalogs import GEOMETRY_SOURCE_READ_DATE, SOURCE_READ_DATE, SOURCE_URL
from aifs.rest.renderer import render_rest_input
from aifs.rest.validator import validate_rest_input
from aifs.workflow_models import (
    EvidenceRef,
    PlanDraft,
    PlanPatch,
    PlanTask,
    require_card_ready,
    task_status,
)
from aifs.workflow_schema import (
    PLAN_SCHEMA_VERSION,
    WorkflowError,
    initialize_database,
    load_snapshot,
    require_writable,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _calculation_settings(task: PlanTask) -> dict[str, Any]:
    """Fields that affect a REST calculation, excluding descriptive provenance."""
    decision = task.decision
    return {
        "kind": task.kind,
        "job_type": task.job_type,
        "system_name": task.system_name,
        "inputs": {
            key: getattr(task.inputs, key)
            for key in ("position", "position_unit", "charge", "spin")
        },
        "decision": (
            {
                key: getattr(decision, key)
                for key in ("xc", "xc_parser", "basis", "empirical_dispersion")
            }
            if decision
            else None
        ),
        "rest_options": task.rest_options,
    }


def _invalidate_result_coordinates(
    original: PlanDraft, revised: PlanDraft, supplied_fields: dict[str, set[str]]
) -> PlanDraft:
    """Conservatively invalidate copied results without inventing result verification."""
    before = {task.task_id: task for task in original.tasks}
    after = {task.task_id: task for task in revised.tasks}
    changed_optimizations = {
        task_id
        for task_id, task in before.items()
        if task.kind == "rest"
        and task.job_type == "opt"
        and (
            task_id not in after
            or _calculation_settings(task) != _calculation_settings(after[task_id])
        )
    }
    changed_results: set[str] = set()
    supplied_coordinates: set[str] = set()
    for task in revised.tasks:
        old = before.get(task.task_id)
        fields = supplied_fields.get(task.task_id, set())
        if (
            "position" in fields
            and "position_unit" not in fields
            and (old is None or task.inputs.position != old.inputs.position)
        ):
            # Each newly supplied result needs its own unit, not an inherited
            # unit from the previous result or starting structure.
            task.inputs.position_unit = None
        if old is None or (
            task.inputs.position != old.inputs.position
            or task.inputs.position_unit != old.inputs.position_unit
        ):
            supplied_coordinates.add(task.task_id)
            if task.inputs.position_from_task:
                changed_results.add(task.inputs.position_from_task)
    # An optimization can itself consume another optimization's structure.
    # Continue until invalidation reaches all descendants, independent of task order.
    while True:
        newly_invalidated: set[str] = set()
        for task in revised.tasks:
            old = before.get(task.task_id)
            source = task.inputs.position_from_task
            old_source = old.inputs.position_from_task if old else None
            changed_source_without_coordinates = (
                old is not None
                and (
                    source != old_source
                    or task.inputs.position_source != old.inputs.position_source
                )
                and not {"position", "position_unit"} <= supplied_fields.get(task.task_id, set())
            )
            if (
                source in changed_optimizations
                or old_source in changed_optimizations
                or changed_source_without_coordinates
                or (source in changed_results and task.task_id not in supplied_coordinates)
            ):
                task.inputs.position = None
                task.inputs.position_unit = None
                if task.kind == "rest" and task.job_type == "opt":
                    newly_invalidated.add(task.task_id)
        newly_invalidated -= changed_optimizations
        if not newly_invalidated:
            break
        changed_optimizations.update(newly_invalidated)
    return revised


class WorkflowStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        try:
            initialize_database(self.connection, path)
        except Exception:
            self.connection.close()
            raise

    def close(self) -> None:
        self.connection.close()

    @contextmanager
    def _write_transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connection
        conn.execute("BEGIN IMMEDIATE")
        try:
            require_writable(conn)
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _check_evidence(self, plan: PlanDraft) -> None:
        ids: set[str] = set()
        for task in plan.tasks:
            refs: list[EvidenceRef] = []
            if task.decision:
                refs.extend(task.decision.supporting + task.decision.opposing)
            for candidate in task.candidates:
                refs.extend(candidate.supporting + candidate.opposing)
            for ref in refs:
                if ref.source == "local" and ref.record_id:
                    ids.add(ref.record_id)
        if not ids:
            return
        evidence = EvidenceStore(Path(get_settings().evidence_db))
        try:
            missing = sorted(record_id for record_id in ids if not evidence.has_record(record_id))
        finally:
            evidence.close()
        if missing:
            raise DomainValidationError(
                "unknown_evidence", f"unknown local record IDs: {', '.join(missing)}"
            )

    def create(self, plan: PlanDraft) -> dict[str, Any]:
        require_writable(self.connection)
        self._check_evidence(plan)
        plan_id = str(uuid.uuid4())
        now = _now()
        with self._write_transaction():
            self.connection.execute("INSERT INTO plans VALUES (?, ?, ?)", (plan_id, now, now))
            self.connection.execute(
                "INSERT INTO plan_versions "
                "(plan_id,version,snapshot_json,change_reason,created_at,schema_version) "
                "VALUES (?, 1, ?, ?, ?, ?)",
                (plan_id, plan.model_dump_json(), "initial plan", now, PLAN_SCHEMA_VERSION),
            )
        return self.get(plan_id)

    def revise(
        self,
        plan_id: str,
        expected_version: int,
        reason: str,
        plan: PlanDraft | None = None,
        *,
        patch: PlanPatch | None = None,
    ) -> dict[str, Any]:
        require_writable(self.connection)
        if (plan is None) == (patch is None):
            raise DomainValidationError(
                "invalid_plan_revision", "provide exactly one of plan or patch"
            )
        with self._write_transaction() as conn:
            row = conn.execute(
                "SELECT * FROM plan_versions WHERE plan_id = ? ORDER BY version DESC LIMIT 1",
                (plan_id,),
            ).fetchone()
            if row is None or row["version"] is None:
                raise WorkflowError("plan_not_found", "plan not found")
            if row["version"] != expected_version:
                raise WorkflowError(
                    "version_conflict", "plan was revised; reload before editing", 409
                )
            original = load_snapshot(row["snapshot_json"], row["schema_version"])
            if patch is not None:
                try:
                    plan = patch.apply_to(original)
                except ValidationError as exc:
                    detail = "; ".join(
                        f"{'.'.join(map(str, error['loc']))}: {error['msg']}"
                        for error in exc.errors(include_input=False, include_url=False)
                    )
                    raise DomainValidationError("invalid_plan_patch", detail) from exc
                except ValueError as exc:
                    raise DomainValidationError("invalid_plan_patch", str(exc)) from exc
            assert plan is not None
            supplied_fields = {
                task.task_id: task.inputs.model_fields_set
                for task in ((patch.tasks or []) if patch else plan.tasks)
                if "inputs" in task.model_fields_set and task.inputs is not None
            }
            if patch:
                supplied_fields.update(
                    {task.task_id: task.inputs.model_fields_set for task in patch.add_tasks}
                )
            plan = _invalidate_result_coordinates(
                original, plan.model_copy(deep=True), supplied_fields
            )
            self._check_evidence(plan)
            version = expected_version + 1
            now = _now()
            conn.execute(
                "INSERT INTO plan_versions "
                "(plan_id,version,snapshot_json,change_reason,created_at,schema_version) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (plan_id, version, plan.model_dump_json(), reason, now, PLAN_SCHEMA_VERSION),
            )
            conn.execute("UPDATE plans SET updated_at = ? WHERE plan_id = ?", (now, plan_id))
        return self.get(plan_id)

    def list(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT p.plan_id, p.created_at, p.updated_at, v.version,
                   v.snapshot_json, v.schema_version
            FROM plans p JOIN plan_versions v ON v.plan_id = p.plan_id
            WHERE v.version = (SELECT MAX(version) FROM plan_versions WHERE plan_id = p.plan_id)
            ORDER BY p.updated_at DESC
            """
        ).fetchall()
        summaries = []
        for row in rows:
            draft = load_snapshot(row["snapshot_json"], row["schema_version"])
            summaries.append(
                {
                    "plan_id": row["plan_id"],
                    "version": row["version"],
                    "goal": draft.goal,
                    "question": draft.question,
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
        return summaries

    def get(self, plan_id: str, version: int | None = None) -> dict[str, Any]:
        if version is None:
            row = self.connection.execute(
                "SELECT * FROM plan_versions WHERE plan_id = ? ORDER BY version DESC LIMIT 1",
                (plan_id,),
            ).fetchone()
        else:
            row = self.connection.execute(
                "SELECT * FROM plan_versions WHERE plan_id = ? AND version = ?", (plan_id, version)
            ).fetchone()
        if row is None:
            raise WorkflowError("plan_not_found", "plan or version not found")
        draft = load_snapshot(row["snapshot_json"], row["schema_version"])
        by_id = {task.task_id: task for task in draft.tasks}
        card_rows = self.connection.execute(
            "SELECT card_id, task_id, filename, sha256, created_at, version, content FROM cards "
            "WHERE plan_id = ? AND version <= ? ORDER BY version DESC, created_at DESC",
            (plan_id, row["version"]),
        ).fetchall()
        expected_contents = {task.task_id: self._ready_content(task, by_id) for task in draft.tasks}
        latest_row = self.connection.execute(
            "SELECT * FROM plan_versions WHERE plan_id = ? ORDER BY version DESC LIMIT 1",
            (plan_id,),
        ).fetchone()
        if latest_row["version"] == row["version"]:
            current_contents = expected_contents
        else:
            try:
                current_draft = load_snapshot(
                    latest_row["snapshot_json"], latest_row["schema_version"]
                )
                current_by_id = {task.task_id: task for task in current_draft.tasks}
                current_contents = {
                    task.task_id: self._ready_content(task, current_by_id)
                    for task in current_draft.tasks
                }
            except WorkflowError:
                current_contents = {}
        cards = []
        card_task_ids: set[str] = set()
        for card in card_rows:
            applicable = expected_contents.get(card["task_id"]) == card["content"]
            if card["task_id"] in card_task_ids:
                continue
            if card["version"] != row["version"] and not applicable:
                continue
            item = dict(card)
            item.pop("content")
            item["export_relative_path"] = saved_export_path(
                plan_id, card["task_id"], card["filename"]
            )
            item["is_current_plan_version"] = card["version"] == latest_row["version"]
            item["is_applicable_to_current_plan"] = (
                current_contents.get(card["task_id"]) == card["content"]
            )
            cards.append(item)
            if applicable:
                card_task_ids.add(card["task_id"])
        return {
            "plan_id": plan_id,
            "version": row["version"],
            "change_reason": row["change_reason"],
            "created_at": row["created_at"],
            "plan": draft.model_dump(),
            "statuses": [
                task_status(task, by_id, has_card=task.task_id in card_task_ids).model_dump()
                for task in draft.tasks
            ],
            "cards": cards,
        }

    @staticmethod
    def _request_for_task(task: PlanTask) -> RestInputRequest:
        assert task.decision is not None
        assert task.inputs.position is not None
        assert task.inputs.position_unit is not None
        assert task.inputs.charge is not None
        assert task.inputs.spin is not None
        return RestInputRequest(
            system_name=task.system_name,
            position=task.inputs.position,
            position_unit=task.inputs.position_unit,
            job_type=task.job_type,
            xc=task.decision.xc,
            xc_parser=task.decision.xc_parser,
            rest_options=task.rest_options,
            basis=task.decision.basis,
            empirical_dispersion=task.decision.empirical_dispersion,
            charge=task.inputs.charge,
            spin=task.inputs.spin,
        )

    @classmethod
    def _ready_content(cls, task: PlanTask, by_id: dict[str, PlanTask]) -> str | None:
        if task_status(task, by_id).state != "ready_for_card":
            return None
        try:
            rendered = render_rest_input(cls._request_for_task(task))
            return rendered.rest_input if validate_rest_input(rendered.rest_input).valid else None
        except (DomainValidationError, ValidationError):
            return None

    def generate_card(self, plan_id: str, task_id: str) -> dict[str, Any]:
        require_writable(self.connection)
        view = self.get(plan_id)
        version = view["version"]
        draft = PlanDraft.model_validate(view["plan"])
        by_id = {task.task_id: task for task in draft.tasks}
        task: PlanTask | None = by_id.get(task_id)
        if task is None:
            raise WorkflowError("task_not_found", "task not found")
        require_card_ready(task, by_id)
        request = self._request_for_task(task)
        rendered = render_rest_input(request)
        validation = validate_rest_input(rendered.rest_input)
        if not validation.valid:
            raise DomainValidationError(
                "card_validation_failed", "generated card failed independent validation"
            )
        card_id = str(uuid.uuid4())
        filename = f"aifs-{plan_id[:8]}-{task_id}-v{version}.in"
        digest = hashlib.sha256(rendered.rest_input.encode("utf-8")).hexdigest()
        render_metadata = {
            "geometry_unit_source_date": GEOMETRY_SOURCE_READ_DATE,
            "geometry_unit_source_url": SOURCE_URL,
            "effective_settings": rendered.effective_settings,
            "defaults_applied": rendered.defaults_applied,
            "warnings": rendered.warnings,
        }
        with self._write_transaction():
            latest = self.connection.execute(
                "SELECT MAX(version) FROM plan_versions WHERE plan_id = ?", (plan_id,)
            ).fetchone()[0]
            if latest != version:
                raise WorkflowError(
                    "version_conflict", "plan was revised; reload before generating", 409
                )
            existing = self.connection.execute(
                "SELECT card_id FROM cards WHERE plan_id = ? AND task_id = ? AND content = ? "
                "ORDER BY version DESC LIMIT 1",
                (plan_id, task_id, rendered.rest_input),
            ).fetchone()
            if existing:
                return self.get_card(plan_id, existing["card_id"])
            self.connection.execute(
                "INSERT OR IGNORE INTO cards VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    card_id,
                    plan_id,
                    version,
                    task_id,
                    filename,
                    rendered.rest_input,
                    digest,
                    request.model_dump_json(),
                    json.dumps(render_metadata, ensure_ascii=False),
                    validation.model_dump_json(),
                    SOURCE_READ_DATE,
                    SOURCE_URL,
                    _now(),
                ),
            )
        saved = self.connection.execute(
            "SELECT card_id FROM cards WHERE plan_id = ? AND version = ? AND task_id = ?",
            (plan_id, version, task_id),
        ).fetchone()
        return self.get_card(plan_id, saved["card_id"])

    def get_card(self, plan_id: str, card_id: str) -> dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM cards WHERE plan_id = ? AND card_id = ?", (plan_id, card_id)
        ).fetchone()
        if row is None:
            raise WorkflowError("card_not_found", "card not found")
        result = dict(row)
        result["request"] = json.loads(result.pop("request_json"))
        result["render"] = json.loads(result.pop("render_json"))
        result["validation"] = json.loads(result.pop("validation_json"))
        # History stays immutable. Expose the actual card keyword even for cards
        # saved before units were recorded, without inferring a source unit.
        try:
            unit = tomllib.loads(result["content"]).get("geom", {}).get("unit")
        except (tomllib.TOMLDecodeError, AttributeError):
            unit = None
        result["position_unit"] = unit
        result["position_unit_status"] = "explicit" if unit is not None else "not_recorded"
        latest = self.connection.execute(
            "SELECT MAX(version) AS version FROM plan_versions WHERE plan_id = ?", (plan_id,)
        ).fetchone()
        result["is_current_plan_version"] = result["version"] == latest["version"]
        current = self.connection.execute(
            "SELECT snapshot_json, schema_version FROM plan_versions WHERE plan_id = ? "
            "AND version = ?",
            (plan_id, latest["version"]),
        ).fetchone()
        try:
            draft = load_snapshot(current["snapshot_json"], current["schema_version"])
            by_id = {task.task_id: task for task in draft.tasks}
            task = by_id.get(result["task_id"])
            applicable = task is not None and self._ready_content(task, by_id) == result["content"]
        except WorkflowError:
            # A newer/unsupported snapshot cannot certify applicability, but must
            # not make a historical immutable input file impossible to download.
            applicable = False
        result["is_applicable_to_current_plan"] = applicable
        result["export_relative_path"] = saved_export_path(
            plan_id, result["task_id"], result["filename"]
        )
        result["download_path"] = f"/v1/plans/{plan_id}/cards/{card_id}/download"
        return result
