"""Tests for the FastAPI application in aifs.api."""

from typing import Any

from fastapi.testclient import TestClient

from aifs.api import app
from aifs.rest import tomllib

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "aifs-api", "version": "0.1.0"}


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
