"""Pydantic domain models for the REST input API.

All REST keywords are validated against the versioned catalogs in
``aifs.rest.catalogs``; no method name or output item is hardcoded here.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from aifs.rest.catalogs import ALLOWED_OUTPUTS, normalize_method_name

MAX_SYSTEM_NAME_LENGTH = 120
MAX_POSITION_LENGTH = 200_000
MAX_REST_INPUT_LENGTH = 500_000


class DomainValidationError(Exception):
    """A domain-level incompatibility (distinct from a schema violation).

    Raised for settings that are individually valid but conflict with REST
    rules, e.g. empirical dispersion on a double-hybrid/RPA method.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class RestInputRequest(BaseModel):
    """Structured request for rendering a REST TOML input card.

    Extra fields are rejected. ``xc`` is normalized to its canonical casing
    and checked against the REST method catalog during validation. The basis
    pool root is deployment configuration (``AIFS_BASIS_SET_POOL``), not a
    request field: ``basis`` is only the name inside that pool.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    system_name: str
    position: str
    job_type: Literal["energy", "opt", "force", "numerical dipole"]
    xc: str
    basis: str | None = None
    charge: float = 0.0
    spin: int = Field(default=1, ge=1)
    spin_polarization: bool | None = None
    empirical_dispersion: Literal["d3", "d3bj", "d4"] | None = None
    print_level: int = Field(default=1, ge=0)
    num_threads: int = Field(default=10, ge=1)
    outputs: list[str] = Field(default_factory=list)

    @field_validator("system_name")
    @classmethod
    def _check_system_name(cls, value: str) -> str:
        if not value:
            raise ValueError("system_name must not be empty")
        if len(value) > MAX_SYSTEM_NAME_LENGTH:
            raise ValueError(
                f"system_name must be at most {MAX_SYSTEM_NAME_LENGTH} characters"
            )
        return value

    @field_validator("position")
    @classmethod
    def _check_position(cls, value: str) -> str:
        if not value:
            raise ValueError("position must not be empty")
        if len(value) > MAX_POSITION_LENGTH:
            raise ValueError(f"position must be at most {MAX_POSITION_LENGTH} characters")
        return value

    @field_validator("charge")
    @classmethod
    def _check_charge_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("charge must be a finite number")
        return value

    @field_validator("xc")
    @classmethod
    def _normalize_xc(cls, value: str) -> str:
        normalized = normalize_method_name(value)
        if normalized is None:
            raise ValueError(f"unsupported REST method: {value!r}")
        return normalized

    @field_validator("basis")
    @classmethod
    def _empty_basis_to_none(cls, value: str | None) -> str | None:
        return value or None

    @field_validator("outputs")
    @classmethod
    def _check_outputs(cls, value: list[str]) -> list[str]:
        allowed = ", ".join(sorted(ALLOWED_OUTPUTS))
        for item in value:
            if item not in ALLOWED_OUTPUTS:
                raise ValueError(f"unsupported output item {item!r}; allowed: {allowed}")
        return value


class RestInputResponse(BaseModel):
    """Result of rendering a structured request into a REST TOML input card."""

    rest_input: str
    effective_settings: dict[str, object]
    defaults_applied: list[str]
    warnings: list[str]


class ValidationIssue(BaseModel):
    """A single validator finding on a REST input card."""

    code: str
    message: str
    section: str | None = None
    field: str | None = None
    line: int | None = None


class ValidateInputRequest(BaseModel):
    """Request to independently validate a complete REST TOML input card."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    rest_input: str

    @field_validator("rest_input")
    @classmethod
    def _check_rest_input(cls, value: str) -> str:
        if not value:
            raise ValueError("rest_input must not be empty")
        if len(value) > MAX_REST_INPUT_LENGTH:
            raise ValueError(f"rest_input must be at most {MAX_REST_INPUT_LENGTH} characters")
        return value


class ValidateInputResponse(BaseModel):
    """Result of independently validating a REST TOML input card.

    ``valid = false`` is a successful domain result, not an infrastructure
    failure.
    """

    valid: bool
    errors: list[ValidationIssue]
    warnings: list[ValidationIssue]
    parsed_sections: list[str]
