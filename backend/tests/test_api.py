"""Tests for the FastAPI application in aifs.api."""

from pathlib import PurePosixPath
from typing import Any

import pytest
from fastapi.testclient import TestClient

from aifs import __version__
from aifs.api import app
from aifs.config import get_settings
from aifs.rest import tomllib

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "aifs-api", "version": __version__}


def test_prepare_card_without_a_plan_validates_and_returns_an_attachment_name(
    request_payload, tmp_path, monkeypatch
):
    database = tmp_path / "unused-workflow.sqlite3"
    monkeypatch.setenv("AIFS_WORKFLOW_DB", str(database))
    get_settings.cache_clear()
    payload = {**request_payload, "charge": 0, "spin": 1, "basis": "def2-TZVP"}
    response = client.post("/v1/rest-inputs/prepare", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["validation"]["valid"] is True
    assert body["validation"]["errors"] == []
    assert body["filename"].startswith("water-energy-") and body["filename"].endswith(".in")
    assert tomllib.loads(body["rest_input"])["geom"]["unit"] == "angstrom"
    assert not database.exists()


@pytest.mark.parametrize("field", ["position_unit", "charge", "spin", "basis"])
@pytest.mark.parametrize("value", ["omitted", None])
def test_prepare_card_rejects_missing_scientific_parameters(request_payload, field, value):
    payload = {**request_payload, "charge": 0, "spin": 1, "basis": "def2-TZVP"}
    if value == "omitted":
        payload.pop(field)
    else:
        payload[field] = value
    response = client.post("/v1/rest-inputs/prepare", json=payload)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "request_validation_error"


def test_prepare_card_never_delivers_invalid_rendered_content(request_payload, monkeypatch):
    from aifs.models import RestInputResponse

    monkeypatch.setattr(
        "aifs.api.render_rest_input",
        lambda _: RestInputResponse(
            rest_input="not TOML", effective_settings={}, defaults_applied=[], warnings=[]
        ),
    )
    payload = {**request_payload, "charge": 0, "spin": 1, "basis": "def2-TZVP"}
    response = client.post("/v1/rest-inputs/prepare", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "card_validation_failed"
    assert "rest_input" not in response.json()


def test_prepare_card_preserves_an_ion_bohr_geometry_and_safe_filename(request_payload):
    payload = {
        **request_payload,
        "system_name": "../../Al3 anion",
        "position_unit": "bohr",
        "position": "Al 0 0 0\nAl 4.9 0 0\nAl 2.45 4.2 0",
        "charge": -1,
        "spin": 1,
        "basis": "aug-cc-pVTZ",
        "xc": "wB97M-V",
        "xc_parser": "parse_xc",
    }
    response = client.post("/v1/rest-inputs/prepare", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    data = tomllib.loads(body["rest_input"])
    assert data["geom"]["position"].strip() == payload["position"]
    assert data["geom"]["unit"] == "bohr"
    assert data["ctrl"]["charge"] == -1
    assert "/" not in body["filename"] and ".." not in body["filename"]


def test_direct_cards_for_the_same_system_do_not_overwrite_other_settings(request_payload):
    payload = {**request_payload, "charge": 0, "spin": 1, "basis": "def2-TZVP"}
    first = client.post("/v1/rest-inputs/prepare", json=payload).json()
    second = client.post("/v1/rest-inputs/prepare", json={**payload, "xc": "PBE0"}).json()
    assert first["filename"] != second["filename"]
    assert first["rest_input"] != second["rest_input"]
    assert (
        client.post("/v1/rest-inputs/prepare", json=payload).json()["filename"] == first["filename"]
    )


def test_direct_exports_are_relative_grouped_and_reused(request_payload):
    payload = {**request_payload, "charge": 0, "spin": 1, "basis": "def2-TZVP"}
    first = client.post("/v1/rest-inputs/prepare", json=payload).json()
    repeated = client.post("/v1/rest-inputs/prepare", json=payload).json()
    changed = client.post("/v1/rest-inputs/prepare", json={**payload, "xc": "PBE0"}).json()
    path = PurePosixPath(first["export_relative_path"])
    assert not path.is_absolute() and ".." not in path.parts
    assert path.parts[0] == "aifs-inputs" and len(path.parts) == 3
    assert path.name == first["filename"]
    assert repeated["export_relative_path"] == first["export_relative_path"]
    assert PurePosixPath(changed["export_relative_path"]).parent != path.parent


def test_create_rest_input_returns_200_with_parseable_card(
    request_payload: dict[str, Any],
) -> None:
    response = client.post("/v1/rest-inputs", json=request_payload)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"rest_input", "effective_settings", "defaults_applied", "warnings"}
    data = tomllib.loads(body["rest_input"])
    assert data["ctrl"]["xc"] == "B3LYP"
    assert data["ctrl"]["basis_path"] == "/data/rest/basis_sets/def2-TZVPP"
    assert "basis=def2-TZVPP" in body["defaults_applied"]
    assert "spin_polarization=false" in body["defaults_applied"]


def test_create_rest_input_domain_error_422_stable_json(
    request_payload: dict[str, Any],
) -> None:
    payload = {**request_payload, "xc": "XYG3", "empirical_dispersion": "d3bj"}
    response = client.post("/v1/rest-inputs", json=payload)
    assert response.status_code == 422
    body = response.json()
    error = body["error"]
    assert error["code"] == "empirical_dispersion_not_needed"
    assert isinstance(error["message"], str)
    assert error["message"]


def test_create_rest_input_schema_error_422_stable_json(
    request_payload: dict[str, Any],
) -> None:
    response = client.post("/v1/rest-inputs", json={**request_payload, "spin": 0})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "request_validation_error"
    detail = body["error"]["detail"]
    assert isinstance(detail, list) and detail
    assert set(detail[0]) == {"loc", "msg", "type"}


def test_create_rest_input_extra_field_422(request_payload: dict[str, Any]) -> None:
    response = client.post("/v1/rest-inputs", json={**request_payload, "junk": 1})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"


def test_create_rest_input_rejects_client_supplied_pool(
    request_payload: dict[str, Any],
) -> None:
    response = client.post(
        "/v1/rest-inputs", json={**request_payload, "basis_set_pool": "/tmp/evil"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"


def test_create_rest_input_without_pool_config_is_500(
    request_payload: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AIFS_BASIS_SET_POOL", raising=False)
    get_settings.cache_clear()
    response = client.post("/v1/rest-inputs", json=request_payload)
    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "configuration_error"
    assert "AIFS_BASIS_SET_POOL" in error["message"]


def test_validate_endpoint_accepts_valid_card_200(valid_card: str) -> None:
    response = client.post("/v1/rest-inputs/validate", json={"rest_input": valid_card})
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["errors"] == []
    assert body["warnings"] == []
    assert body["parsed_sections"] == ["ctrl", "geom"]


def test_validate_endpoint_domain_failure_is_200(valid_card: str) -> None:
    card = valid_card.replace("spin = 1", "spin = 0")
    response = client.post("/v1/rest-inputs/validate", json={"rest_input": card})
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert any(item["code"] == "out_of_range" for item in body["errors"])


def test_validate_endpoint_syntax_error_is_200() -> None:
    response = client.post("/v1/rest-inputs/validate", json={"rest_input": "not toml"})
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert [item["code"] for item in body["errors"]] == ["toml_syntax"]


def test_validate_endpoint_schema_error_422() -> None:
    response = client.post("/v1/rest-inputs/validate", json={"rest_input": "   "})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"


def test_recommendations_route_does_not_exist() -> None:
    response = client.get("/v1/recommendations")
    assert response.status_code == 404


def test_evidence_import_and_search_are_source_linked(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    records = tmp_path / "records.jsonl"
    records.write_text(
        json.dumps(
            {
                "record_id": "MREC-api",
                "source": {"doi": "10.1/api", "title": "Water DFT"},
                "context": {
                    "system": "water molecule",
                    "calculation": "geometry optimization",
                    "benchmark": "CCSD(T)",
                },
                "method": {"functional": "PBE0", "protocol": "def2-TZVP"},
                "experience": {"type": "evaluation", "summary": "good geometry"},
                "evidence": [
                    {
                        "quote": "good geometry",
                        "page": 2,
                        "section": "Results",
                        "evidence_type": "text",
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    db = tmp_path / "api.sqlite3"
    monkeypatch.setenv("AIFS_EVIDENCE_DB", str(db))
    get_settings.cache_clear()
    imported = client.post("/v1/evidence/import", json={"records_path": str(records)})
    assert imported.status_code == 200
    assert imported.json() == {"imported": 1}
    response = client.post(
        "/v1/evidence/search",
        json={
            "system_description": "water molecule",
            "calculation_goal": "geometry optimization",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["retrieval_mode"] == "lexical_fallback"
    assert body["hits"][0]["doi"] == "10.1/api"
    assert body["hits"][0]["evidence"][0]["page"] == 2
