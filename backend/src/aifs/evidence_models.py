"""Request and response models for literature evidence retrieval."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EvidenceSearchRequest(BaseModel):
    """Natural-language retrieval query passed from the Harness tool."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    system_description: str = Field(min_length=1, max_length=4000)
    calculation_goal: str | None = Field(default=None, max_length=2000)
    candidate_functionals: list[str] = Field(default_factory=list, max_length=32)
    limit: int = Field(default=8, ge=1, le=50)

    @field_validator("candidate_functionals")
    @classmethod
    def _clean_functionals(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value.strip()]


class EvidenceQuote(BaseModel):
    quote: str
    page: int | None = None
    section: str | None = None
    evidence_type: str | None = None


class EvidenceHit(BaseModel):
    record_id: str
    doi: str | None = None
    title: str | None = None
    system: str | None = None
    calculation: str | None = None
    benchmark: str | None = None
    functional: str | None = None
    protocol: str | None = None
    experience_type: str | None = None
    summary: str | None = None
    score: float
    evidence: list[EvidenceQuote]


class EvidenceSearchResponse(BaseModel):
    retrieval_mode: str
    query: str
    hits: list[EvidenceHit]


class EvidenceImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    records_path: str = Field(min_length=1, max_length=2000)


class EvidenceImportResponse(BaseModel):
    imported: int
