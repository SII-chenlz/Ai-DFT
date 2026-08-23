"""Render DFT input cards from a concrete DftJobSpec."""

from __future__ import annotations

from pathlib import Path

from functional_advisor.models import DftJobSpec


def render_inputs(spec: DftJobSpec) -> dict[str, str]:
    """Return a mapping of filename -> file content for the target DFT code."""
    if spec.code == "vasp":
        return render_vasp(spec)
    if spec.code == "qe":
        return render_qe(spec)
    raise ValueError(f"Unsupported DFT code: {spec.code}")


def render_vasp(spec: DftJobSpec) -> dict[str, str]:
    lines = [
        f"SYSTEM = {_sanitize(spec.system_name)}",
        f"# recommended functional: {spec.functional}"
        + (f" + {spec.dispersion}" if spec.dispersion else ""),
    ]
    for key, value in spec.parameters.items():
        if key.startswith("_"):
            continue
        lines.append(f"{key} = {_format_value(value)}")

    if spec.hubbard_u:
        lines.extend(
            [
                "LDAU = .TRUE.",
                "LDAUTYPE = 2",
                "LDAUPRINT = 1",
                "# LDAUL/LDAUU/LDAUJ below must be expanded per atomic species.",
            ]
        )
        for species, u_value in spec.hubbard_u.items():
            lines.append(f"# {species}: U = {u_value:.2f} eV")

    if spec.dispersion and "IVDW" not in spec.parameters:
        lines.append("IVDW = 11")
    if spec.spin_polarized and "ISPIN" not in spec.parameters:
        lines.append("ISPIN = 2")
    if spec.charged or any(k == "_charge_note" for k in spec.parameters):
        lines.append("# Charged cell: set NELECT = total_valence_electrons - net_charge after POTCAR.")

    incar = "\n".join(lines) + "\n"

    kpoints = """# Automatic k-mesh; adjust according to cell shape.
# Gamma-centered 3x3x3 is a conservative generic start.
0
Gamma
3 3 3
0 0 0
"""

    poscar = _render_poscar(spec)

    potcar = _render_potcar_placeholder(spec)

    run_script = """#!/usr/bin/env bash
# VASP run template. Set VASP_EXE and copy a real POTCAR first.
set -euo pipefail
VASP_EXE=${VASP_EXE:-vasp_std}
mpirun -np "${NP:-4}" "${VASP_EXE}"
"""

    return {
        "INCAR": incar,
        "KPOINTS": kpoints,
        "POSCAR": poscar,
        "POTCAR.placeholder": potcar,
        "run_vasp.sh": run_script,
    }


def render_qe(spec: DftJobSpec) -> dict[str, str]:
    calculation = "relax" if "geometry optimization" in spec.task else "scf"
    if "band structure" in spec.task:
        calculation = "bands"

    input_dft = _qe_input_dft(spec)
    lines = [
        "&CONTROL",
        f"    calculation = '{calculation}'",
        "    prefix = 'system'",
        "    pseudo_dir = './pseudo'",
        "    outdir = './tmp'",
        "    verbosity = 'high'",
        " /",
        "&SYSTEM",
        "    ibrav = 0",
        "    nat = 0",
        "    ntyp = 0",
        f"    ecutwfc = {spec.parameters.get('ecutwfc', 60)}",
        f"    ecutrho = {spec.parameters.get('ecutrho', 480)}",
    ]
    if input_dft:
        lines.append(f"    input_dft = '{input_dft}'")
    if spec.spin_polarized:
        lines.append("    nspin = 2")
        lines.append("    starting_magnetization(1) = 0.5")
    if spec.charged or spec.charge != 0:
        lines.append(f"    tot_charge = {spec.charge}")
    if spec.hubbard_u:
        lines.append("    lda_plus_u = .true.")
        lines.append("    lda_plus_u_kind = 1")
        lines.append(f"    Hubbard_U(1) = {next(iter(spec.hubbard_u.values()))}")
    lines.extend(
        [
            "    occupations = 'smearing'",
            "    smearing = 'gaussian'",
            "    degauss = 0.01",
            " /",
            "&ELECTRONS",
            f"    conv_thr = {spec.parameters.get('conv_thr', 1e-08)}",
            f"    mixing_beta = {spec.parameters.get('mixing_beta', 0.3)}",
            f"    electron_maxstep = {spec.parameters.get('electron_maxstep', 200)}",
            " /",
            "ATOMIC_SPECIES",
            "# element  mass  pseudopotential_file",
            "ATOMIC_POSITIONS crystal",
            "# element x y z",
            "K_POINTS automatic",
            "3 3 3 0 0 0",
        ]
    )

    qe_input = "\n".join(lines) + "\n"
    return {"pw.x.in": qe_input, "README.pseudo": "# Put pseudopotentials in ./pseudo and update ATOMIC_SPECIES.\n"}


def _render_poscar(spec: DftJobSpec) -> str:
    if spec.structure_file:
        path = Path(spec.structure_file)
        if path.exists():
            content = path.read_text(encoding="utf-8")
            if content.strip():
                return content
    return f"""{spec.system_name}
1.0
# Provide cell vectors here:
8.0 0.0 0.0
0.0 8.0 0.0
0.0 0.0 8.0
# Provide element symbols here, then coordinates below.
"""


def _render_potcar_placeholder(spec: DftJobSpec) -> str:
    lines = [
        "# POTCAR is code-distribution-protected and cannot be generated.",
        "# Concatenate PAW datasets in the same order as POSCAR species.",
        f"# Recommended PAW flavour: standard/standard_* compatible with {spec.functional}.",
        "# Example: cat potpaw_PBE/Fe/POTCAR potpaw_PBE/O/POTCAR > POTCAR",
    ]
    if spec.hubbard_u:
        lines.append("# For +U runs use PAW datasets that include the required valence states.")
    return "\n".join(lines) + "\n"


def _qe_input_dft(spec: DftJobSpec) -> str:
    functional = spec.functional.lower()
    if "hse" in functional:
        return "hse"
    if "pbesol" in functional:
        return "pbesol"
    if "scan" in functional:
        return "scan"
    return "pbe"


def _sanitize(value: str) -> str:
    return value.replace("\n", " ").replace("=", " ").strip()


def _format_value(value: object) -> str:
    if isinstance(value, bool):
        return ".TRUE." if value else ".FALSE."
    if isinstance(value, str):
        return value
    return str(value)
