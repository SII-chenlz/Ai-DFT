"""GW/BSE input contracts, independently checked cards and existing dependencies.

The guide fixtures describe inputs, not REST executions or verified energies.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aifs.api import app
from aifs.config import get_settings
from aifs.rest import tomllib
from aifs.rest.validator import validate_rest_input

GUIDE_CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "gwbse-guide-inputs.json").read_text()
)


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFS_WORKFLOW_DB", str(tmp_path / "workflow.sqlite3"))
    monkeypatch.setenv("AIFS_EVIDENCE_DB", str(tmp_path / "evidence.sqlite3"))
    get_settings.cache_clear()
    return TestClient(app)


def payload(**qp):
    return {
        "system_name": "H2",
        "position": "H 0 0 0\nH 0 0 0.74",
        "position_unit": "angstrom",
        "charge": 0,
        "spin": 1,
        "xc": "PBE",
        "basis": "cc-pVDZ",
        "job_type": "energy",
        "rest_options": {
            "ctrl": {"eri_type": "ri_v", "auxbas_path": "def2-SV(P)-JKFIT"},
            "quasiparticle_methods": {"gw_or_bse": "gw", "gw_scheme": "extrapolated", **qp},
        },
    }


def bse_payload(**qp):
    return payload(gw_or_bse="bse", bse_spin="singlet", bse_tda=True, **qp)


@pytest.mark.parametrize("case", GUIDE_CASES, ids=[
    f"{p['system_name']}-{p['rest_options']['quasiparticle_methods']['bse_spin']}"
    for p in GUIDE_CASES
])
def test_guide_inputs_prepare_and_validate_without_creating_plans(api, case, tmp_path):
    response = api.post("/v1/rest-inputs/prepare", json=case)
    assert response.status_code == 200, response.text
    result = response.json()
    data = tomllib.loads(result["rest_input"])
    assert result["validation"]["valid"] is True
    assert validate_rest_input(result["rest_input"]).valid
    assert data["quasiparticle_methods"] == case["rest_options"]["quasiparticle_methods"]
    assert data["geom"]["position"].strip() == case["position"]
    # Triplet BSE keeps the same closed-shell ground state.
    assert data["ctrl"]["spin"] == 1 and data["ctrl"]["spin_polarization"] is False
    assert data["ctrl"]["eri_type"] == "ri_v"
    assert not (tmp_path / "workflow.sqlite3").exists()


@pytest.mark.parametrize("settings", [
    {"gw_scheme": "qp equation"},
    {"gw_scheme": "linearize"},
    {"scgw": "evgw", "evgw_rounds": 5},
    {"renormalized_singles": True, "w_rs": True},
    {"homo_lumo_gw_qp": True},
    {"gw_extrapolate_occ_threshold": 0.1, "gw_extrapolate_vir_threshold": 0.2},
    {"use_low_rank_contour": True, "nomega_chi_real": 6, "low_rank_tolerance": 1e-3},
])
def test_gw_variants_preserve_requested_options(api, settings):
    request = payload(**settings)
    response = api.post("/v1/rest-inputs/prepare", json=request)
    assert response.status_code == 200, response.text
    data = tomllib.loads(response.json()["rest_input"])
    for key, value in settings.items():
        assert data["quasiparticle_methods"][key] == value


@pytest.mark.parametrize("tda", [True, False])
@pytest.mark.parametrize("channel", ["singlet", "triplet", "both"])
def test_bse_channels_and_solvers_are_separate_from_scf_spin(api, tda, channel):
    request = payload(
        gw_or_bse="bse", bse_spin=channel, bse_tda=tda, bse_davidson_solver=True,
        davidson_target_excitations=5, davidson_maximum_subspace_size=50,
        davidson_restart_dimensions=10, davidson_converge_threshold=1e-8,
        bse_cutoff_energy=20.0, bse_auxbas_path="./basis/bse-lamb",
    )
    response = api.post("/v1/rest-inputs/prepare", json=request)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["validation"]["valid"] is True
    data = tomllib.loads(result["rest_input"])
    assert data["quasiparticle_methods"]["bse_tda"] is tda
    assert data["quasiparticle_methods"]["bse_spin"] == channel
    assert data["quasiparticle_methods"]["bse_auxbas_path"] == "./basis/bse-lamb"
    assert data["ctrl"]["spin"] == 1


@pytest.mark.parametrize("qp,bad_field", [
    ({"threshold": 0.1}, "gw_extrapolate_occ_threshold"),
    ({"gw_scheme": "full"}, "gw_scheme"),
    ({"gw_or_bse": "response_bse"}, "gw_or_bse"),
    ({"gw_scheme": "extrapolated", "scgw": "evgw"}, "evgw_rounds"),
    ({"scgw": "evgw", "evgw_rounds": 0}, "evgw_rounds"),
    ({"bse_tda": "true"}, "bse_tda"),
    ({"w_rs": True}, "renormalized_singles"),
    ({"gw_or_bse": "bse", "bse_spin": "none", "bse_tda": True}, "bse_spin"),
    ({"gw_or_bse": "bse", "bse_spin": "triplet"}, "bse_tda"),
    ({"gw_or_bse": "bse", "bse_spin": "unrestricted", "bse_tda": True}, "bse_spin"),
    ({"gw_or_bse": "bse", "bse_spin": "singlet", "bse_tda": True,
      "bse_davidson_solver": True, "davidson_target_excitations": 6,
      "davidson_maximum_subspace_size": 4}, "davidson_maximum_subspace_size"),
    ({"gw_or_bse": "bse", "bse_spin": "singlet", "bse_tda": True,
      "davidson_target_excitations": 5}, "bse_davidson_solver"),
    ({"gw_or_bse": "bse", "bse_spin": "singlet", "bse_tda": True,
      "homo_lumo_gw_qp": True}, "homo_lumo_gw_qp"),
])
def test_invalid_or_ineffective_options_block_formal_cards(api, qp, bad_field):
    response = api.post("/v1/rest-inputs/prepare", json=payload(**qp))
    assert response.status_code == 422, response.text
    assert bad_field in response.text
    assert "rest_input" not in response.json()


def test_missing_gw_selector_cannot_silently_generate_an_scf_only_card(api):
    request = payload()
    request["rest_options"]["quasiparticle_methods"] = {}
    response = api.post("/v1/rest-inputs/prepare", json=request)
    assert response.status_code == 422
    assert "gw_or_bse" in response.text


def test_pruned_ri_pairs_cannot_be_used_for_gw(api):
    request = payload()
    request["rest_options"]["ctrl.ri_jk"] = {"pair_screen_threshold": 1e-8}
    response = api.post("/v1/rest-inputs/prepare", json=request)
    assert response.status_code == 422, response.text
    assert "pruning" in response.text


def test_bse_reads_an_explicit_external_qp_file_without_claiming_it_exists(api):
    request = bse_payload(gw_scheme="parse from file", parse_qp_path="./run/qp_energies")
    response = api.post("/v1/rest-inputs/prepare", json=request)
    assert response.status_code == 200, response.text
    assert tomllib.loads(response.json()["rest_input"])["quasiparticle_methods"][
        "parse_qp_path"
    ] == "./run/qp_energies"
    request["rest_options"]["quasiparticle_methods"].pop("parse_qp_path")
    assert api.post("/v1/rest-inputs/prepare", json=request).status_code == 422


@pytest.mark.parametrize("field,value", [
    ("davidson_target_excitations", -1), ("davidson_target_excitations", True),
    ("nomega_chi_real", 0), ("low_rank_tolerance", 0),
    ("gw_extrapolate_occ_threshold", -0.1),
])
def test_qp_numeric_contract_rejects_invalid_counts_and_windows(api, field, value):
    response = api.post("/v1/rest-inputs/prepare", json=payload(**{field: value}))
    assert response.status_code == 422 and field in response.text


@pytest.mark.parametrize("job", ["opt", "force", "numerical dipole"])
def test_unreviewed_qp_derivatives_do_not_pass_as_an_energy_card(api, job):
    request = payload()
    request["job_type"] = job
    assert api.post("/v1/rest-inputs/prepare", json=request).status_code == 422


@pytest.mark.parametrize("eri_type", ["ri-v", "ri_v"])
def test_both_ri_spellings_work_and_analytic_integrals_do_not(api, eri_type):
    request = payload()
    request["rest_options"]["ctrl"]["eri_type"] = eri_type
    response = api.post("/v1/rest-inputs/prepare", json=request)
    assert response.status_code == 200, response.text
    request["rest_options"]["ctrl"]["eri_type"] = "analytic"
    response = api.post("/v1/rest-inputs/prepare", json=request)
    assert response.status_code == 422 and "RI" in response.text


def test_manual_card_is_checked_independently(api, valid_card):
    suffix = '\n[quasiparticle_methods]\ngw_or_bse="bse"\ngw_scheme="extrapolated"\n'
    invalid = validate_rest_input(valid_card + suffix)
    assert invalid.valid is False
    assert any("bse_spin" in issue.message for issue in invalid.errors)
    complete = suffix + 'bse_spin="triplet"\nbse_tda=false\n'
    assert validate_rest_input(valid_card + complete).valid


def test_unrestricted_bse_is_one_coupled_channel_not_a_triplet_switch(api):
    request = payload(gw_or_bse="bse", bse_spin="unrestricted", bse_tda=True)
    request.update(charge=1, spin=2)
    response = api.post("/v1/rest-inputs/prepare", json=request)
    assert response.status_code == 200, response.text
    qp = request["rest_options"]["quasiparticle_methods"]
    qp["bse_spin"] = "triplet"
    assert api.post("/v1/rest-inputs/prepare", json=request).status_code == 422
    qp.update(bse_spin="unrestricted", scgw="evgw", evgw_rounds=5)
    assert api.post("/v1/rest-inputs/prepare", json=request).status_code == 422
    qp.update(scgw="g0w0", renormalized_singles=True)
    assert api.post("/v1/rest-inputs/prepare", json=request).status_code == 422


def plan_task(name, request):
    return {
        "task_id": name, "title": name, "purpose": "Requested calculation", "kind": "rest",
        "system_name": request["system_name"], "job_type": request["job_type"],
        "rest_options": request.get("rest_options", {}),
        "inputs": {
            "position": request["position"], "position_unit": request["position_unit"],
            "position_source": "user", "charge": request["charge"], "charge_source": "user",
            "spin": request["spin"], "spin_source": "user",
        },
        "decision": {"xc": request["xc"], "basis": request["basis"], "source": "user",
                     "rationale": "User selected parameters"},
    }


def test_optimize_then_bse_reuses_patch_readiness_and_card_history(api):
    opt = plan_task("opt", {**payload(), "job_type": "opt", "rest_options": {}})
    bse = plan_task("excited", bse_payload())
    bse["depends_on"] = ["opt"]
    bse["inputs"].update(
        position=None, position_unit=None, position_source="prior_result", position_from_task="opt"
    )
    response = api.post("/v1/plans", json={
        "question": "Optimize then BSE", "goal": "other", "tasks": [opt, bse],
    })
    assert response.status_code == 201, response.text
    saved = response.json()
    url = f"/v1/plans/{saved['plan_id']}"
    assert api.post(url + "/tasks/opt/cards").status_code == 201
    assert api.post(url + "/tasks/excited/cards").status_code == 422
    patch = {"tasks": [{"task_id": "excited", "inputs": {
        "position": "H 0 0 0\nH 0 0 1.4", "position_unit": "bohr",
    }}]}
    revised = api.put(url, json={
        "expected_version": 1, "change_reason": "User supplied optimization", "patch": patch,
    })
    assert revised.status_code == 200, revised.text
    ready = api.post(url + "/tasks/excited/cards")
    assert ready.status_code == 201, ready.text
    card = ready.json()
    assert tomllib.loads(card["content"])["geom"]["unit"] == "bohr"
    assert api.post(url + "/tasks/excited/cards").json()["card_id"] == card["card_id"]
    # Changing the approximation only changes this task, leaving its geometry and methods intact.
    full = copy.deepcopy(bse["rest_options"])
    full["quasiparticle_methods"]["bse_tda"] = False
    revised = api.put(url, json={
        "expected_version": 2, "change_reason": "User selected full BSE",
        "patch": {"tasks": [{"task_id": "excited", "rest_options": full}]},
    })
    assert revised.status_code == 200, revised.text
    current = api.post(url + "/tasks/excited/cards").json()
    assert current["card_id"] != card["card_id"]
    assert tomllib.loads(current["content"])["geom"]["unit"] == "bohr"
    revised = api.put(url, json={
        "expected_version": 3, "change_reason": "Change optimization method",
        "patch": {"tasks": [{"task_id": "opt", "decision": {"xc": "PBE0"}}]},
    })
    assert revised.status_code == 200, revised.text
    assert api.post(url + "/tasks/excited/cards").status_code == 422
    historic = api.get(url + f"/cards/{card['card_id']}").json()
    assert historic["is_applicable_to_current_plan"] is False
    assert api.get(card["download_path"]).text == card["content"]
