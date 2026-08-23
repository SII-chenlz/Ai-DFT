"""FastAPI application exposing the AIFS REST input API.

Endpoints:

- ``GET /health``: liveness probe.
- ``POST /v1/rest-inputs``: render a structured request into a REST TOML card.
  Domain incompatibilities return 422 with a stable JSON error.
- ``POST /v1/rest-inputs/validate``: independently validate a complete card;
  ``valid=false`` is a 200 domain result, never an infrastructure failure.

Deployment misconfiguration (e.g. an unset ``AIFS_BASIS_SET_POOL``) returns
500 with a stable JSON error; it is an infrastructure failure, not a domain
one.

The recommendation endpoint is deliberately absent; the recommender is
implemented by a later task.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from aifs.config import ConfigurationError
from aifs.models import (
    DomainValidationError,
    RestInputRequest,
    RestInputResponse,
    ValidateInputRequest,
    ValidateInputResponse,
)
from aifs.rest.renderer import render_rest_input
from aifs.rest.validator import validate_rest_input

SERVICE_NAME = "aifs-api"
SERVICE_VERSION = "0.1.0"

app = FastAPI(title="AIFS API", version=SERVICE_VERSION)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME, "version": SERVICE_VERSION}


@app.post("/v1/rest-inputs", response_model=RestInputResponse)
def create_rest_input(request: RestInputRequest) -> RestInputResponse:
    """Render a structured request into a REST TOML input card."""
    return render_rest_input(request)


@app.post("/v1/rest-inputs/validate", response_model=ValidateInputResponse)
def validate_rest_input_card(request: ValidateInputRequest) -> ValidateInputResponse:
    """Independently validate a complete REST TOML input card."""
    return validate_rest_input(request.rest_input)


@app.exception_handler(DomainValidationError)
async def domain_validation_error_handler(
    request: Request, exc: DomainValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(ConfigurationError)
async def configuration_error_handler(
    request: Request, exc: ConfigurationError
) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "configuration_error", "message": exc.message}},
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    detail = [
        {
            "loc": [str(part) for part in item.get("loc", ())],
            "msg": item.get("msg", ""),
            "type": item.get("type", ""),
        }
        for item in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "request_validation_error", "detail": detail}},
    )
