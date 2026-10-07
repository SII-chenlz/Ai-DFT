"""Meaningful workflow scenarios across persistence, state gates and downloads."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from copy import deepcopy
from pathlib import Path

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
    example = json.loads(re.search(r"```json\n(.*?)\n```", skill.read_text(), re.S)[1])
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
    api: TestClient, system: str, initial: str, result: str,
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
                task["decision"].update(
                    xc="wB97M-V", xc_parser="parse_xc", basis="aug-cc-pVTZ"
                )
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
    assert api.put(
        f"/v1/plans/{plan_id}",
        json={"expected_version": 2, "change_reason": "Result units confirmed", "plan": draft},
    ).status_code == 200
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
