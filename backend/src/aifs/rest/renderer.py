"""Render structured requests into REST TOML input cards.

The renderer only emits values from validated model fields and catalog
entries; it never accepts or concatenates arbitrary user-provided TOML
key/value fragments. Field order is fixed so snapshot-style assertions stay
reliable.
"""

from __future__ import annotations

from pathlib import Path

from aifs.models import DomainValidationError, RestInputRequest, RestInputResponse
from aifs.rest.catalogs import NO_DISPERSION_METHODS, default_basis, method_category


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

    basis = request.basis
    if basis is None:
        basis = default_basis(category)
        defaults_applied.append(f"basis={basis}")

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

    basis_path = str(Path(request.basis_set_pool) / basis)

    lines: list[str] = ["[ctrl]"]
    lines.append(f"xc = {_escape_toml_string(request.xc, multiline=False)}")
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
    lines.append("")
    lines.append("[geom]")
    lines.append(f"name = {_escape_toml_string(request.system_name, multiline=False)}")
    lines.append("position = " + _escape_toml_string(request.position, multiline=True))
    rest_input = "\n".join(lines) + "\n"

    effective_settings: dict[str, object] = {
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
    }

    return RestInputResponse(
        rest_input=rest_input,
        effective_settings=effective_settings,
        defaults_applied=defaults_applied,
        warnings=[],
    )
