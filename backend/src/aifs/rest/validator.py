"""Independent validation of REST TOML input cards.

This module never calls the renderer: it parses the TOML itself and checks
the card against the versioned REST catalogs. Errors are returned in a
stable, deterministic order; when the TOML cannot be parsed at all, only the
syntax error is reported.
"""

from __future__ import annotations

import math
import re
from typing import Any

from aifs.models import ValidateInputResponse, ValidationIssue
from aifs.rest import catalogs, tomllib

CTRL_REQUIRED_FIELDS: tuple[str, ...] = (
    "xc",
    "basis_path",
    "print_level",
    "num_threads",
    "job_type",
    "charge",
    "spin",
    "spin_polarization",
)
GEOM_REQUIRED_FIELDS: tuple[str, ...] = ("name", "position")

CTRL_FIELDS: frozenset[str] = frozenset(CTRL_REQUIRED_FIELDS + ("empirical_dispersion", "outputs"))
GEOM_FIELDS: frozenset[str] = frozenset(GEOM_REQUIRED_FIELDS + ("unit",))
KNOWN_OPTIONAL_SECTIONS: frozenset[str] = frozenset(
    {"hessian", "thermo", "geometric_pyo3"}
)

# Keywords from other input-card conventions that REST does not support.
FORBIDDEN_KEYWORDS: frozenset[str] = frozenset({"method", "coord", "molecule"})


def _toml_error_line(exc: Exception) -> int | None:
    """Read the syntax-error line across tomli and stdlib tomllib versions."""
    line = getattr(exc, "lineno", None)
    if isinstance(line, int):
        return line
    match = re.search(r"\bat line (\d+)\b", str(exc))
    return int(match.group(1)) if match else None


def _issue(
    code: str,
    message: str,
    *,
    section: str | None = None,
    field: str | None = None,
    line: int | None = None,
) -> ValidationIssue:
    return ValidationIssue(code=code, message=message, section=section, field=field, line=line)


def _check_sections(
    data: dict[str, Any], errors: list[ValidationIssue]
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Extract the [ctrl] and [geom] tables, reporting missing/invalid ones."""
    ctrl: dict[str, Any] | None = None
    geom: dict[str, Any] | None = None

    for key, value in data.items():
        if not isinstance(value, dict):
            errors.append(
                _issue("invalid_section", f"top-level key {key!r} must be a TOML table")
            )

    if "ctrl" not in data:
        errors.append(_issue("missing_section", "required section [ctrl] is missing"))
    elif not isinstance(data["ctrl"], dict):
        errors.append(_issue("invalid_section", "section [ctrl] must be a TOML table"))
    else:
        ctrl = data["ctrl"]

    if "geom" not in data:
        errors.append(_issue("missing_section", "required section [geom] is missing"))
    elif not isinstance(data["geom"], dict):
        errors.append(_issue("invalid_section", "section [geom] must be a TOML table"))
    else:
        geom = data["geom"]

    return ctrl, geom


def _check_forbidden_keywords(
    data: dict[str, Any],
    ctrl: dict[str, Any] | None,
    geom: dict[str, Any] | None,
    errors: list[ValidationIssue],
) -> None:
    for key in data:
        if key.lower() in FORBIDDEN_KEYWORDS:
            errors.append(
                _issue("forbidden_keyword", f"keyword {key!r} is not a REST keyword", field=key)
            )
    for section_name, table in (("ctrl", ctrl), ("geom", geom)):
        if table is None:
            continue
        for key in table:
            if key.lower() in FORBIDDEN_KEYWORDS:
                errors.append(
                    _issue(
                        "forbidden_keyword",
                        f"keyword {key!r} is not a REST keyword",
                        section=section_name,
                        field=key,
                    )
                )


def _check_unknown_sections_and_keywords(
    data: dict[str, Any],
    ctrl: dict[str, Any] | None,
    geom: dict[str, Any] | None,
    warnings: list[ValidationIssue],
) -> None:
    """Surface catalog gaps without rejecting forward-compatible REST fields."""
    known_sections = {"ctrl", "geom"} | KNOWN_OPTIONAL_SECTIONS
    for key, value in data.items():
        if isinstance(value, dict) and key not in known_sections:
            warnings.append(
                _issue(
                    "unknown_section",
                    f"section [{key}] is not in the current REST section catalog",
                    section=key,
                )
            )

    for section_name, table, known_fields in (
        ("ctrl", ctrl, CTRL_FIELDS),
        ("geom", geom, GEOM_FIELDS),
    ):
        if table is None:
            continue
        for key in table:
            if key not in known_fields:
                warnings.append(
                    _issue(
                        "unknown_keyword",
                        f"keyword {key!r} is not in the current REST keyword catalog",
                        section=section_name,
                        field=key,
                    )
                )


def _check_required_and_placement(
    ctrl: dict[str, Any] | None,
    geom: dict[str, Any] | None,
    errors: list[ValidationIssue],
) -> None:
    if ctrl is not None:
        for field in CTRL_REQUIRED_FIELDS:
            if field not in ctrl:
                errors.append(
                    _issue(
                        "missing_required_field",
                        f"required field {field!r} is missing in [ctrl]",
                        section="ctrl",
                        field=field,
                    )
                )
        for key in ctrl:
            if key in GEOM_FIELDS:
                errors.append(
                    _issue(
                        "field_in_wrong_section",
                        f"field {key!r} belongs to [geom], not [ctrl]",
                        section="ctrl",
                        field=key,
                    )
                )
    if geom is not None:
        for field in GEOM_REQUIRED_FIELDS:
            if field not in geom:
                errors.append(
                    _issue(
                        "missing_required_field",
                        f"required field {field!r} is missing in [geom]",
                        section="geom",
                        field=field,
                    )
                )
        for key in geom:
            if key in CTRL_FIELDS:
                errors.append(
                    _issue(
                        "field_in_wrong_section",
                        f"field {key!r} belongs to [ctrl], not [geom]",
                        section="geom",
                        field=key,
                    )
                )


def _check_position(
    geom: dict[str, Any],
    errors: list[ValidationIssue],
) -> None:
    value = geom.get("position")
    if not isinstance(value, str):
        errors.append(
            _issue("invalid_type", "position must be a string", section="geom", field="position")
        )
        return
    stripped = value.strip()
    if not stripped:
        errors.append(
            _issue(
                "invalid_position",
                "position must contain at least one line of the form 'Element x y z'",
                section="geom",
                field="position",
            )
        )
        return
    parseable = 0
    for index, raw_line in enumerate(stripped.splitlines(), start=1):
        if not raw_line.strip():
            continue
        tokens = raw_line.split()
        if len(tokens) != 4 or not tokens[0].isalpha():
            errors.append(
                _issue(
                    "invalid_position_line",
                    f"position line {index} must look like 'Element x y z'",
                    section="geom",
                    field="position",
                    line=index,
                )
            )
            continue
        try:
            float(tokens[1])
            float(tokens[2])
            float(tokens[3])
        except ValueError:
            errors.append(
                _issue(
                    "invalid_position_line",
                    f"position line {index} coordinates must be numbers",
                    section="geom",
                    field="position",
                    line=index,
                )
            )
            continue
        parseable += 1
    if parseable == 0:
        errors.append(
            _issue(
                "invalid_position",
                "position must contain at least one line of the form 'Element x y z'",
                section="geom",
                field="position",
            )
        )


def _check_ctrl_values(
    ctrl: dict[str, Any],
    errors: list[ValidationIssue],
    warnings: list[ValidationIssue],
) -> None:
    canonical_xc: str | None = None

    value = ctrl.get("xc")
    if isinstance(value, str) and value.strip():
        canonical_xc = catalogs.normalize_method_name(value)
        if canonical_xc is None:
            errors.append(
                _issue(
                    "unknown_method",
                    f"method {value!r} is not in the REST method catalog",
                    section="ctrl",
                    field="xc",
                )
            )
    elif value is not None:
        errors.append(
            _issue("invalid_type", "xc must be a non-empty string", section="ctrl", field="xc")
        )

    value = ctrl.get("basis_path")
    if value is not None and not (isinstance(value, str) and value.strip()):
        errors.append(
            _issue(
                "invalid_basis_path",
                "basis_path must be a non-empty string",
                section="ctrl",
                field="basis_path",
            )
        )

    value = ctrl.get("print_level")
    if value is not None:
        if isinstance(value, bool) or not isinstance(value, int):
            errors.append(
                _issue("invalid_type", "print_level must be an integer", section="ctrl",
                       field="print_level")
            )
        elif value < 0:
            errors.append(
                _issue("out_of_range", "print_level must be >= 0", section="ctrl",
                       field="print_level")
            )

    value = ctrl.get("num_threads")
    if value is not None:
        if isinstance(value, bool) or not isinstance(value, int):
            errors.append(
                _issue("invalid_type", "num_threads must be an integer", section="ctrl",
                       field="num_threads")
            )
        elif value < 1:
            errors.append(
                _issue("out_of_range", "num_threads must be >= 1", section="ctrl",
                       field="num_threads")
            )

    value = ctrl.get("job_type")
    if value is not None and (not isinstance(value, str) or value not in catalogs.JOB_TYPES):
        errors.append(
            _issue(
                "invalid_job_type",
                f"job_type must be one of {sorted(catalogs.JOB_TYPES)}",
                section="ctrl",
                field="job_type",
            )
        )

    value = ctrl.get("charge")
    if value is not None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(
                _issue("invalid_type", "charge must be a number", section="ctrl", field="charge")
            )
        elif not math.isfinite(value):
            errors.append(
                _issue(
                    "non_finite",
                    "charge must be a finite number",
                    section="ctrl",
                    field="charge",
                )
            )

    value = ctrl.get("spin")
    if value is not None:
        if isinstance(value, bool) or not isinstance(value, int):
            errors.append(
                _issue("invalid_type", "spin must be an integer", section="ctrl", field="spin")
            )
        elif value < 1:
            errors.append(
                _issue("out_of_range", "spin must be >= 1", section="ctrl", field="spin")
            )

    value = ctrl.get("spin_polarization")
    spin = ctrl.get("spin")
    if value is not None:
        if not isinstance(value, bool):
            errors.append(
                _issue(
                    "invalid_type",
                    "spin_polarization must be a boolean",
                    section="ctrl",
                    field="spin_polarization",
                )
            )
        elif isinstance(spin, int) and not isinstance(spin, bool):
            if spin == 1 and value:
                warnings.append(
                    _issue(
                        "singlet_spin_polarization",
                        "spin=1 with spin_polarization=true is unusual; closed-shell "
                        "singlets normally use spin_polarization=false",
                        section="ctrl",
                        field="spin_polarization",
                    )
                )
            if spin > 1 and not value:
                warnings.append(
                    _issue(
                        "rohf_high_spin_limitation",
                        "spin>1 with spin_polarization=false requests a ROHF-style "
                        "high-spin reference; verify this is intended",
                        section="ctrl",
                        field="spin_polarization",
                    )
                )

    value = ctrl.get("empirical_dispersion")
    if value is not None:
        if not isinstance(value, str) or value.lower() not in catalogs.DISPERSION_VALUES:
            errors.append(
                _issue(
                    "invalid_dispersion",
                    f"empirical_dispersion must be one of {sorted(catalogs.DISPERSION_VALUES)}",
                    section="ctrl",
                    field="empirical_dispersion",
                )
            )
        elif canonical_xc in catalogs.NO_DISPERSION_METHODS:
            errors.append(
                _issue(
                    "empirical_dispersion_not_needed",
                    f"method {canonical_xc} is a double-hybrid/RPA method that does "
                    "not need empirical dispersion",
                    section="ctrl",
                    field="empirical_dispersion",
                )
            )

    value = ctrl.get("outputs")
    if value is not None:
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            errors.append(
                _issue(
                    "invalid_type",
                    "outputs must be a list of strings",
                    section="ctrl",
                    field="outputs",
                )
            )
        else:
            for item in value:
                if item not in catalogs.ALLOWED_OUTPUTS:
                    errors.append(
                        _issue(
                            "unknown_output",
                            f"output item {item!r} is not supported by REST",
                            section="ctrl",
                            field="outputs",
                        )
                    )


def _check_geom_values(geom: dict[str, Any], errors: list[ValidationIssue]) -> None:
    value = geom.get("name")
    if value is not None and not (isinstance(value, str) and value.strip()):
        errors.append(
            _issue(
                "invalid_type",
                "name must be a non-empty string",
                section="geom",
                field="name",
            )
        )
    _check_position(geom, errors)


def validate_rest_input(rest_input: str) -> ValidateInputResponse:
    """Independently validate a complete REST TOML input card."""
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []

    try:
        data = tomllib.loads(rest_input)
    except tomllib.TOMLDecodeError as exc:
        errors.append(
            _issue(
                "toml_syntax",
                f"TOML syntax error: {exc}",
                line=_toml_error_line(exc),
            )
        )
        return ValidateInputResponse(valid=False, errors=errors, warnings=[], parsed_sections=[])

    ctrl, geom = _check_sections(data, errors)
    _check_forbidden_keywords(data, ctrl, geom, errors)
    _check_required_and_placement(ctrl, geom, errors)
    _check_unknown_sections_and_keywords(data, ctrl, geom, warnings)
    if ctrl is not None:
        _check_ctrl_values(ctrl, errors, warnings)
    if geom is not None:
        _check_geom_values(geom, errors)

    parsed_sections = [key for key, value in data.items() if isinstance(value, dict)]
    return ValidateInputResponse(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        parsed_sections=parsed_sections,
    )
