"""Advanced inputs must survive plans, independent checks and actual downloads."""

from __future__ import annotations

import copy

import pytest
from fastapi.testclient import TestClient

from aifs.api import app
from aifs.config import get_settings
from aifs.rest import tomllib
from aifs.rest.capabilities import UPSTREAM_COMMIT
from aifs.rest.validator import validate_rest_input


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFS_WORKFLOW_DB", str(tmp_path / "workflow.sqlite3"))
    monkeypatch.setenv("AIFS_EVIDENCE_DB", str(tmp_path / "evidence.sqlite3"))
    monkeypatch.setenv("AIFS_BASIS_SET_POOL", str(tmp_path / "basis"))
    get_settings.cache_clear()
    return TestClient(app)


def task(options=None, xc="PBE", parser="legacy", job="energy"):
    return {
        "task_id": "H2",
        "title": "H2 property",
        "purpose": "Prepare requested property",
        "kind": "rest",
        "system_name": "H2",
        "job_type": job,
        "rest_options": options or {},
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
            "xc": xc,
            "basis": "def2-TZVPP",
            "xc_parser": parser,
            "source": "user",
            "rationale": "User confirmed method and required parameters",
        },
    }


def create(client, value):
    response = client.post(
        "/v1/plans", json={"question": "Requested property", "goal": "other", "tasks": [value]}
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize(
    "xc,parser",
    [
        ("wB97X", "legacy"),
        ("wB97X", "parse_xc"),
        ("wB97X-V", "parse_xc"),
        ("wB97M-V", "parse_xc"),
        ("wB97X-D3", "parse_xc"),
        ("wB97X-D3BJ", "parse_xc"),
        ("CAM-B3LYP", "legacy"),
        ("LC-wPBE", "legacy"),
        ("SVWN", "legacy"),
        ("SVWN-RPA", "legacy"),
        ("PZ-LDA", "legacy"),
        ("PW-LDA", "legacy"),
        ("LDA_X_SLATER", "legacy"),
    ],
)
def test_reviewed_method_saved_card_round_trip(client, xc, parser):
    plan = create(client, task(xc=xc, parser=parser))
    card = client.post(f"/v1/plans/{plan['plan_id']}/tasks/H2/cards")
    assert card.status_code == 201, card.text
    card = card.json()
    data = tomllib.loads(card["content"])
    assert data["ctrl"]["xc"] == xc
    assert data["ctrl"].get("xc_parser", "legacy") == parser
    assert data["ctrl"]["basis_path"].endswith("def2-TZVPP")
    assert card["render"]["effective_settings"]["rest_source_commit"] == UPSTREAM_COMMIT
    assert validate_rest_input(card["content"]).valid
    assert client.get(card["download_path"]).content.decode() == card["content"]


def test_lda_category_is_not_silently_treated_as_a_specific_functional(client):
    plan = create(client, task(xc="LDA"))
    assert plan["statuses"][0]["state"] == "unsupported"
    assert client.post(f"/v1/plans/{plan['plan_id']}/tasks/H2/cards").status_code == 422


@pytest.mark.parametrize(
    "options,job",
    [
        ({"hessian": {"frequencies": True}}, "energy"),
        ({"ctrl.hessian": {"frequencies": True}, "ctrl.thermo": {"temperature": 298.15}}, "energy"),
        (
            {
                "hessian": {},
                "thermo": {"temperature": [300, 800, 50], "pressure": 1.0, "ilowfreq": 2},
            },
            "energy",
        ),
        ({"tddft": {"tddft_method": "tda", "nroots": 6}}, "energy"),
        ({"tddft": {"tddft_spin": "triplet", "tddft_mode": "ao"}}, "energy"),
        ({"ctrl": {"analdrv_tasks": ["hessian"]}, "analdrv": {"cpscf_tol": 1e-9}}, "energy"),
        (
            {"ctrl": {"analdrv_tasks": ["hessian"]}, "thermo": {"temperature": 300.0}},
            "energy",
        ),
        (
            {
                "ctrl": {"analdrv_tasks": ["multipole"]},
                "analdrv": {"multipole_orders": [1, 2], "multipole_origin": [0.0, 0.0, 1.0]},
            },
            "energy",
        ),
        (
            {
                "tddft": {
                    "response_tddft": True,
                    "external_field_freq": 0.1,
                    "lifetime_gamma": 0.001,
                    "response_tddft_solver": "gmres",
                }
            },
            "energy",
        ),
        (
            {
                "tddft": {
                    "tddft_feast_solver": True,
                    "tddft_feast_eigenrange_min": 0.1,
                    "tddft_feast_eigenrange_max": 0.5,
                    "tddft_method": "tda",
                }
            },
            "energy",
        ),
        ({"tddft": {"pysoc": True, "tddft_spin": "both", "tddft_mode": "ao"}}, "energy"),
        ({"tddft": {"tddft_grad_state": 1, "nroots": 3}}, "force"),
        (
            {
                "geom": {
                    "rrs_pbc": True,
                    "pbc_dim": 1,
                    "unit_cell_index": [0, 1],
                    "rrs_pbc_vec": [0.0, 0.0, 1.48],
                    "max_step": [0],
                    "k_points": [10],
                }
            },
            "energy",
        ),
        (
            {"geometric_pyo3": {"transition": True, "hessian": "first", "thermo": [298.15, 1.0]}},
            "opt",
        ),
        ({"geometric_pyo3": {"irc": True, "irc_direction": "both", "hessian": "first"}}, "opt"),
        (
            {
                "ctrl": {
                    "max_scf_cycle": 200,
                    "scf_acc_etot": 1e-10,
                    "solvent_model": "CPCM",
                    "solvent": "water",
                }
            },
            "energy",
        ),
        ({"ctrl.ri_pt2": {"fp_mode": "FP64", "streaming": True}}, "energy"),
        (
            {"geom": {"ext_field_dipole": [0, 0.001, 0], "ghost": "basis set H 0.0 0.0 2.0"}},
            "energy",
        ),
    ],
)
def test_extensions_saved_revised_and_downloaded(client, options, job):
    value = task(options=options, job=job)
    plan = create(client, value)
    assert plan["statuses"][0]["state"] == "ready_for_card", plan["statuses"]
    response = client.post(f"/v1/plans/{plan['plan_id']}/tasks/H2/cards")
    assert response.status_code == 201, response.text
    old = response.json()
    parsed = tomllib.loads(old["content"])
    for section, fields in options.items():
        table = parsed
        for part in section.split("."):
            table = table[part]
        for key, value_field in fields.items():
            assert table[key] == value_field
    value["rest_options"].setdefault("ctrl", {})["num_max_diis"] = 10
    new_draft = {"question": "Requested property", "goal": "other", "tasks": [value]}
    revised = client.put(
        f"/v1/plans/{plan['plan_id']}",
        json={
            "expected_version": 1,
            "change_reason": "User adjusted SCF options",
            "plan": new_draft,
        },
    )
    assert revised.status_code == 200
    latest = client.post(f"/v1/plans/{plan['plan_id']}/tasks/H2/cards").json()
    assert latest["version"] == 2 and old["version"] == 1
    assert old["content"] != latest["content"]
    assert client.get(old["download_path"]).content.decode() == old["content"]
    assert client.get(latest["download_path"]).content.decode() == latest["content"]
    fetched = client.get(f"/v1/plans/{plan['plan_id']}").json()
    assert fetched["plan"]["tasks"][0]["rest_options"] == value["rest_options"]


@pytest.mark.parametrize(
    "options,xc,parser,job",
    [
        ({"ctrl": {"charge": 1}}, "PBE", "legacy", "energy"),
        ({"hessian": {"frequencies": "yes"}}, "PBE", "legacy", "energy"),
        ({"hessian": {}}, "XYG3", "legacy", "energy"),
        ({"hessian": {}}, "wB97X", "legacy", "energy"),
        ({"hessian": {}}, "SCAN", "legacy", "energy"),
        ({"geom": {"ghost": "basis set H 0 0 2"}}, "PBE", "legacy", "energy"),
        ({"geom": {"ghost": "point charge 1.0 0.0 0.0 1e-3"}}, "PBE", "legacy", "energy"),
        ({"thermo": {}}, "PBE", "legacy", "energy"),
        ({"thermo": {"temperature": [800, 300, 50]}, "hessian": {}}, "PBE", "legacy", "energy"),
        ({"tddft": {"nroots": True}}, "PBE", "legacy", "energy"),
        ({"tddft": {"tddft_spin": "triplet"}}, "PBE", "legacy", "energy"),
        ({"geometric_pyo3": {"converge_grms": 1e-5}}, "PBE", "legacy", "opt"),
        ({"geometric_pyo3": {"transition": True}}, "PBE", "legacy", "energy"),
        ({"geometric_pyo3": {"transition": True}}, "PBE", "legacy", "opt"),
        ({"geometric_pyo3": {"irc": True, "hessian": "last"}}, "PBE", "legacy", "opt"),
        (
            {"geometric_pyo3": {"transition": True, "irc": True, "hessian": "first"}},
            "PBE",
            "legacy",
            "opt",
        ),
        ({"hessian": {}}, "wB97X-V", "parse_xc", "energy"),
        ({}, "wB97X-V", "parse_xc", "opt"),
        ({"ctrl": {"empirical_dispersion": "d3bj"}}, "wB97X-V", "parse_xc", "energy"),
        (
            {"hessian": {}, "ctrl.ri_jk": {"pair_screen_threshold": 1e-12}},
            "PBE",
            "legacy",
            "energy",
        ),
    ],
)
def test_unverified_or_invalid_combination_is_saved_but_blocked(client, options, xc, parser, job):
    plan = create(client, task(options, xc, parser, job))
    assert plan["statuses"][0]["state"] == "needs_input", plan["statuses"]
    assert plan["statuses"][0]["blockers"]
    assert client.post(f"/v1/plans/{plan['plan_id']}/tasks/H2/cards").status_code == 422


def test_unrestricted_tddft_does_not_invent_spin_channel(client):
    value = task({"tddft": {"tddft_spin": "singlet"}})
    value["inputs"]["spin"] = 2
    plan = create(client, value)
    assert "Unrestricted TDDFT" in " ".join(plan["statuses"][0]["blockers"])
    del value["rest_options"]["tddft"]["tddft_spin"]
    revised = client.put(
        f"/v1/plans/{plan['plan_id']}",
        json={
            "expected_version": 1,
            "change_reason": "Remove invalid spin channel",
            "plan": {"question": "Open-shell excited states", "goal": "other", "tasks": [value]},
        },
    )
    assert revised.json()["statuses"][0]["state"] == "ready_for_card"
    assert client.post(f"/v1/plans/{plan['plan_id']}/tasks/H2/cards").status_code == 201


@pytest.mark.parametrize("xc", ["wB97X", "CAM-B3LYP", "SCAN"])
def test_analdrv_open_shell_hessian_preserves_requested_method(client, xc):
    value = task({"ctrl": {"analdrv_tasks": ["hessian"]}}, xc=xc)
    value["inputs"].update(charge=1, spin=2)
    plan = create(client, value)
    assert plan["statuses"][0]["state"] == "ready_for_card", plan["statuses"]
    response = client.post(f"/v1/plans/{plan['plan_id']}/tasks/H2/cards")
    assert response.status_code == 201, response.text
    data = tomllib.loads(response.json()["content"])
    assert data["ctrl"]["spin_polarization"] is True
    assert data["ctrl"]["xc"] == xc
    assert data["ctrl"]["analdrv_tasks"] == ["hessian"]
    assert "hessian" not in data
    assert validate_rest_input(response.json()["content"]).valid


@pytest.mark.parametrize(
    "options,xc,spin,job,reason",
    [
        ({"analdrv": {}}, "PBE", 1, "energy", "analdrv_tasks"),
        ({"ctrl": {"analdrv_tasks": ["hessian"]}, "hessian": {}}, "PBE", 1, "energy", "separate"),
        ({"ctrl": {"analdrv_tasks": ["hessian"]}}, "XYG3", 1, "energy", "post-SCF"),
        (
            {"ctrl": {"analdrv_tasks": ["hessian"]}, "analdrv": {"atm_list": [0]}, "thermo": {}},
            "PBE",
            1,
            "energy",
            "all atoms",
        ),
        (
            {"ctrl": {"analdrv_tasks": ["hessian"]}, "analdrv": {"atm_list": [2]}},
            "PBE",
            1,
            "energy",
            "indices",
        ),
        (
            {"ctrl": {"analdrv_tasks": ["multipole"]}, "analdrv": {"multipole_orders": [0]}},
            "PBE",
            1,
            "energy",
            "1 to 4",
        ),
        ({"ctrl": {"analdrv_tasks": ["multipole"]}}, "R-xDH7", 1, "energy", "PT2"),
        (
            {"ctrl": {"analdrv_tasks": ["multipole"], "frozen_core_postscf": 1}},
            "XYG3",
            1,
            "energy",
            "frozen",
        ),
        ({"ctrl": {"analdrv_tasks": ["multipole"]}}, "XYG3", 2, "energy", "unrestricted"),
        ({"tddft": {"response_tddft": True}}, "PBE", 2, "energy", "restricted"),
        ({"tddft": {"tddft_feast_solver": True}}, "PBE", 2, "energy", "FEAST"),
        ({"tddft": {"tddft_feast_solver": True, "tddft_mode": "ao"}}, "PBE", 1, "energy", "MO"),
        ({"tddft": {"tddft_mode": "ao", "tddft_fxc_driver": "mo"}}, "PBE", 2, "energy", "fxc"),
        (
            {"tddft": {"response_tddft": True, "tddft_grad_state": 1}},
            "PBE",
            1,
            "force",
            "eigenvalue",
        ),
        ({"tddft": {"tddft_grad_state": 4, "nroots": 3}}, "PBE", 1, "force", "nroots"),
        ({"tddft": {"tddft_grad_state": 1}}, "PBE", 1, "energy", "force"),
        ({"tddft": {"tddft_grad_state": 1}}, "PBE", 2, "force", "restricted"),
        ({"tddft": {"tddft_grad_state": 1}}, "wB97X", 1, "force", "gradient method"),
        ({"tddft": {"tddft_grad_state": 1}}, "SCAN", 1, "force", "gradient method"),
        ({"tddft": {"pysoc": True}}, "PBE", 1, "energy", "both"),
        (
            {
                "tddft": {
                    "tddft_feast_solver": True,
                    "tddft_feast_eigenrange_min": 0.8,
                    "tddft_feast_eigenrange_max": 0.4,
                }
            },
            "PBE",
            1,
            "energy",
            "range",
        ),
        (
            {"tddft": {"response_tddft": True, "stability": "internal"}},
            "PBE",
            1,
            "energy",
            "stability",
        ),
        (
            {"tddft": {"response_tddft": True, "response_tddft_x_points": 0}},
            "PBE",
            1,
            "energy",
            "integer",
        ),
        ({"geom": {"rrs_pbc": True}}, "PBE", 1, "energy", "unit_cell_index"),
        (
            {
                "geom": {
                    "rrs_pbc": True,
                    "pbc_dim": 1,
                    "unit_cell_index": [2],
                    "rrs_pbc_vec": [1, 0, 0],
                    "max_step": [1],
                    "k_points": [10],
                }
            },
            "PBE",
            1,
            "energy",
            "indices",
        ),
        (
            {
                "geom": {
                    "rrs_pbc": True,
                    "pbc_dim": 1,
                    "unit_cell_index": [0],
                    "rrs_pbc_vec": [1, 0],
                    "max_step": [1],
                    "k_points": [10],
                }
            },
            "PBE",
            1,
            "energy",
            "3",
        ),
        (
            {
                "geom": {
                    "rrs_pbc": True,
                    "pbc_dim": 1,
                    "unit_cell_index": [0],
                    "rrs_pbc_vec": [1, 0, 0],
                    "max_step": [1],
                    "k_points": [0],
                }
            },
            "PBE",
            1,
            "energy",
            "positive",
        ),
        (
            {
                "geom": {
                    "rrs_pbc": True,
                    "pbc_dim": 1,
                    "unit_cell_index": [0],
                    "rrs_pbc_vec": [1, 0, 0],
                    "max_step": [1],
                    "k_points": [10],
                }
            },
            "PBE",
            2,
            "energy",
            "closed-shell",
        ),
    ],
)
def test_property_combinations_cannot_bypass_plan_validation(
    client, options, xc, spin, job, reason
):
    value = task(options, xc=xc, job=job)
    value["inputs"]["spin"] = spin
    plan = create(client, value)
    assert plan["statuses"][0]["state"] == "needs_input"
    assert reason.lower() in " ".join(plan["statuses"][0]["blockers"]).lower()
    assert client.post(f"/v1/plans/{plan['plan_id']}/tasks/H2/cards").status_code == 422


@pytest.mark.parametrize(
    "addition",
    [
        "\n[tddft]\nresponse_tddft = true\ntddft_grad_state = 1\n",
        '\n[tddft]\ntddft_feast_solver = true\ntddft_mode = "ao"\n',
        "\n[analdrv]\ncpscf_tol = 1e-9\n",
        '\n[geom]\nname = "H2"\nunit = "angstrom"\nposition = "H 0 0 0\\nH 0 0 0.74"\n'
        "rrs_pbc = true\npbc_dim = 1\nunit_cell_index = [0, 1]\n"
        "rrs_pbc_vec = [0, 0, 1.48]\nmax_step = [0]\nk_points = [0]\n",
    ],
)
def test_independent_checker_rejects_conflicts_in_manually_edited_card(addition):
    ctrl = (
        '[ctrl]\nxc = "PBE"\nbasis_path = "/basis/def2-TZVP"\nprint_level = 1\n'
        'num_threads = 1\njob_type = "energy"\ncharge = 0.0\nspin = 1\n'
        "spin_polarization = false\n"
    )
    geom = '\n[geom]\nname = "H2"\nunit = "angstrom"\nposition = "H 0 0 0\\nH 0 0 0.74"\n'
    assert validate_rest_input(ctrl + geom).valid
    invalid = ctrl + ("" if "[geom]" in addition else geom) + addition
    result = validate_rest_input(invalid)
    assert not result.valid and result.errors


def test_fixed_atoms_preserved_and_wrong_engine_blocked(client):
    value = task({"geometric_pyo3": {"coordsys": "tric"}}, job="opt")
    value["inputs"]["position"] = "H 0 0 0 0\nH 1 0 0 0.74"
    plan = create(client, value)
    response = client.post(f"/v1/plans/{plan['plan_id']}/tasks/H2/cards")
    assert response.status_code == 201, response.text
    assert (
        tomllib.loads(response.json()["content"])["geom"]["position"].strip()
        == value["inputs"]["position"]
    )
    value["rest_options"]["ctrl"] = {"opt_engine": "LBFGS"}
    blocked = create(client, value)
    assert blocked["statuses"][0]["state"] == "needs_input"


def test_capabilities_report_exact_source_units_and_pending(client):
    overview = client.get("/v1/rest-capabilities").json()
    assert overview["source_commit"] == UPSTREAM_COMMIT
    assert overview["pending"]
    assert "REST not executed" in overview["validation_scope"]
    assert (
        client.get("/v1/rest-capabilities?section=thermo").json()["keywords"]["pressure"]["unit"]
        == "atm"
    )
    assert (
        client.get("/v1/rest-capabilities?section=geometric_pyo3").json()["keywords"]["thermo"][
            "unit"
        ]
        == "K, bar"
    )
    assert client.get("/v1/rest-capabilities?section=made_up").status_code == 422


def test_independent_validator_checks_extension_values(valid_card):
    assert not validate_rest_input(valid_card + "\n[hessian]\nfrequencies = 'yes'\n").valid
    assert not validate_rest_input(valid_card + "\n[tddft]\nnroots = -1\n").valid
    assert not validate_rest_input(valid_card + "\n[thermo]\ntemperature = 298.15\n").valid
    # Geometry nan/inf must never be counted as valid coordinates.
    assert not validate_rest_input(valid_card.replace("O 0.0", "O nan")).valid


def test_literal_option_strings_cannot_inject_tables(client):
    options = {"ctrl": {"chkfile": 'test"\n[evil]\ncharge=2\n"'}}
    plan = create(client, task(copy.deepcopy(options)))
    card = client.post(f"/v1/plans/{plan['plan_id']}/tasks/H2/cards").json()
    parsed = tomllib.loads(card["content"])
    assert "evil" not in parsed
    assert parsed["ctrl"]["chkfile"] == options["ctrl"]["chkfile"]
