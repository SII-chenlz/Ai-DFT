"""FastAPI application exposing AIFS evidence, workflow and REST card APIs.

Endpoints:

- ``GET /health``: liveness probe.
- ``POST /v1/rest-inputs``: render a structured request into a REST TOML card.
  Domain incompatibilities return 422 with a stable JSON error.
- ``POST /v1/rest-inputs/validate``: independently validate a complete card;
  ``valid=false`` is a 200 domain result, never an infrastructure failure.
- ``/v1/plans``: persist versioned task graphs, decisions and validated cards.

Deployment misconfiguration (e.g. an unset ``AIFS_BASIS_SET_POOL``) returns
500 with a stable JSON error; it is an infrastructure failure, not a domain
one.

The recommendation endpoint remains deliberately absent; evidence retrieval
supports the Harness LLM but the backend does not make the recommendation.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from aifs import __version__
from aifs.config import ConfigurationError
from aifs.evidence_models import (
    EvidenceImportRequest,
    EvidenceImportResponse,
    EvidenceSearchRequest,
    EvidenceSearchResponse,
)
from aifs.evidence_store import EvidenceStore
from aifs.models import (
    DomainValidationError,
    RestInputRequest,
    RestInputResponse,
    ValidateInputRequest,
    ValidateInputResponse,
)
from aifs.rest.renderer import render_rest_input
from aifs.rest.validator import validate_rest_input
from aifs.vector_index import EmbeddingProvider, FaissIndex, SentenceTransformerProvider
from aifs.workflow_models import PlanDraft, PlanRevisionRequest
from aifs.workflow_store import WorkflowError, WorkflowStore

SERVICE_NAME = "aifs-api"
SERVICE_VERSION = __version__

app = FastAPI(title="AIFS API", version=SERVICE_VERSION)


@lru_cache
def _embedding_provider() -> EmbeddingProvider | None:
    from aifs.config import get_settings

    model = get_settings().embedding_model.strip()
    return SentenceTransformerProvider(model) if model else None


@lru_cache
def _faiss_index() -> FaissIndex | None:
    from aifs.config import get_settings

    provider = _embedding_provider()
    return FaissIndex(Path(get_settings().faiss_index), provider) if provider else None


def _evidence_store() -> EvidenceStore:
    from aifs.config import get_settings

    return EvidenceStore(Path(get_settings().evidence_db), faiss_index=_faiss_index())


def _workflow_store() -> WorkflowStore:
    from aifs.config import get_settings

    return WorkflowStore(Path(get_settings().workflow_db))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME, "version": SERVICE_VERSION}


@app.post("/v1/rest-inputs", response_model=RestInputResponse)
def create_rest_input(request: RestInputRequest) -> RestInputResponse:
    """Render a structured request into a REST TOML input card."""
    return render_rest_input(request)


@app.get("/v1/rest-capabilities")
def rest_capabilities(section: str | None = None) -> dict[str, object]:
    """Expose the reviewed contract and explicit remaining integration gaps."""
    from aifs.rest.capabilities import capability_view

    try:
        return capability_view(section)
    except ValueError as exc:
        raise DomainValidationError("unknown_rest_section", str(exc)) from exc


@app.post("/v1/rest-inputs/validate", response_model=ValidateInputResponse)
def validate_rest_input_card(request: ValidateInputRequest) -> ValidateInputResponse:
    """Independently validate a complete REST TOML input card."""
    return validate_rest_input(request.rest_input)


@app.post("/v1/evidence/search", response_model=EvidenceSearchResponse)
def search_evidence(request: EvidenceSearchRequest) -> EvidenceSearchResponse:
    """Return source-linked literature evidence; never a final recommendation."""
    store = _evidence_store()
    try:
        return store.search(request)
    finally:
        store.close()


@app.post("/v1/evidence/import", response_model=EvidenceImportResponse)
def import_evidence(request: EvidenceImportRequest) -> EvidenceImportResponse:
    """Import Record-Builder JSON/JSONL into the configured evidence store."""
    from aifs.evidence_import import import_records

    store = _evidence_store()
    try:
        return EvidenceImportResponse(imported=import_records(Path(request.records_path), store))
    finally:
        store.close()


@app.post("/v1/plans", status_code=201)
def create_plan(plan: PlanDraft) -> dict:
    store = _workflow_store()
    try:
        return store.create(plan)
    finally:
        store.close()


@app.get("/v1/plans")
def list_plans() -> dict:
    store = _workflow_store()
    try:
        return {"plans": store.list()}
    finally:
        store.close()


@app.get("/v1/plans/{plan_id}")
def get_plan(plan_id: str, version: int | None = None) -> dict:
    store = _workflow_store()
    try:
        return store.get(plan_id, version)
    finally:
        store.close()


@app.put("/v1/plans/{plan_id}")
def revise_plan(plan_id: str, request: PlanRevisionRequest) -> dict:
    store = _workflow_store()
    try:
        return store.revise(plan_id, request.expected_version, request.change_reason, request.plan)
    finally:
        store.close()


@app.post("/v1/plans/{plan_id}/tasks/{task_id}/cards", status_code=201)
def generate_task_card(plan_id: str, task_id: str, request: Request) -> dict:
    store = _workflow_store()
    try:
        card = store.generate_card(plan_id, task_id)
        card["download_url"] = str(request.base_url).rstrip("/") + card["download_path"]
        return card
    finally:
        store.close()


@app.get("/v1/plans/{plan_id}/cards/{card_id}")
def get_task_card(plan_id: str, card_id: str, request: Request) -> dict:
    store = _workflow_store()
    try:
        card = store.get_card(plan_id, card_id)
        card["download_url"] = str(request.base_url).rstrip("/") + card["download_path"]
        return card
    finally:
        store.close()


@app.get("/v1/plans/{plan_id}/cards/{card_id}/download")
def download_task_card(plan_id: str, card_id: str) -> Response:
    store = _workflow_store()
    try:
        card = store.get_card(plan_id, card_id)
        return Response(
            card["content"],
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{card["filename"]}"'},
        )
    finally:
        store.close()


@app.exception_handler(WorkflowError)
async def workflow_error_handler(request: Request, exc: WorkflowError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(DomainValidationError)
async def domain_validation_error_handler(
    request: Request, exc: DomainValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(ConfigurationError)
async def configuration_error_handler(request: Request, exc: ConfigurationError) -> JSONResponse:
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
