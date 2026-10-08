"""Meaningful workflow scenarios across persistence, state gates and downloads."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from copy import deepcopy
from pathlib import Path, PurePosixPath

import pytest
from fastapi.testclient import TestClient

from aifs.api import app
from aifs.config import get_settings
from aifs.rest import tomllib


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("AIFS_WORKFLOW_DB", str(tmp_path / "workflow.sqlite3"))
    monkeypatch.setenv("AIFS_EVIDENCE_DB", str(tmp_path / "evidence.sqlite3"))
    monkeypatch.setenv("AIFS_BASIS_SET_POOL", str(tmp_path / "basis"))
    get_settings.cache_clear()
    return TestClient(app)


def _task(task_id: str, job_type: str, *, decision: bool = True) -> dict:
    return {
        "task_id": task_id,
        "title": f"Calculate {task_id}",
        "purpose": "Obtain electronic energy",
        "kind": "rest",
        "job_type": job_type,
        "system_name": task_id,
        "inputs": {
            "position": "H 0 0 0\nH 0 0 0.74",
            "position_source": "user",
            "position_unit": "angstrom",
            "charge": 0,
            "charge_source": "user",
            "spin": 1,
            "spin_source": "user",
        },
        "decision": {
            "xc": "PBE",
            "basis": "def2-TZVPP",
            "source": "user",
            "rationale": "The user selected PBE; no literature ranking is claimed.",
        }
        if decision
        else None,
    }


def _reaction() -> dict:
    return {
        "question": "Calculate A + B -> C electronic reaction energy",
        "goal": "reaction_energy",
        "tasks": [
            _task("A", "energy"),
            _task("B", "energy"),
            _task("C", "energy"),
            {
                "task_id": "delta_e",
                "title": "Combine energies",
                "purpose": "Compute reaction electronic energy",
                "kind": "analysis",
                "depends_on": ["A", "B", "C"],
                "analysis_formula": "E(C)-E(A)-E(B)",
            },
        ],
    }


def test_saved_exports_keep_one_plan_directory_and_task_history_after_revision(api):
    saved = api.post("/v1/plans", json=_reaction()).json()
    plan_url = f"/v1/plans/{saved['plan_id']}"
    first = api.post(plan_url + "/tasks/A/cards").json()
    other = api.post(plan_url + "/tasks/B/cards").json()
    first_path = PurePosixPath(first["export_relative_path"])
    other_path = PurePosixPath(other["export_relative_path"])
    assert first_path.parts[:2] == other_path.parts[:2]
    assert first_path.parent != other_path.parent
    assert first_path.name == first["filename"]
    assert not first_path.is_absolute() and ".." not in first_path.parts
    reply = api.put(plan_url, json={
        "expected_version": 1,
        "change_reason": "Change method and display text",
        "patch": {"question": "Renamed workflow", "tasks": [{
            "task_id": "A", "title": "Renamed task", "decision": {"xc": "PBE0"},
        }]},
    })
    assert reply.status_code == 200, reply.text
    updated = api.post(plan_url + "/tasks/A/cards").json()
    assert PurePosixPath(updated["export_relative_path"]).parent == first_path.parent
    assert updated["export_relative_path"] != first["export_relative_path"]
    historical = api.get(plan_url + f"/cards/{first['card_id']}").json()
    assert historical["export_relative_path"] == first["export_relative_path"]
    assert historical["content"] == first["content"]
    assert api.get(first["download_path"]).text == first["content"]
    current = api.get(plan_url).json()
    assert next(c for c in current["cards"] if c["card_id"] == updated["card_id"])[
        "export_relative_path"
    ] == updated["export_relative_path"]


def test_partial_revision_preserves_other_tasks_evidence_and_historical_cards(api):
    draft = _reaction()
    draft["tasks"][0]["decision"]["supporting"] = [
        {
            "source": "web",
            "url": "https://example.org/paper",
            "title": "Method study",
            "note": "Reports the method used, not a ranking",
            "claim_type": "method_used",
        }
    ]
    saved = api.post("/v1/plans", json=draft).json()
    path = f"/v1/plans/{saved['plan_id']}"
    old_card = api.post(path + "/tasks/A/cards").json()
    reply = api.put(
        path,
        json={
            "expected_version": 1,
            "change_reason": "User selected another basis for A",
            "patch": {"tasks": [{"task_id": "A", "decision": {"basis": "def2-TZVP"}}]},
        },
    )
    assert reply.status_code == 200, reply.text
    revised = reply.json()
    assert revised["version"] == 2
    before = saved["plan"]["tasks"][0]
    after = revised["plan"]["tasks"][0]
    assert after["decision"]["basis"] == "def2-TZVP"
    assert after["decision"]["xc"] == "PBE"
    assert after["decision"]["supporting"] == before["decision"]["supporting"]
    assert revised["plan"]["tasks"][1:] == saved["plan"]["tasks"][1:]
    assert api.get(path + "?version=1").json()["plan"] == saved["plan"]
    assert api.get(old_card["download_path"]).text == old_card["content"]
    new_card = api.post(path + "/tasks/A/cards").json()
    assert new_card["request"]["basis"] == "def2-TZVP"
    stale = api.put(
        path,
        json={
            "expected_version": 1,
            "change_reason": "stale update",
            "patch": {"question": "stale"},
        },
    )
    assert stale.status_code == 409
    assert api.get(path).json()["version"] == 2


def test_partial_result_revision_keeps_source_and_unknown_units_block_cards(api):
    opt, sp = _task("opt", "opt"), _task("sp", "energy")
    sp["depends_on"] = ["opt"]
    sp["inputs"].update(
        position=None, position_unit=None, position_source="prior_result", position_from_task="opt"
    )
    saved = api.post(
        "/v1/plans",
        json={
            "question": "Optimize then energy",
            "goal": "optimization_single_point",
            "tasks": [opt, sp],
        },
    ).json()
    path = f"/v1/plans/{saved['plan_id']}"
    reply = api.put(
        path,
        json={
            "expected_version": 1,
            "change_reason": "Actual output",
            "patch": {
                "tasks": [
                    {
                        "task_id": "sp",
                        "inputs": {"position": "H 0 0 0\nH 0 0 1.4", "position_unit": "bohr"},
                    }
                ]
            },
        },
    )
    assert reply.status_code == 200, reply.text
    task = reply.json()["plan"]["tasks"][1]
    assert task["inputs"]["position_from_task"] == "opt"
    assert task["inputs"]["position_source"] == "prior_result"
    assert task["inputs"]["charge_source"] == "user"
    assert api.post(path + "/tasks/sp/cards").json()["position_unit"] == "bohr"
    cleared = api.put(
        path,
        json={
            "expected_version": 2,
            "change_reason": "Unit uncertain",
            "patch": {"tasks": [{"task_id": "sp", "inputs": {"position_unit": None}}]},
        },
    )
    assert cleared.status_code == 200
    assert cleared.json()["statuses"][1]["state"] == "needs_input"
    assert api.post(path + "/tasks/sp/cards").status_code == 422


def _result_workflow() -> dict:
    """Two optimizations with the geometry consumers used for ADE/VDE and ZPE."""
    tasks = [_task("opt_anion", "opt"), _task("opt_neutral", "opt")]
    for task_id, source in (
        ("anion_energy", "opt_anion"),
        ("neutral_energy", "opt_neutral"),
        ("vertical_energy", "opt_anion"),
        ("anion_frequency", "opt_anion"),
        ("neutral_frequency", "opt_neutral"),
    ):
        task = _task(task_id, "energy")
        task["depends_on"] = [source]
        task["inputs"].update(position_source="prior_result", position_from_task=source)
        if "frequency" in task_id:
            task["rest_options"] = {"ctrl": {"analdrv_tasks": ["hessian"]}}
        tasks.append(task)
    return {"question": "Prepare detachment energy and ZPE steps", "goal": "other", "tasks": tasks}


@pytest.mark.parametrize("job", ["energy", "force", "numerical dipole"])
def test_every_rest_optimization_consumer_requires_explicit_result_source(api, job):
    opt, consumer = _task("opt", "opt"), _task("property", job)
    consumer["depends_on"] = ["opt"]
    body = {"question": "Optimize then property", "goal": "other", "tasks": [opt, consumer]}
    saved = api.post("/v1/plans", json=body).json()
    path = f"/v1/plans/{saved['plan_id']}"
    assert saved["statuses"][1]["state"] == "needs_input"
    consumer["inputs"]["position_source"] = "external_optimized"
    response = api.put(
        path, json={"expected_version": 1, "change_reason": "external result", "plan": body}
    )
    assert response.status_code == 200
    assert response.json()["statuses"][1]["state"] == "needs_input"
    consumer["inputs"].update(position_from_task="opt", position_unit="bohr")
    response = api.put(
        path, json={"expected_version": 2, "change_reason": "identify result", "plan": body}
    )
    assert response.status_code == 200, response.text
    card = api.post(path + "/tasks/property/cards")
    assert card.status_code == 201, card.text
    assert card.json()["position_unit"] == "bohr"
    standalone = deepcopy(consumer)
    standalone["depends_on"] = []
    standalone["inputs"]["position_from_task"] = None
    response = api.post(
        "/v1/plans", json={"question": "External structure", "goal": "other", "tasks": [standalone]}
    )
    assert response.status_code == 201
    assert response.json()["statuses"][0]["state"] == "ready_for_card"


def test_old_nonoptimization_result_source_is_readable_but_cannot_generate(api):
    parent, consumer = _task("energy", "energy"), _task("property", "force")
    consumer["depends_on"] = ["energy"]
    consumer["inputs"].update(position_source="prior_result", position_from_task="energy")
    response = api.post(
        "/v1/plans",
        json={"question": "Historical source", "goal": "other", "tasks": [parent, consumer]},
    )
    assert response.status_code == 201
    saved = response.json()
    assert saved["statuses"][1]["state"] == "needs_input"
    assert "optimization task" in str(saved["statuses"][1]["blockers"])
    path = f"/v1/plans/{saved['plan_id']}"
    assert api.get(path).status_code == 200
    assert api.post(path + "/tasks/property/cards").status_code == 422


@pytest.mark.parametrize("mode", ["patch", "plan"])
@pytest.mark.parametrize("change", ["basis", "position", "charge", "spin", "rest_options"])
def test_optimization_setting_change_invalidates_all_its_consumers_only(api, mode, change):
    body = _result_workflow()
    saved = api.post("/v1/plans", json=body).json()
    path = f"/v1/plans/{saved['plan_id']}"
    old_card = api.post(path + "/tasks/anion_energy/cards").json()
    update = {"task_id": "opt_anion"}
    if change == "basis":
        update["decision"] = {"basis": "def2-TZVP"}
    elif change == "rest_options":
        update["rest_options"] = {"ctrl": {"num_threads": 2}}
    else:
        value = {"position": "H 0 0 0\nH 0 0 0.8", "charge": -1, "spin": 2}[change]
        update["inputs"] = {change: value}
    # Even fresh-looking coordinates in the same edit cannot bypass invalidation.
    result_update = {
        "task_id": "anion_energy",
        "inputs": {"position": "H 0 0 0\nH 0 0 1.5", "position_unit": "bohr"},
    }
    if mode == "patch":
        revision = {"patch": {"tasks": [update, result_update]}}
    else:
        body = deepcopy(saved["plan"])
        for task_update in (update, result_update):
            target = next(
                task for task in body["tasks"] if task["task_id"] == task_update["task_id"]
            )
            for key, value in task_update.items():
                if key in {"inputs", "decision"}:
                    target[key].update(value)
                elif key != "task_id":
                    target[key] = value
        revision = {"plan": body}
    response = api.put(
        path, json={"expected_version": 1, "change_reason": "new optimization settings", **revision}
    )
    assert response.status_code == 200, response.text
    revised = response.json()
    by_id = {task["task_id"]: task for task in revised["plan"]["tasks"]}
    for task_id in ("anion_energy", "vertical_energy", "anion_frequency"):
        inputs = by_id[task_id]["inputs"]
        assert inputs["position"] is None and inputs["position_unit"] is None
        assert inputs["position_from_task"] == "opt_anion"
        assert inputs["charge"] == 0 and inputs["spin"] == 1
        assert api.post(path + f"/tasks/{task_id}/cards").status_code == 422
    assert by_id["neutral_energy"] == saved["plan"]["tasks"][3]
    assert by_id["neutral_frequency"] == saved["plan"]["tasks"][6]
    assert api.get(old_card["download_path"]).text == old_card["content"]
    assert (
        api.get(path + f"/cards/{old_card['card_id']}").json()["is_applicable_to_current_plan"]
        is False
    )
    # A later, separate result update is accepted.
    supplied = api.put(
        path,
        json={
            "expected_version": 2,
            "change_reason": "actual result",
            "patch": {"tasks": [result_update]},
        },
    )
    assert supplied.status_code == 200
    assert api.post(path + "/tasks/anion_energy/cards").status_code == 201


@pytest.mark.parametrize("mode", ["patch", "plan"])
def test_replacing_shared_result_clears_unmodified_consumers_and_preserves_explicit_updates(
    api, mode
):
    saved = api.post("/v1/plans", json=_result_workflow()).json()
    path = f"/v1/plans/{saved['plan_id']}"
    updates = [
        {"task_id": task_id, "inputs": {"position": "H 0 0 0\nH 0 0 1.5", "position_unit": "bohr"}}
        for task_id in ("anion_energy", "vertical_energy")
    ]
    if mode == "patch":
        revision = {"patch": {"tasks": updates}}
    else:
        body = deepcopy(saved["plan"])
        for task in body["tasks"]:
            if task["task_id"] in {"anion_energy", "vertical_energy"}:
                task["inputs"].update(updates[0]["inputs"])
        revision = {"plan": body}
    response = api.put(
        path, json={"expected_version": 1, "change_reason": "replace result", **revision}
    )
    assert response.status_code == 200, response.text
    tasks = {task["task_id"]: task for task in response.json()["plan"]["tasks"]}
    assert tasks["anion_energy"]["inputs"]["position_unit"] == "bohr"
    assert tasks["vertical_energy"]["inputs"]["position_unit"] == "bohr"
    assert tasks["anion_frequency"]["inputs"]["position"] is None
    assert tasks["neutral_frequency"] == saved["plan"]["tasks"][6]


def test_changing_between_two_optimization_sources_requires_separate_result(api):
    saved = api.post("/v1/plans", json=_result_workflow()).json()
    path = f"/v1/plans/{saved['plan_id']}"
    reply = api.put(
        path,
        json={
            "expected_version": 1,
            "change_reason": "switch source",
            "patch": {
                "tasks": [
                    {
                        "task_id": "vertical_energy",
                        "depends_on": ["opt_neutral"],
                        "inputs": {"position_from_task": "opt_neutral"},
                    }
                ]
            },
        },
    )
    assert reply.status_code == 200, reply.text
    task = reply.json()["plan"]["tasks"][4]
    assert task["inputs"]["position"] is None
    assert task["inputs"]["position_from_task"] == "opt_neutral"
    assert api.post(path + "/tasks/vertical_energy/cards").status_code == 422


@pytest.mark.parametrize("source", ["prior_result", "external_optimized"])
def test_relabeling_starting_structure_without_explicit_result_pair_stays_blocked(api, source):
    opt, consumer = _task("opt", "opt"), _task("sp", "energy")
    consumer["depends_on"] = ["opt"]
    saved = api.post(
        "/v1/plans",
        json={"question": "Optimize then energy", "goal": "other", "tasks": [opt, consumer]},
    ).json()
    path = f"/v1/plans/{saved['plan_id']}"
    response = api.put(
        path,
        json={
            "expected_version": 1,
            "change_reason": "relabel coordinates",
            "patch": {
                "tasks": [
                    {
                        "task_id": "sp",
                        "inputs": {"position_source": source, "position_from_task": "opt"},
                    }
                ]
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["plan"]["tasks"][1]["inputs"]["position"] is None
    assert response.json()["statuses"][1]["state"] == "needs_input"
    assert api.post(path + "/tasks/sp/cards").status_code == 422
    # Numeric equality is allowed when the user explicitly supplies the pair.
    response = api.put(
        path,
        json={
            "expected_version": 2,
            "change_reason": "actual result has same coordinates",
            "patch": {
                "tasks": [
                    {
                        "task_id": "sp",
                        "inputs": {
                            "position": consumer["inputs"]["position"],
                            "position_unit": "angstrom",
                        },
                    }
                ]
            },
        },
    )
    assert response.status_code == 200
    assert api.post(path + "/tasks/sp/cards").status_code == 201


def test_new_result_coordinates_do_not_inherit_previous_result_unit(api):
    saved = api.post("/v1/plans", json=_result_workflow()).json()
    path = f"/v1/plans/{saved['plan_id']}"
    response = api.put(
        path,
        json={
            "expected_version": 1,
            "change_reason": "new result unit not given",
            "patch": {
                "tasks": [{"task_id": "anion_energy", "inputs": {"position": "H 0 0 0\nH 0 0 1.5"}}]
            },
        },
    )
    assert response.status_code == 200
    task = response.json()["plan"]["tasks"][2]
    assert task["inputs"]["position"] == "H 0 0 0\nH 0 0 1.5"
    assert task["inputs"]["position_unit"] is None
    assert api.post(path + "/tasks/anion_energy/cards").status_code == 422


def test_descriptive_revision_reuses_same_card_without_new_database_row(api):
    saved = api.post("/v1/plans", json=_result_workflow()).json()
    path = f"/v1/plans/{saved['plan_id']}"
    old = api.post(path + "/tasks/anion_energy/cards").json()
    update = {
        "task_id": "opt_anion",
        "title": "Renamed optimization",
        "notes": "New description",
        "decision": {"rationale": "More explanation", "uncertainty": "No new scientific setting"},
    }
    reply = api.put(
        path,
        json={
            "expected_version": 1,
            "change_reason": "explanation only",
            "patch": {"tasks": [update]},
        },
    )
    assert reply.status_code == 200
    assert reply.json()["plan"]["tasks"][2] == saved["plan"]["tasks"][2]
    assert reply.json()["statuses"][2]["state"] == "card_ready"
    card = api.post(path + "/tasks/anion_energy/cards").json()
    assert card["card_id"] == old["card_id"]
    assert card["version"] == 1
    assert card["is_current_plan_version"] is False
    assert card["is_applicable_to_current_plan"] is True
    with sqlite3.connect(get_settings().workflow_db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 1
    assert api.get(path + "?version=1").json()["plan"] == saved["plan"]


@pytest.mark.parametrize("scientific_change", [False, True])
def test_historical_view_card_flags_always_describe_actual_latest_plan(api, scientific_change):
    saved = api.post(
        "/v1/plans",
        json={"question": "Single point", "goal": "other", "tasks": [_task("H2", "energy")]},
    ).json()
    path = f"/v1/plans/{saved['plan_id']}"
    original = api.post(path + "/tasks/H2/cards").json()
    update = (
        {"inputs": {"position": "H 0 0 0\nH 0 0 0.8", "position_unit": "angstrom"}}
        if scientific_change
        else {"notes": "Description changed"}
    )
    revision = api.put(
        path,
        json={
            "expected_version": 1,
            "change_reason": "revise",
            "patch": {"tasks": [{"task_id": "H2", **update}]},
        },
    )
    assert revision.status_code == 200
    historical = api.get(path + "?version=1").json()
    assert historical["version"] == 1
    assert historical["statuses"][0]["state"] == "card_ready"
    card = historical["cards"][0]
    assert card["card_id"] == original["card_id"]
    assert card["is_current_plan_version"] is False
    assert card["is_applicable_to_current_plan"] is (not scientific_change)
    assert api.get(original["download_path"]).text == original["content"]


def test_optimization_result_invalidation_reaches_descendants_independent_of_task_order(api):
    first, second, energy = _task("first", "opt"), _task("second", "opt"), _task("energy", "energy")
    for task, source in ((second, "first"), (energy, "second")):
        task["depends_on"] = [source]
        task["inputs"].update(position_source="prior_result", position_from_task=source)
    saved = api.post(
        "/v1/plans",
        json={"question": "Refine then energy", "goal": "other", "tasks": [energy, second, first]},
    ).json()
    path = f"/v1/plans/{saved['plan_id']}"
    revised = api.put(
        path,
        json={
            "expected_version": 1,
            "change_reason": "change first optimization",
            "patch": {"tasks": [{"task_id": "first", "decision": {"basis": "def2-TZVP"}}]},
        },
    )
    assert revised.status_code == 200
    assert revised.json()["plan"]["tasks"][0]["inputs"]["position"] is None
    assert revised.json()["plan"]["tasks"][1]["inputs"]["position"] is None
    assert api.post(path + "/tasks/energy/cards").status_code == 422


@pytest.mark.parametrize("mode", ["patch", "plan"])
def test_invalid_source_revision_is_atomic(api, mode):
    saved = api.post("/v1/plans", json=_result_workflow()).json()
    path = f"/v1/plans/{saved['plan_id']}"
    if mode == "patch":
        revision = {
            "patch": {
                "tasks": [
                    {"task_id": "anion_energy", "inputs": {"position_from_task": "opt_neutral"}}
                ]
            }
        }
    else:
        body = deepcopy(saved["plan"])
        body["tasks"][2]["inputs"]["position_from_task"] = "opt_neutral"
        revision = {"plan": body}
    response = api.put(
        path, json={"expected_version": 1, "change_reason": "wrong source dependency", **revision}
    )
    assert response.status_code == 422
    reopened = api.get(path).json()
    assert reopened["version"] == 1
    assert reopened["plan"] == saved["plan"]


def test_partial_revision_can_add_and_remove_tasks_with_graph_validation(api):
    saved = api.post(
        "/v1/plans",
        json={"question": "H2 energy", "goal": "other", "tasks": [_task("H2", "energy")]},
    ).json()
    path = f"/v1/plans/{saved['plan_id']}"
    analysis = {
        "task_id": "result",
        "title": "Energy analysis",
        "purpose": "Compare",
        "kind": "analysis",
        "depends_on": ["H2"],
        "analysis_formula": "E(H2)",
    }
    added = api.put(
        path,
        json={
            "expected_version": 1,
            "change_reason": "Add analysis",
            "patch": {"add_tasks": [analysis]},
        },
    )
    assert added.status_code == 200, added.text
    invalid = api.put(
        path,
        json={
            "expected_version": 2,
            "change_reason": "Break graph",
            "patch": {"remove_task_ids": ["H2"]},
        },
    )
    assert invalid.status_code == 422
    assert api.get(path).json()["version"] == 2
    removed = api.put(
        path,
        json={
            "expected_version": 2,
            "change_reason": "Remove analysis",
            "patch": {"remove_task_ids": ["result"]},
        },
    )
    assert removed.status_code == 200
    assert [t["task_id"] for t in removed.json()["plan"]["tasks"]] == ["H2"]


@pytest.mark.parametrize(
    "patch",
    [
        {},
        {"tasks": [{"task_id": "missing", "notes": "new"}]},
        {"tasks": [{"task_id": "H2", "notes": "a"}, {"task_id": "H2", "notes": "b"}]},
        {"tasks": [{"task_id": "H2", "inputs": {"position_unit": "nanometer"}}]},
        {"tasks": [{"task_id": "H2", "decision": {"source": "evidence", "supporting": []}}]},
        {"tasks": [{"task_id": "H2", "title": None}]},
        {"tasks": [{"task_id": "H2", "inputs": {"spin": 0}}]},
        {"tasks": [{"task_id": "H2", "depends_on": ["H2"]}]},
        {"tasks": [{"task_id": "H2", "question_display": "invented"}]},
        {"tasks": [{"task_id": "H2", "notes": "changed"}], "remove_task_ids": ["H2"]},
        {"add_tasks": [_task("H2", "energy")]},
    ],
)
def test_invalid_partial_revision_is_atomic(api, patch):
    saved = api.post(
        "/v1/plans",
        json={"question": "H2 energy", "goal": "other", "tasks": [_task("H2", "energy")]},
    ).json()
    path = f"/v1/plans/{saved['plan_id']}"
    reply = api.put(
        path, json={"expected_version": 1, "change_reason": "Invalid edit", "patch": patch}
    )
    assert reply.status_code == 422, reply.text
    assert api.get(path).json() == saved


def test_revision_requires_exactly_one_mode_and_rechecks_a_new_decision(api):
    draft = {
        "question": "No decision yet",
        "goal": "other",
        "tasks": [_task("H2", "energy", decision=False)],
    }
    saved = api.post("/v1/plans", json=draft).json()
    path = f"/v1/plans/{saved['plan_id']}"
    base = {"expected_version": 1, "change_reason": "Choose method"}
    assert api.put(path, json=base).status_code == 422
    assert (
        api.put(path, json={**base, "plan": draft, "patch": {"question": "new"}}).status_code == 422
    )
    incomplete = {"tasks": [{"task_id": "H2", "decision": {"basis": "def2-TZVP"}}]}
    assert api.put(path, json={**base, "patch": incomplete}).status_code == 422
    decision = _task("H2", "energy")["decision"]
    revised = api.put(
        path, json={**base, "patch": {"tasks": [{"task_id": "H2", "decision": decision}]}}
    )
    assert revised.status_code == 200
    assert revised.json()["statuses"][0]["state"] == "ready_for_card"


def test_large_workflow_revision_changes_only_selected_tasks(api):
    opt = _task("opt", "opt")
    steps = []
    for number in range(80):
        task = _task(f"sp_{number}", "energy")
        task["depends_on"] = ["opt"]
        task["inputs"].update(
            position=None,
            position_unit=None,
            position_source="prior_result",
            position_from_task="opt",
        )
        task["notes"] = "Preserve the purpose and uncertainty of this comparison. " * 15
        steps.append(task)
    draft = {
        "question": "Compare multiple final energy settings after optimization",
        "goal": "optimization_single_point",
        "tasks": [opt, *steps],
    }
    saved = api.post("/v1/plans", json=draft).json()
    path = f"/v1/plans/{saved['plan_id']}"
    revision = {
        "expected_version": 1,
        "change_reason": "Confirmed output and basis",
        "patch": {
            "tasks": [
                {
                    "task_id": "sp_37",
                    "decision": {"basis": "def2-TZVP"},
                    "inputs": {"position": "H 0 0 0\nH 0 0 1.4", "position_unit": "bohr"},
                }
            ]
        },
    }
    # The model need not retransmit the surrounding 80 tasks and notes.
    assert len(json.dumps(revision)) < len(json.dumps(saved["plan"])) / 100
    reply = api.put(path, json=revision)
    assert reply.status_code == 200, reply.text
    after = reply.json()
    assert len(after["plan"]["tasks"]) == 81
    for before_task, after_task in zip(saved["plan"]["tasks"], after["plan"]["tasks"], strict=True):
        if before_task["task_id"] != "sp_37":
            assert after_task == before_task
    assert after["statuses"][38]["state"] == "ready_for_card"
    assert all(status["state"] == "needs_input" for status in after["statuses"][1:38])
    assert api.post(path + "/tasks/sp_37/cards").json()["position_unit"] == "bohr"
    assert api.get(path + "?version=1").json()["plan"] == saved["plan"]


def test_partial_revision_replaces_lists_options_and_clears_a_nullable_decision(api):
    task = _task("H2", "energy")
    task["candidates"] = [{"xc": "PBE0", "rationale": "Alternative"}]
    task["rest_options"] = {"ctrl": {"print_level": 2, "num_threads": 8}}
    saved = api.post(
        "/v1/plans",
        json={
            "question": "H2 energy",
            "goal": "other",
            "tasks": [task],
            "assumptions": ["Original assumption"],
        },
    ).json()
    path = f"/v1/plans/{saved['plan_id']}"
    reply = api.put(
        path,
        json={
            "expected_version": 1,
            "change_reason": "Withdraw decision",
            "patch": {
                "assumptions": [],
                "tasks": [
                    {
                        "task_id": "H2",
                        "candidates": [],
                        "decision": None,
                        "rest_options": {"ctrl": {"num_threads": 4}},
                    }
                ],
            },
        },
    )
    assert reply.status_code == 200, reply.text
    draft = reply.json()["plan"]
    assert draft["assumptions"] == []
    assert draft["tasks"][0]["candidates"] == []
    assert draft["tasks"][0]["rest_options"] == {"ctrl": {"num_threads": 4}}
    assert draft["tasks"][0]["inputs"] == saved["plan"]["tasks"][0]["inputs"]
    assert reply.json()["statuses"][0]["state"] == "needs_decision"
    assert api.post(path + "/tasks/H2/cards").status_code == 422


def test_unintegrated_method_is_saved_without_claiming_rest_lacks_it(api: TestClient) -> None:
    task = _task("H2", "energy")
    task["candidates"] = [{"xc": "wB97X-D", "rationale": "Compare a range-separated candidate"}]
    task["decision"]["xc"] = "wB97X-D"
    created = api.post(
        "/v1/plans", json={"question": "Compare methods", "goal": "other", "tasks": [task]}
    )
    assert created.status_code == 201
    plan = created.json()
    assert plan["plan"]["tasks"][0]["candidates"][0]["xc"] == "wB97X-D"
    status = plan["statuses"][0]
    assert status["state"] == "unsupported"
    assert "AIFS REST card catalog" in status["blockers"][0]
    assert api.post(f"/v1/plans/{plan['plan_id']}/tasks/H2/cards").status_code == 422


def test_functional_selection_waits_for_a_separate_basis_decision(api: TestClient) -> None:
    task = _task("H2", "energy")
    task["decision"]["basis"] = None
    draft = {"question": "PBE selected, basis not yet chosen", "goal": "other", "tasks": [task]}
    created = api.post("/v1/plans", json=draft).json()
    plan_id = created["plan_id"]
    assert created["statuses"][0]["state"] == "needs_decision"
    assert "basis decision" in created["statuses"][0]["blockers"][0]
    assert api.post(f"/v1/plans/{plan_id}/tasks/H2/cards").status_code == 422
    assert api.get(f"/v1/plans/{plan_id}").json()["cards"] == []

    task["decision"]["basis"] = "def2-TZVPP"
    revised = api.put(
        f"/v1/plans/{plan_id}",
        json={"expected_version": 1, "change_reason": "User selected basis", "plan": draft},
    ).json()
    assert revised["statuses"][0]["state"] == "ready_for_card"
    card = api.post(f"/v1/plans/{plan_id}/tasks/H2/cards").json()
    assert card["validation"]["valid"]
    assert card["request"]["xc"] == "PBE"
    assert card["request"]["basis"] == "def2-TZVPP"
    assert api.get(card["download_path"]).text == card["content"]
    historic = api.get(f"/v1/plans/{plan_id}?version=1").json()
    assert historic["plan"]["tasks"][0]["decision"]["basis"] is None


def test_units_required_and_persist_across_revisions_and_downloads(api: TestClient) -> None:
    task = _task("H2", "energy")
    task["inputs"].pop("position_unit")
    draft = {"question": "H2 energy", "goal": "other", "tasks": [task]}
    created = api.post("/v1/plans", json=draft).json()
    plan_id = created["plan_id"]
    assert created["statuses"][0]["state"] == "needs_input"
    assert any("coordinate unit" in item for item in created["statuses"][0]["blockers"])
    assert api.post(f"/v1/plans/{plan_id}/tasks/H2/cards").status_code == 422
    for version, unit in [(1, "bohr"), (2, "angstrom")]:
        task["inputs"]["position_unit"] = unit
        revised = api.put(
            f"/v1/plans/{plan_id}",
            json={
                "expected_version": version,
                "change_reason": "User confirmed coordinate unit",
                "plan": draft,
            },
        )
        assert revised.status_code == 200
        card = api.post(f"/v1/plans/{plan_id}/tasks/H2/cards").json()
        assert card["validation"]["valid"]
        assert card["request"]["position_unit"] == unit
        assert card["render"]["effective_settings"]["position_unit"] == unit
        assert tomllib.loads(card["content"])["geom"]["unit"] == unit
        assert api.get(card["download_path"]).content.decode() == card["content"]
        if unit == "bohr":
            old = card
    historic = api.get(f"/v1/plans/{plan_id}/cards/{old['card_id']}").json()
    assert not historic["is_current_plan_version"]
    assert historic["content"] == old["content"]
    assert (
        api.get(f"/v1/plans/{plan_id}?version=1").json()["plan"]["tasks"][0]["inputs"][
            "position_unit"
        ]
        is None
    )
    assert (
        api.get(f"/v1/plans/{plan_id}").json()["plan"]["tasks"][0]["inputs"]["position_unit"]
        == "angstrom"
    )


def test_skill_example_matches_backend_and_waits_for_result_unit(api: TestClient) -> None:
    skill = Path(__file__).resolve().parents[2] / "skills/aifs-molecular-planning/SKILL.md"
    text = skill.read_text().split("## Plan contract example", 1)[1]
    example = json.loads(re.search(r"```json\n(.*?)\n```", text, re.S)[1])
    created = api.post("/v1/plans", json=example)
    assert created.status_code == 201
    plan_id = created.json()["plan_id"]
    assert [status["state"] for status in created.json()["statuses"]] == [
        "ready_for_card",
        "needs_input",
    ]
    assert api.post(f"/v1/plans/{plan_id}/tasks/opt_H2/cards").status_code == 201
    assert api.post(f"/v1/plans/{plan_id}/tasks/sp_H2/cards").status_code == 422
    example["tasks"][1]["inputs"]["position"] = "H 0 0 0\nH 0 0 1.4"
    changed = api.put(
        f"/v1/plans/{plan_id}",
        json={
            "expected_version": 1,
            "change_reason": "Result coordinates, unit still unknown",
            "plan": example,
        },
    )
    assert changed.status_code == 200
    assert changed.json()["statuses"][1]["state"] == "needs_input"
    assert api.post(f"/v1/plans/{plan_id}/tasks/sp_H2/cards").status_code == 422
    example["tasks"][1]["inputs"]["position_unit"] = "bohr"
    assert (
        api.put(
            f"/v1/plans/{plan_id}",
            json={
                "expected_version": 2,
                "change_reason": "Result unit confirmed",
                "plan": example,
            },
        ).status_code
        == 200
    )
    card = api.post(f"/v1/plans/{plan_id}/tasks/sp_H2/cards").json()
    assert card["validation"]["valid"]
    assert tomllib.loads(card["content"])["geom"]["unit"] == "bohr"


@pytest.mark.parametrize(
    "system,initial,result",
    [
        (
            "Al3",
            "Al 0 0 0\nAl 2.6 0 0\nAl 1.3 2.2 0",
            "Al 0 0 0\nAl 2.58 0 0\nAl 1.29 2.23 0",
        ),
        (
            "CH3",
            "C 0 0 0\nH 1.1 0 0\nH -0.55 0.95 0\nH -0.55 -0.95 0",
            "C 0 0 0\nH 1.08 0 0\nH -0.54 0.94 0\nH -0.54 -0.94 0",
        ),
    ],
)
def test_experimental_ade_frequency_tasks_wait_and_keep_separate_energy_protocol(
    api: TestClient,
    system: str,
    initial: str,
    result: str,
) -> None:
    tasks = []
    for species, charge, spin in [("anion", -1, 1), ("neutral", 0, 2)]:
        opt = _task(f"{species}_opt", "opt")
        opt["system_name"] = f"{system}_{species}"
        opt["inputs"].update(position=initial, charge=charge, spin=spin)
        opt["decision"].update(xc="PBE0", basis="def2-TZVP")
        tasks.append(opt)
        for suffix in ("sp", "freq"):
            task = deepcopy(opt)
            task.update(
                task_id=f"{species}_{suffix}",
                title=f"{species} {'frequencies and ZPE' if suffix == 'freq' else 'energy'}",
                purpose="Obtain ZPE and check minimum" if suffix == "freq" else "Final energy",
                job_type="energy",
                depends_on=[opt["task_id"]],
            )
            task["inputs"].update(
                position=None,
                position_unit=None,
                position_source="prior_result",
                position_from_task=opt["task_id"],
            )
            if suffix == "sp":
                task["decision"].update(xc="wB97M-V", xc_parser="parse_xc", basis="aug-cc-pVTZ")
            else:
                task["rest_options"] = {
                    "ctrl": {"analdrv_tasks": ["hessian"]},
                    "thermo": {"sclzpe": 1.0},
                }
            tasks.append(task)
    vertical = deepcopy(tasks[4])
    vertical.update(task_id="neutral_at_anion_sp", depends_on=["anion_opt"])
    vertical["inputs"]["position_from_task"] = "anion_opt"
    tasks.append(vertical)
    analyses = [
        ("ade_electronic", ["neutral_sp", "anion_sp"], "E(neutral_sp)-E(anion_sp)"),
        (
            "ade_0",
            ["neutral_sp", "anion_sp", "neutral_freq", "anion_freq"],
            "E(neutral_sp)-E(anion_sp)+ZPE(neutral_freq)-ZPE(anion_freq)",
        ),
        (
            "vde_electronic",
            ["neutral_at_anion_sp", "anion_sp"],
            "E(neutral_at_anion_sp)-E(anion_sp)",
        ),
    ]
    for task_id, dependencies, formula in analyses:
        tasks.append(
            {
                "task_id": task_id,
                "title": task_id,
                "purpose": "Compare detachment energies with experiment",
                "kind": "analysis",
                "depends_on": dependencies,
                "analysis_formula": formula,
                "notes": "Await external energies/ZPE, units and minimum checks; not evaluated.",
            }
        )
    draft = {
        "question": f"{system} ADE including ZPE and electronic VDE",
        "goal": "other",
        "tasks": tasks,
    }
    created = api.post("/v1/plans", json=draft)
    assert created.status_code == 201
    plan_id = created.json()["plan_id"]
    statuses = {item["task_id"]: item for item in created.json()["statuses"]}
    for task_id in ("anion_freq", "neutral_freq"):
        assert statuses[task_id]["state"] == "needs_input"
        assert api.post(f"/v1/plans/{plan_id}/tasks/{task_id}/cards").status_code == 422
    assert statuses["ade_0"]["state"] == "analysis_only"
    assert api.post(f"/v1/plans/{plan_id}/tasks/ade_0/cards").status_code == 422

    # A supplied result still lacks its own unit; no premature frequency card.
    for task in tasks:
        if task.get("inputs", {}).get("position_source") == "prior_result":
            task["inputs"]["position"] = result
    response = api.put(
        f"/v1/plans/{plan_id}",
        json={"expected_version": 1, "change_reason": "Result coordinates only", "plan": draft},
    )
    assert response.status_code == 200
    assert api.post(f"/v1/plans/{plan_id}/tasks/neutral_freq/cards").status_code == 422
    for task in tasks:
        if task.get("inputs", {}).get("position_source") == "prior_result":
            task["inputs"]["position_unit"] = "angstrom"
    assert (
        api.put(
            f"/v1/plans/{plan_id}",
            json={"expected_version": 2, "change_reason": "Result units confirmed", "plan": draft},
        ).status_code
        == 200
    )
    for species, polarized in [("anion", False), ("neutral", True)]:
        card_response = api.post(f"/v1/plans/{plan_id}/tasks/{species}_freq/cards")
        assert card_response.status_code == 201
        card = card_response.json()
        assert card["validation"]["valid"]
        parsed = tomllib.loads(card["content"])
        assert parsed["ctrl"]["xc"] == "PBE0"
        assert parsed["ctrl"]["analdrv_tasks"] == ["hessian"]
        assert parsed["ctrl"]["spin_polarization"] is polarized
        assert parsed["thermo"]["sclzpe"] == 1.0
        assert "atm_list" not in parsed.get("analdrv", {})
        assert api.get(card["download_path"]).text == card["content"]
        energy = api.post(f"/v1/plans/{plan_id}/tasks/{species}_sp/cards").json()
        assert tomllib.loads(energy["content"])["ctrl"]["xc"] == "wB97M-V"
    saved = api.get(f"/v1/plans/{plan_id}").json()["plan"]["tasks"]
    saved_analysis = {task["task_id"]: task for task in saved if task["kind"] == "analysis"}
    for task_id, dependencies, formula in analyses:
        assert saved_analysis[task_id]["depends_on"] == dependencies
        assert saved_analysis[task_id]["analysis_formula"] == formula
    historical = api.get(f"/v1/plans/{plan_id}?version=1").json()
    assert historical["plan"]["tasks"][2]["inputs"]["position"] is None


@pytest.mark.parametrize(
    "geometry_xc,energy_xc", [("PBE", "XYG7"), ("wB97X", "XYG3"), ("XYG3", "XYG7")]
)
def test_task_methods_are_independent_across_result_revision_and_history(
    api: TestClient, geometry_xc: str, energy_xc: str
) -> None:
    optimization = _task("opt_H2", "opt")
    optimization["decision"].update(xc=geometry_xc, basis="def2-TZVP")
    energy = _task("sp_H2", "energy")
    energy["depends_on"] = ["opt_H2"]
    energy["decision"].update(xc=energy_xc, basis="def2-TZVPP")
    energy["inputs"].update(
        position=None,
        position_unit=None,
        position_source="prior_result",
        position_from_task="opt_H2",
    )
    draft = {
        "question": "Use different confirmed methods for geometry and final energy",
        "goal": "optimization_single_point",
        "tasks": [optimization, energy],
    }
    created = api.post("/v1/plans", json=draft).json()
    plan_id = created["plan_id"]
    assert [s["state"] for s in created["statuses"]] == ["ready_for_card", "needs_input"]
    old_card = api.post(f"/v1/plans/{plan_id}/tasks/opt_H2/cards").json()
    assert old_card["validation"]["valid"]
    assert tomllib.loads(old_card["content"])["ctrl"]["xc"] == geometry_xc
    assert api.post(f"/v1/plans/{plan_id}/tasks/sp_H2/cards").status_code == 422
    energy["inputs"].update(position="H 0 0 0\nH 0 0 0.73", position_unit="angstrom")
    revision = api.put(
        f"/v1/plans/{plan_id}",
        json={
            "expected_version": 1,
            "change_reason": "Confirmed optimized coordinates",
            "plan": draft,
        },
    )
    assert revision.status_code == 200
    card = api.post(f"/v1/plans/{plan_id}/tasks/sp_H2/cards").json()
    assert card["validation"]["valid"]
    parsed = tomllib.loads(card["content"])
    assert parsed["ctrl"]["xc"] == energy_xc
    assert parsed["ctrl"]["basis_path"].endswith("/def2-TZVPP")
    assert api.get(card["download_path"]).text == card["content"]
    reopened = TestClient(app).get(f"/v1/plans/{plan_id}").json()
    assert [t["decision"]["xc"] for t in reopened["plan"]["tasks"]] == [geometry_xc, energy_xc]
    historical = api.get(f"/v1/plans/{plan_id}/cards/{old_card['card_id']}").json()
    assert not historical["is_current_plan_version"]
    assert historical["content"] == old_card["content"]


def test_pre_unit_history_is_readable_and_never_silently_rewritten(api: TestClient) -> None:
    draft = {"question": "Historical H2", "goal": "other", "tasks": [_task("H2", "energy")]}
    plan_id = api.post("/v1/plans", json=draft).json()["plan_id"]
    card = api.post(f"/v1/plans/{plan_id}/tasks/H2/cards").json()
    old_content = card["content"].replace('unit = "angstrom"\n', "")
    digest = hashlib.sha256(old_content.encode()).hexdigest()
    # Simulate an existing pre-unit database; the application must not migrate
    # its original coordinate assumption into a newly confirmed unit.
    draft["tasks"][0]["inputs"].pop("position_unit")
    with sqlite3.connect(get_settings().workflow_db) as connection:
        connection.execute("UPDATE plan_versions SET snapshot_json = ?", (json.dumps(draft),))
        connection.execute(
            "UPDATE cards SET content = ?, sha256 = ? WHERE card_id = ?",
            (old_content, digest, card["card_id"]),
        )
    reopened = api.get(f"/v1/plans/{plan_id}/cards/{card['card_id']}").json()
    assert reopened["position_unit_status"] == "not_recorded"
    assert reopened["position_unit"] is None
    assert reopened["content"] == old_content
    assert reopened["sha256"] == digest
    assert api.get(reopened["download_path"]).content.decode() == old_content
    assert api.get(f"/v1/plans/{plan_id}").json()["statuses"][0]["state"] == "needs_input"


def test_reaction_plan_cards_survive_reopen_and_revision(api: TestClient) -> None:
    plan = _reaction()
    plan["tasks"][0]["inputs"]["charge"] = None
    plan["tasks"][0]["inputs"]["charge_source"] = None
    created = api.post("/v1/plans", json=plan)
    assert created.status_code == 201
    plan_id = created.json()["plan_id"]
    assert created.json()["statuses"][0]["state"] == "needs_input"
    blocked = api.post(f"/v1/plans/{plan_id}/tasks/A/cards")
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "task_not_ready"
    plan["tasks"][0]["inputs"]["charge"] = 0
    plan["tasks"][0]["inputs"]["charge_source"] = "user"
    revised = api.put(
        f"/v1/plans/{plan_id}",
        json={"expected_version": 1, "change_reason": "user confirmed charge", "plan": plan},
    )
    assert revised.status_code == 200
    assert revised.json()["version"] == 2
    assert revised.json()["statuses"][0]["state"] == "ready_for_card"
    card_response = api.post(f"/v1/plans/{plan_id}/tasks/A/cards")
    assert card_response.status_code == 201
    card = card_response.json()
    assert card["version"] == 2
    assert card["validation"]["valid"] is True
    assert card["catalog_source_date"] == "2026-10-04"
    assert card["render"]["effective_settings"]["basis"] == "def2-TZVPP"
    assert card["filename"].endswith(".in")
    assert api.get(card["download_path"]).content.decode() == card["content"]
    assert api.get(f"/v1/plans/{plan_id}").json()["statuses"][0]["state"] == "card_ready"
    assert api.get("/v1/plans").json()["plans"][0]["plan_id"] == plan_id
    assert api.get(f"/v1/plans/{plan_id}?version=1").json()["cards"] == []
    assert (
        api.put(
            f"/v1/plans/{plan_id}",
            json={
                "expected_version": 1,
                "change_reason": "stale",
                "plan": plan,
            },
        ).status_code
        == 409
    )
    plan["tasks"][0]["decision"]["xc"] = "B3LYP"
    assert (
        api.put(
            f"/v1/plans/{plan_id}",
            json={
                "expected_version": 2,
                "change_reason": "method changed",
                "plan": plan,
            },
        ).status_code
        == 200
    )
    assert api.get(f"/v1/plans/{plan_id}").json()["statuses"][0]["state"] == "ready_for_card"
    historical_card = api.get(f"/v1/plans/{plan_id}/cards/{card['card_id']}").json()
    assert historical_card["version"] == 2
    assert historical_card["is_current_plan_version"] is False


def test_optimization_result_gate_and_supported_jobs(api: TestClient) -> None:
    opt = _task("opt", "opt")
    energy = _task("sp", "energy")
    energy["depends_on"] = ["opt"]
    plan = {
        "question": "Optimize then calculate energy",
        "goal": "optimization_single_point",
        "tasks": [opt, energy],
    }
    created = api.post("/v1/plans", json=plan)
    assert created.status_code == 201
    plan_id = created.json()["plan_id"]
    assert created.json()["statuses"][1]["state"] == "needs_input"
    assert "optimized coordinates" in str(created.json()["statuses"][1]["blockers"])
    assert api.post(f"/v1/plans/{plan_id}/tasks/opt/cards").status_code == 201
    assert api.post(f"/v1/plans/{plan_id}/tasks/sp/cards").status_code == 422
    plan["tasks"][1]["inputs"]["position_source"] = "prior_result"
    plan["tasks"][1]["inputs"]["position_from_task"] = "opt"
    updated = api.put(
        f"/v1/plans/{plan_id}",
        json={
            "expected_version": 1,
            "change_reason": "user supplied optimization output coordinates",
            "plan": plan,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["statuses"][1]["state"] == "ready_for_card"
    assert api.post(f"/v1/plans/{plan_id}/tasks/sp/cards").status_code == 201
    for goal, job_type in (("force", "force"), ("dipole", "numerical dipole")):
        body = {"question": goal, "goal": goal, "tasks": [_task(goal, job_type)]}
        response = api.post("/v1/plans", json=body)
        assert response.status_code == 201
        assert (
            api.post(f"/v1/plans/{response.json()['plan_id']}/tasks/{goal}/cards").status_code
            == 201
        )


def test_unsupported_and_invalid_graph_never_make_cards(api: TestClient) -> None:
    plan = _reaction()
    plan["tasks"].append(
        {
            "task_id": "freq",
            "title": "Frequency",
            "purpose": "Thermal correction",
            "kind": "unsupported",
            "job_type": "frequency",
            "depends_on": ["C"],
        }
    )
    created = api.post("/v1/plans", json=plan)
    assert created.status_code == 201
    assert created.json()["statuses"][-1]["state"] == "unsupported"
    assert api.post(f"/v1/plans/{created.json()['plan_id']}/tasks/freq/cards").status_code == 422
    cycle = deepcopy(plan)
    cycle["tasks"][0]["depends_on"] = ["delta_e"]
    assert api.post("/v1/plans", json=cycle).status_code == 422
    fake = deepcopy(plan)
    fake["tasks"][0]["status"] = "card_ready"
    assert api.post("/v1/plans", json=fake).status_code == 422


def test_binding_energy_records_candidate_comparison_and_combination(api: TestClient) -> None:
    plan = {
        "question": "Electronic binding energy of A and B",
        "goal": "binding_energy",
        "assumptions": ["No BSSE correction is included in this initial electronic-energy plan"],
        "tasks": [
            _task("complex", "energy"),
            _task("fragment_a", "energy"),
            _task("fragment_b", "energy"),
            {
                "task_id": "binding_delta",
                "title": "Combine energies",
                "purpose": "Compute electronic binding energy",
                "kind": "analysis",
                "depends_on": ["complex", "fragment_a", "fragment_b"],
                "analysis_formula": "E(complex)-E(fragment_a)-E(fragment_b)",
            },
        ],
    }
    plan["tasks"][0]["candidates"] = [
        {"xc": "PBE", "rationale": "User candidate; evidence not yet established"},
        {"xc": "B3LYP", "rationale": "Alternative to compare"},
    ]
    response = api.post("/v1/plans", json=plan)
    assert response.status_code == 201
    assert len(response.json()["plan"]["tasks"][0]["candidates"]) == 2
    assert response.json()["statuses"][3]["state"] == "analysis_only"


def test_web_source_is_distinct_and_unknown_local_record_is_rejected(api: TestClient) -> None:
    body = {"question": "Find force", "goal": "force", "tasks": [_task("force", "force")]}
    decision = body["tasks"][0]["decision"]
    decision["source"] = "evidence"
    decision["supporting"] = [
        {
            "source": "web",
            "claim_type": "method_used",
            "url": "https://example.org/paper",
            "title": "A paper",
            "note": "This article discusses the method; comparison has not been verified",
        }
    ]
    created = api.post("/v1/plans", json=body)
    assert created.status_code == 201
    saved_web = created.json()["plan"]["tasks"][0]["decision"]["supporting"][0]
    assert saved_web["source"] == "web"
    assert saved_web["url"] == "https://example.org/paper"
    assert saved_web["title"] == "A paper"
    assert saved_web["claim_type"] == "method_used"
    assert saved_web["note"].startswith("未整理网页来源：")
    assert "泛函优选未核验" in created.json()["plan"]["tasks"][0]["decision"]["uncertainty"]
    assert "只说明方法被使用" in created.json()["plan"]["tasks"][0]["decision"]["uncertainty"]
    decision["supporting"][0]["url"] = "https://"
    assert api.post("/v1/plans", json=body).status_code == 422
    decision["supporting"] = [{"source": "local", "record_id": "absent", "note": "missing"}]
    rejected = api.post("/v1/plans", json=body)
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "unknown_evidence"


def test_web_comparison_opposition_and_missing_evidence_decisions(api: TestClient) -> None:
    body = {
        "question": "Compare force methods",
        "goal": "force",
        "tasks": [_task("force", "force")],
    }
    task = body["tasks"][0]
    task["decision"] = {
        "xc": "PBE",
        "basis": "def2-TZVP",
        "source": "provisional",
        "rationale": "No relevant source was found yet",
        "uncertainty": "Web search found no relevant comparison",
    }
    empty = api.post("/v1/plans", json=body)
    assert empty.status_code == 201
    plan_id = empty.json()["plan_id"]
    assert empty.json()["statuses"][0]["state"] == "needs_decision"
    assert api.post(f"/v1/plans/{plan_id}/tasks/force/cards").status_code == 422

    task["candidates"] = [
        {
            "xc": "B3LYP",
            "rationale": "Alternative reported in a different protocol",
            "opposing": [
                {
                    "source": "web",
                    "claim_type": "method_used",
                    "url": "https://example.org/usage",
                    "title": "Usage report",
                    "note": "Uses B3LYP but does not compare it with PBE",
                }
            ],
        }
    ]
    task["decision"] = {
        "xc": "PBE",
        "basis": "def2-TZVP",
        "source": "evidence",
        "rationale": (
            "One comparison favors PBE for this test property; protocol transfer remains uncertain"
        ),
        "supporting": [
            {
                "source": "web",
                "claim_type": "comparative_benchmark",
                "url": "https://example.org/comparison",
                "title": "Comparison study",
                "note": "Reports a relevant PBE versus B3LYP comparison",
            }
        ],
        "opposing": [
            {
                "source": "web",
                "claim_type": "author_recommendation",
                "url": "https://example.org/counterpoint",
                "title": "Counterpoint study",
                "note": "Authors favor another method under a different protocol",
            }
        ],
        "uncertainty": "The sources use different protocols",
    }
    revised = api.put(
        f"/v1/plans/{plan_id}",
        json={"expected_version": 1, "change_reason": "recorded web comparison", "plan": body},
    )
    assert revised.status_code == 200
    saved = revised.json()["plan"]["tasks"][0]
    assert saved["decision"]["supporting"][0]["claim_type"] == "comparative_benchmark"
    assert saved["decision"]["opposing"][0]["claim_type"] == "author_recommendation"
    assert saved["candidates"][0]["opposing"][0]["claim_type"] == "method_used"
    assert "different protocols" in saved["decision"]["uncertainty"]
    assert "泛函优选未核验" in saved["decision"]["uncertainty"]
    historical = api.get(f"/v1/plans/{plan_id}?version=1").json()
    assert historical["statuses"][0]["state"] == "needs_decision"

    task["decision"] = {
        "xc": "PBE",
        "basis": "def2-TZVP",
        "source": "user",
        "rationale": "User chose PBE for a controlled run, not a literature recommendation",
    }
    user_choice = api.put(
        f"/v1/plans/{plan_id}",
        json={
            "expected_version": 2,
            "change_reason": "user explicitly selected method",
            "plan": body,
        },
    )
    assert user_choice.status_code == 200
    assert user_choice.json()["plan"]["tasks"][0]["decision"]["source"] == "user"
    assert user_choice.json()["statuses"][0]["state"] == "ready_for_card"
