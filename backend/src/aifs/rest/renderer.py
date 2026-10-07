"""Render structured requests into REST TOML input cards.

The renderer only emits values from validated model fields and catalog
entries; it never accepts or concatenates arbitrary user-provided TOML
key/value fragments. The basis pool root comes from deployment settings
(``require_basis_set_pool``), and basis names are checked so they cannot
escape that root. Field order is fixed so snapshot-style assertions stay
reliable.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from aifs.config import require_basis_set_pool
from aifs.models import DomainValidationError, RestInputRequest, RestInputResponse
from aifs.rest.capabilities import CHECKED_DATE, UPSTREAM_COMMIT
from aifs.rest.catalogs import NO_DISPERSION_METHODS, default_basis, method_category

#: Windows drive-letter prefixes; rejected because joining them to a POSIX
#: pool root would silently produce an unrelated absolute path on Windows.
_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:[\\/]")


def _check_basis_name(basis: str) -> None:
    """Reject basis names that could escape the configured pool root.

    ``Path(pool) / basis`` discards the pool when ``basis`` is absolute, and
    ``..`` segments walk out of the pool directory; both would let a caller
    point the card at an arbitrary filesystem location. Relative subpaths
    inside the pool (e.g. ``aux/def2-SVP``) remain allowed.
    """
    parts = [part for part in re.split(r"[\\/]", basis) if part]
    escapes = (
        _DRIVE_PREFIX.match(basis) is not None
        or Path(basis).is_absolute()
        or any(part in (".", "..") for part in parts)
    )
    if escapes:
        raise DomainValidationError(
            code="basis_outside_pool",
            message=(
                "basis must stay inside the configured basis_set_pool: absolute "
                "paths, drive letters and '.'/'..' segments are rejected; "
                f"got {basis!r}"
            ),
        )


def _escape_toml_string(value: str, *, multiline: bool) -> str:
    """Escape ``value`` for a TOML basic string (or multi-line basic string)."""
    parts: list[str] = []
    for char in value:
        if char == "\\":
            parts.append("\\\\")
        elif char == '"':
            parts.append('\\"')
        elif char == "\n":
            parts.append("\n" if multiline else "\\n")
        elif char == "\t":
            parts.append("\\t")
        elif char == "\r":
            parts.append("\\r")
        elif ord(char) < 0x20 or ord(char) == 0x7F:
            parts.append(f"\\u{ord(char):04x}")
        else:
            parts.append(char)
    if multiline:
        return '"""\n' + "".join(parts) + '"""'
    return '"' + "".join(parts) + '"'


def render_rest_input(request: RestInputRequest) -> RestInputResponse:
    """Render a validated request into a REST TOML input card."""
    category = method_category(request.xc)
    defaults_applied: list[str] = []
    warnings: list[str] = []
    if "position_unit" not in request.model_fields_set:
        defaults_applied.append("position_unit=angstrom")
        warnings.append(
            "Coordinate unit was omitted; AIFS explicitly uses angstrom. "
            "Confirm the source coordinates use angstrom before running REST."
        )

    basis = request.basis
    if basis is None:
        basis = default_basis(category)
        defaults_applied.append(f"basis={basis}")
    _check_basis_name(basis)

    if request.empirical_dispersion is not None and request.xc in NO_DISPERSION_METHODS:
        raise DomainValidationError(
            code="empirical_dispersion_not_needed",
            message=(
                f"method {request.xc} is a double-hybrid/RPA method that does not "
                "need empirical dispersion; omit empirical_dispersion"
            ),
        )

    spin_polarization = request.spin_polarization
    if spin_polarization is None:
        spin_polarization = request.spin > 1
        defaults_applied.append(f"spin_polarization={str(spin_polarization).lower()}")

    basis_path = str(Path(require_basis_set_pool()) / basis)

    lines: list[str] = ["[ctrl]"]
    lines.append(f"xc = {_escape_toml_string(request.xc, multiline=False)}")
    if request.xc_parser != "legacy":
        lines.append(f"xc_parser = {_escape_toml_string(request.xc_parser, multiline=False)}")
    lines.append(f"basis_path = {_escape_toml_string(basis_path, multiline=False)}")
    lines.append(f"print_level = {request.print_level}")
    lines.append(f"num_threads = {request.num_threads}")
    lines.append(f"job_type = {_escape_toml_string(request.job_type, multiline=False)}")
    lines.append(f"charge = {request.charge}")
    lines.append(f"spin = {request.spin}")
    lines.append(f"spin_polarization = {str(spin_polarization).lower()}")
    if request.empirical_dispersion is not None:
        lines.append(
            "empirical_dispersion = "
            + _escape_toml_string(request.empirical_dispersion, multiline=False)
        )
    if request.outputs:
        rendered_outputs = ", ".join(
            _escape_toml_string(item, multiline=False) for item in request.outputs
        )
        lines.append(f"outputs = [{rendered_outputs}]")
    _append_options(lines, request.rest_options.get("ctrl", {}))
    lines.append("")
    lines.append("[geom]")
    lines.append(f"name = {_escape_toml_string(request.system_name, multiline=False)}")
    lines.append(f"unit = {_escape_toml_string(request.position_unit, multiline=False)}")
    lines.append("position = " + _escape_toml_string(request.position, multiline=True))
    _append_options(lines, request.rest_options.get("geom", {}))
    for section, fields in sorted(request.rest_options.items()):
        if section not in {"ctrl", "geom"}:
            lines.extend(["", f"[{section}]"])
            _append_options(lines, fields)
    rest_input = "\n".join(lines) + "\n"
    # Independent checks apply to every extension, including direct API calls.
    if request.rest_options or request.xc_parser != "legacy":
        from aifs.rest.validator import validate_rest_input

        validation = validate_rest_input(rest_input)
        if not validation.valid:
            raise DomainValidationError(
                "invalid_rest_options", "; ".join(issue.message for issue in validation.errors)
            )
        warnings.extend(issue.message for issue in validation.warnings)

    effective_settings: dict[str, object] = {
        "position_unit": request.position_unit,
        "xc": request.xc,
        "basis": basis,
        "basis_path": basis_path,
        "job_type": request.job_type,
        "charge": request.charge,
        "spin": request.spin,
        "spin_polarization": spin_polarization,
        "print_level": request.print_level,
        "num_threads": request.num_threads,
        "empirical_dispersion": request.empirical_dispersion,
        "outputs": request.outputs,
        "xc_parser": request.xc_parser,
        "rest_options": request.rest_options,
        "rest_source_commit": UPSTREAM_COMMIT,
        "rest_source_checked_date": CHECKED_DATE,
        "validation_scope": "AIFS input checks; REST not executed",
    }

    return RestInputResponse(
        rest_input=rest_input,
        effective_settings=effective_settings,
        defaults_applied=defaults_applied,
        warnings=warnings,
    )


def _toml_value(value: object) -> str:
    if isinstance(value, str):
        return _escape_toml_string(value, multiline="\n" in value)
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return (
            "{ "
            + ", ".join(
                f"{json.dumps(key)} = {_toml_value(item)}" for key, item in sorted(value.items())
            )
            + " }"
        )
    raise DomainValidationError("invalid_rest_value", "REST options must contain TOML values")


def _append_options(lines: list[str], fields: dict[str, object]) -> None:
    for field, value in sorted(fields.items()):
        lines.append(f"{field} = {_toml_value(value)}")
