"""Reviewed input extensions, pinned to upstream source rather than model claims.

This is an input contract, not a claim that REST has run on this machine.
Unknown fields fail closed when generating a saved card. Add each extension
here with its type, bounds and conditional checks before exposing it to tools.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from typing import Any

UPSTREAM_COMMIT = "6fa7f3b0b6476fa533dfc38af8b8505730713ac6"
UPSTREAM_URL = f"https://gitee.com/restgroup/rest/tree/{UPSTREAM_COMMIT}"
CHECKED_DATE = "2026-10-04"


@dataclass(frozen=True)
class Keyword:
    type: str
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] = ()
    unit: str | None = None


S = Keyword("string")
B = Keyword("boolean")
N = Keyword("number")
POS = Keyword("positive")
NONNEG = Keyword("number", minimum=0)
NONNEG_INT = Keyword("integer", minimum=0)
COUNT = Keyword("integer", minimum=1)
STRINGS = Keyword("strings")


def enum(*values: str) -> Keyword:
    return Keyword("string", choices=values)


# Values here are *extra* settings. Core fields (charge/spin/position/xc...)
# remain explicit confirmed plan fields and cannot be overridden by options.
SECTIONS: dict[str, dict[str, Keyword]] = {
    "ctrl": {
        "max_memory": Keyword("positive", unit="MB per MPI rank"),
        "abort_on_mem_exceed": B,
        "auxbasis_response": B,
        "opt_engine": enum("LBFGS", "geometric-pyo3"),
        "numerical_force": B,
        "nforce_displacement": Keyword("positive", unit="bohr"),
        "max_scf_cycle": COUNT,
        "noiter": B,
        "scf_acc_rho": POS,
        "scf_acc_eev": POS,
        "scf_acc_etot": Keyword("positive", unit="hartree"),
        "mixer": enum("direct", "diis", "linear", "ediis", "ediis+diis", "adiis+diis"),
        "mix_param": Keyword("number", minimum=0, maximum=1),
        "start_diis_cycle": NONNEG_INT,
        "num_max_diis": COUNT,
        "level_shift": Keyword("number", unit="hartree"),
        "ediis_penalty": NONNEG,
        "adiis_penalty": NONNEG,
        "start_check_oscillation": NONNEG_INT,
        "smear": enum("fermi", "gaussian"),
        "smear_sigma": Keyword("positive", unit="hartree"),
        "smear_anneal": B,
        "smear_sigma_min": Keyword("positive", unit="hartree"),
        "initial_guess": enum("sad", "vsap", "hcore"),
        "guess_mix": B,
        "guess_mix_theta_deg": Keyword("number_or_pair"),
        "guessfile": S,
        "chkfile": S,
        "basis_type": enum("Spheric", "Cartesian"),
        "auxbas_path": S,
        "eri_type": enum("analytic", "ri-v"),
        "algorithm_jk": enum("ri-direct", "ri-incore", "ri", "default"),
        "algorithm_j": enum("ri-direct", "ri-incore", "ri", "default", "ri-schwartz"),
        "algorithm_k": enum("ri-direct", "ri-incore", "ri", "default"),
        "use_dm_only": B,
        "grid_generation_level": NONNEG_INT,
        "pruning": enum("nwchem", "sg1", "none"),
        "radial_grid_method": enum("treutler", "gc2nd", "delley", "becke", "mura_knowles", "lmg"),
        "radii_adjust": enum("becke", "treutler"),
        "vxc_screen_threshold": NONNEG,
        "ao_cutoff": NONNEG,
        "non0tab_blksize": NONNEG_INT,
        "drop_dense_ao": B,
        "frozen_core_postscf": Keyword("integer", minimum=0, maximum=99),
        "frequency_points": COUNT,
        "freq_grid_type": Keyword("integer", minimum=0, maximum=2),
        "lambda_points": COUNT,
        "post_ai_correction": enum("SCC15"),
        "post_xc": STRINGS,
        "post_correlation": STRINGS,
        "check_stab": enum("off", "internal", "external", "full", "auto"),
        "solvent_model": enum("CPCM", "COSMO", "IEFPCM", "SS(V)PE", "SMD"),
        "solvent": S,
        "solvent_ri": B,
        "solv_epsilon": POS,
        "solvent_descriptors": Keyword("numbers8"),
        "pcm_cavity_radii": enum("Bondi", "UFF"),
        "solvent_enabled": B,
        "rel": enum("sfx2c"),
        "cube_orb_setting": Keyword("numbers2"),
        "cube_orb_indices": Keyword("orbital_ranges"),
        "cube_orb_type": enum("wavefunction", "density"),
        "analdrv_tasks": Keyword("analdrv_tasks"),
        "pbc_eigenval": S,
    },
    "ctrl.ri_jk": {
        "schwartz_threshold": NONNEG,
        "schwartz_overlap_tol2": NONNEG,
        "pair_screen_threshold": NONNEG,
    },
    "ctrl.ri_pt2": {
        "ss_factor": N,
        "os_factor": N,
        "fp_mode": enum("FP32", "FP64", "TF32"),
        "mpi_mode": NONNEG_INT,
        "streaming": B,
        "new_driver": B,
        "stream_block_size": NONNEG_INT,
        "engine": enum("torch", "cpu"),
        "torch_devices": Keyword("integers"),
        "torch_force_batch_inter": B,
        "torch_batch": NONNEG_INT,
    },
    "geom": {
        "ghost": S,
        "ext_field_dipole": Keyword("numbers3", unit="a.u."),
        "rrs_pbc": B,
        "pbc_dim": Keyword("integer", minimum=1, maximum=3),
        "unit_cell_index": Keyword("integers", unit="zero-based atom indices"),
        "rrs_pbc_vec": Keyword("numbers", unit="same as geom.unit"),
        "max_step": Keyword("integers"),
        "k_points": Keyword("integers"),
    },
    "analdrv": {
        "verbose": NONNEG_INT,
        "cpscf_level_shift": Keyword("number", unit="hartree"),
        "cpscf_tol": POS,
        "cpscf_max_cycle": COUNT,
        "cpscf_max_space": COUNT,
        "cpscf_lindep": POS,
        "cpscf_tol_inflation": POS,
        "grid_level_cpscf": NONNEG_INT,
        "resp_auxbas_path": S,
        "atm_list": Keyword("integers", unit="zero-based atom indices"),
        "grid_level_skeleton": NONNEG_INT,
        "grid_shift_deriv": B,
        "tol_point_group": Keyword("positive", unit="bohr / sqrt(1 + atom count)"),
        "dftd_hess_step": Keyword("positive", unit="bohr"),
        "gau_thermo": B,
        "multipole_orders": Keyword("integers"),
        "multipole_origin": Keyword("numbers3", unit="bohr"),
        "multipole_rdm1_relax": enum("relaxed", "unrelaxed"),
        "multipole_rdm1_dump": B,
    },
    "hessian": {
        "solver": enum("krylov", "dense"),
        "frequencies": B,
        "krylov_max_cycle": COUNT,
        "krylov_tol": POS,
        "krylov_lindep": POS,
        "krylov_tol_inflation": POS,
        "verbose": NONNEG_INT,
        "hessian_matrix_path": S,
        "eigenmodes_path": S,
    },
    "thermo": {
        "temperature": Keyword("scan", unit="K"),
        "pressure": Keyword("scan", unit="atm"),
        "symmetry_number": NONNEG,
        "electronic_energy": Keyword("number", unit="hartree"),
        "sclzpe": POS,
        "sclheat": POS,
        "scls": POS,
        "sclcv": POS,
        "scale_factor": POS,
        "ilowfreq": Keyword("integer", minimum=0, maximum=3),
        "ravib": Keyword("positive", unit="cm^-1"),
        "intpvib": Keyword("positive", unit="cm^-1"),
        "imagreal": Keyword("number", minimum=0, unit="cm^-1"),
        "conc": S,
        "output_path": S,
    },
    "geometric_pyo3": {
        "maxiter": COUNT,
        "convergence_energy": Keyword("positive", unit="hartree"),
        "convergence_grms": Keyword("positive", unit="hartree/bohr"),
        "convergence_gmax": Keyword("positive", unit="hartree/bohr"),
        "convergence_drms": Keyword("positive", unit="angstrom"),
        "convergence_dmax": Keyword("positive", unit="angstrom"),
        "coordsys": enum("tric", "dlc", "hdlc", "cart", "prim", "tric-p"),
        "fac": POS,
        "radii": Keyword("radii"),
        "check": NONNEG_INT,
        "transition": B,
        "irc": B,
        "irc_direction": enum("forward", "backward", "both"),
        "hessian": enum("never", "first", "last", "first+last", "stop", "each"),
        "analytic_hessian": B,
        "use_analdrv": B,
        "frequency": B,
        "thermo": Keyword("numbers2", unit="K, bar"),
        "reset": B,
        "trust": Keyword("positive", unit="angstrom"),
        "tmax": Keyword("positive", unit="angstrom"),
        "tmin": Keyword("positive", unit="angstrom"),
        "epsilon": POS,
        "subfrctor": Keyword("integer", minimum=0, maximum=2),
        "usedmax": B,
        "prefix": S,
        "verbose": NONNEG_INT,
    },
    "tddft": {
        "tddft_method": enum("tda", "lr"),
        "tddft_spin": enum("singlet", "triplet", "both"),
        "nroots": COUNT,
        "tddft_cutoff_energy": Keyword("positive", unit="hartree"),
        "tddft_mode": enum("mo", "ao"),
        "grid_batch": B,
        "tddft_ao_rik_driver": enum("semitrans", "dm", "lowrank"),
        "tddft_fxc_driver": enum("semitrans", "mo", "dm"),
        "tddft_svd_tol": POS,
        "davidson_tol": POS,
        "davidson_max_iter": COUNT,
        "davidson_max_subspace": COUNT,
        "tddft_use_optimized_fxc": B,
        "stability": enum("off", "internal", "external", "full", "auto"),
        "stability_nroots": COUNT,
        "stability_tol": POS,
        "response_tddft": B,
        "response_tddft_solver": enum("pople", "gmres", "klopper", "dense"),
        "response_tddft_tol": POS,
        "response_tddft_max_iter": COUNT,
        "external_field_freq": Keyword("number", minimum=0, unit="hartree"),
        "lifetime_gamma": Keyword("positive", unit="hartree"),
        "tddft_feast_solver": B,
        "tddft_feast_eigenrange_min": Keyword("number", minimum=0, unit="hartree"),
        "tddft_feast_eigenrange_max": Keyword("positive", unit="hartree"),
        "tddft_feast_m_expected": COUNT,
        "tddft_feast_max_iter": COUNT,
        "tddft_feast_tol": POS,
        "tddft_feast_gmres_restart": COUNT,
        "tddft_feast_gmres_max_iter": COUNT,
        "tddft_feast_cg_max_iter": COUNT,
        "tddft_feast_cg_tol": POS,
        "tddft_feast_init_guess_type": enum("random", "gaussian"),
        "tddft_feast_gaussian_width_factor": POS,
        "pysoc": B,
        "tddft_grad_state": NONNEG_INT,
    },
}
for _axis in "xyz":
    SECTIONS["tddft"].update(
        {
            f"response_tddft_{_axis}_start": Keyword("number", unit="bohr"),
            f"response_tddft_{_axis}_end": Keyword("number", unit="bohr"),
            f"response_tddft_{_axis}_points": COUNT,
        }
    )
SECTIONS["ctrl.hessian"] = SECTIONS["hessian"]
SECTIONS["ctrl.thermo"] = SECTIONS["thermo"]

# These aliases are explicitly present in upstream parse_xc/dispersion.rs.
# Bare WB97X resolves through libxc. Never turn WB97X-D into WB97X-D3.
PARSE_XC_METHODS = {
    "wb97x": "wB97X",
    "wb97x-v": "wB97X-V",
    "wb97m-v": "wB97M-V",
    "wb97x-d3": "wB97X-D3",
    "wb97x-d3bj": "wB97X-D3BJ",
    "wb97m-d3bj": "wB97M-D3BJ",
}
NLC_METHODS = frozenset({"wB97X-V", "wB97M-V"})
# The older native module has no reviewed RSH/mGGA derivative path. The
# broader analdrv module is separate and must not be silently selected.
NATIVE_HESSIAN_METHODS = frozenset(
    {
        "HF",
        "SVWN",
        "SVWN-RPA",
        "PZ-LDA",
        "PW-LDA",
        "LDA_X_SLATER",
        "BLYP",
        "PBE",
        "xPBE",
        "XLYP",
        "B3LYP",
        "X3LYP",
        "PBE0",
    }
)


def normalize_xc(value: str, parser: str) -> str | None:
    from aifs.rest.catalogs import normalize_method_name

    if parser == "legacy":
        return normalize_method_name(value)
    if parser == "parse_xc":
        return PARSE_XC_METHODS.get(value.strip().lower())
    return None


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def accepts(spec: Keyword, value: Any) -> bool:
    """Strict JSON/TOML types: booleans are not integers; numbers must be finite."""
    kind = spec.type
    if kind == "string":
        valid = isinstance(value, str) and bool(value.strip())
    elif kind == "boolean":
        valid = isinstance(value, bool)
    elif kind == "integer":
        valid = isinstance(value, int) and not isinstance(value, bool)
    elif kind in {"number", "positive"}:
        valid = _number(value) and (kind != "positive" or value > 0)
    elif kind == "strings":
        valid = isinstance(value, list) and all(isinstance(v, str) and v.strip() for v in value)
    elif kind == "integers":
        valid = isinstance(value, list) and all(accepts(NONNEG_INT, v) for v in value)
    elif kind == "numbers":
        valid = isinstance(value, list) and all(_number(v) for v in value)
    elif kind == "analdrv_tasks":
        valid = (
            isinstance(value, list)
            and bool(value)
            and all(v in {"hessian", "multipole"} for v in value if isinstance(v, str))
            and all(isinstance(v, str) for v in value)
            and len(set(value)) == len(value)
        )
    elif kind.startswith("numbers"):
        valid = (
            isinstance(value, list)
            and len(value) == int(kind[7:])
            and all(_number(v) for v in value)
        )
    elif kind == "number_or_pair":
        valid = _number(value) or accepts(Keyword("numbers2"), value)
    elif kind == "scan":
        valid = (_number(value) and value > 0) or (
            accepts(Keyword("numbers3"), value)
            and value[0] > 0
            and value[1] >= value[0]
            and value[2] > 0
        )
    elif kind == "orbital_ranges":
        valid = isinstance(value, list) and all(
            isinstance(v, list)
            and len(v) == 3
            and all(accepts(NONNEG_INT, x) for x in v)
            and v[1] >= v[0]
            and v[2] in {0, 1}
            for v in value
        )
    elif kind == "radii":
        valid = isinstance(value, dict) and all(
            isinstance(k, str) and k.isalpha() and accepts(NONNEG, v) for k, v in value.items()
        )
    else:
        valid = False
    if not valid:
        return False
    if spec.choices and value not in spec.choices:
        return False
    if spec.minimum is not None and value < spec.minimum:
        return False
    return spec.maximum is None or value <= spec.maximum


def option_errors(options: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for section, values in options.items():
        if section not in SECTIONS:
            errors.append(f"[{section}] is not yet covered by the AIFS extension contract")
            continue
        for field, value in values.items():
            spec = SECTIONS[section].get(field)
            if spec is None:
                errors.append(f"[{section}] {field} is not an allowed extension keyword")
            elif not accepts(spec, value):
                errors.append(f"[{section}] {field} requires {spec.type}; choices={spec.choices}")
    for section in ("hessian", "thermo"):
        if section in options and f"ctrl.{section}" in options:
            errors.append(f"Use only one of [{section}] and [ctrl.{section}]")
    return errors


def semantic_errors(
    ctrl: dict[str, Any], geom: dict[str, Any], options: dict[str, dict[str, Any]]
) -> list[str]:
    """Combinations known to be rejected or not yet verified for card generation."""
    from aifs.rest.catalogs import POST_SCF_METHODS

    errors = option_errors(options)
    if errors:
        return errors
    xc = normalize_xc(str(ctrl.get("xc", "")), str(ctrl.get("xc_parser", "legacy")))
    job = ctrl.get("job_type")
    geo = options.get("geometric_pyo3", {})
    tddft = options.get("tddft", {})
    has_hessian = "hessian" in options or "ctrl.hessian" in options
    has_thermo = "thermo" in options or "ctrl.thermo" in options
    tasks = ctrl.get("analdrv_tasks", [])
    anal_hessian = "hessian" in tasks
    anal = options.get("analdrv", {})
    analytic = has_hessian or anal_hessian or geo.get("analytic_hessian") is True
    if has_thermo and not (has_hessian or anal_hessian):
        errors.append("[thermo] requires an explicit native or analdrv Hessian calculation")
    if has_hessian and anal_hessian:
        errors.append("Use native and analdrv Hessian in separate tasks")
    atoms = len([line for line in str(geom.get("position", "")).splitlines() if line.strip()])
    indices = anal.get("atm_list")
    if indices is not None:
        if not indices or len(set(indices)) != len(indices) or any(v >= atoms for v in indices):
            errors.append("analdrv atm_list requires unique, in-range atom indices")
        if has_thermo and set(indices) != set(range(atoms)):
            errors.append("Thermochemistry requires a Hessian covering all atoms")
    if "analdrv" in options and not tasks and not geo.get("analytic_hessian"):
        errors.append("[analdrv] settings require ctrl.analdrv_tasks or geometric analytic_hessian")
    if tasks and (ctrl.get("spin", 1) > 1 and not ctrl.get("spin_polarization")):
        errors.append("analdrv does not support ROHF references")
    if "multipole" in tasks:
        orders = anal.get("multipole_orders", [1, 2, 3, 4])
        if not orders or any(v < 1 or v > 4 for v in orders):
            errors.append("Multipole orders must be 1 to 4")
        if xc in POST_SCF_METHODS:
            if xc not in {"MP2", "XYG3", "XYGJOS", "XYG7", "xDH-PBE0"}:
                errors.append("Post-SCF multipoles require a reviewed PT2-family method")
            if ctrl.get("spin_polarization"):
                errors.append("Post-SCF multipoles are unavailable for unrestricted references")
            if ctrl.get("frozen_core_postscf", 0) != 0:
                errors.append("Post-SCF multipoles do not support frozen-core settings")
            if ctrl.get("eri_type", "ri-v") != "ri-v":
                errors.append("Post-SCF multipoles require RI integrals")
        if anal.get("multipole_rdm1_dump"):
            errors.append(
                "Multipole density dump requires explicit fchk output; not integrated yet"
            )
    if "geometric_pyo3" in options:
        if job != "opt" or ctrl.get("opt_engine", "geometric-pyo3") != "geometric-pyo3":
            errors.append("[geometric_pyo3] requires job_type=opt and opt_engine=geometric-pyo3")
        if geo.get("transition") or geo.get("irc"):
            if geo.get("hessian") not in {"first", "first+last", "each"}:
                errors.append(
                    "Transition-state / IRC tasks require an explicit initial Hessian "
                    "mode: first, first+last or each"
                )
            if geo.get("transition") and geo.get("irc"):
                errors.append("Split transition-state optimization and IRC into separate tasks")
        if geo.get("trust", 0.1) > geo.get("tmax", 0.3):
            errors.append("geometric_pyo3 trust must not exceed tmax")
        if geo.get("tmin", 1e-4) > geo.get("tmax", 0.3):
            errors.append("geometric_pyo3 tmin must not exceed tmax")
        thermo = geo.get("thermo")
        if isinstance(thermo, list) and any(v <= 0 for v in thermo):
            errors.append("geometric_pyo3 thermo requires positive temperature K and pressure bar")
    position = geom.get("position", "")
    fixed = isinstance(position, str) and any(
        len(line.split()) == 5 and line.split()[1] == "0" for line in position.splitlines()
    )
    if fixed and job == "opt":
        if ctrl.get("opt_engine", "geometric-pyo3") != "geometric-pyo3":
            errors.append("Fixed atoms require opt_engine=geometric-pyo3")
        if geo.get("coordsys", "tric") not in {"tric", "dlc", "hdlc"}:
            errors.append("Fixed atoms require tric/dlc/hdlc coordinates")
    if "tddft" in options:
        if xc in POST_SCF_METHODS:
            errors.append("TDDFT with this post-SCF method is not covered by this contract")
        if ctrl.get("spin_polarization") and "tddft_spin" in tddft:
            errors.append("Unrestricted TDDFT must omit tddft_spin")
        if tddft.get("tddft_spin") in {"triplet", "both"}:
            if tddft.get("tddft_mode", "mo") != "ao":
                errors.append("Triplet/both TDDFT requires tddft_mode=ao")
        if ctrl.get("spin", 1) > 1 and ctrl.get("spin_polarization") is False:
            errors.append("ROHF TDDFT/stability is not covered by this contract")
        if has_hessian or tasks or "geometric_pyo3" in options:
            errors.append("Split TDDFT and geometry/Hessian into separate plan tasks")
        errors.extend(_tddft_errors(ctrl, tddft, xc))
    if analytic:
        if xc in POST_SCF_METHODS:
            errors.append("Analytic Hessian is not available for post-SCF methods at pinned source")
        if has_hessian and (ctrl.get("spin", 1) != 1 or ctrl.get("spin_polarization")):
            errors.append("[hessian] requires a closed-shell reference; select analdrv explicitly")
        if has_hessian and xc not in NATIVE_HESSIAN_METHODS:
            errors.append(
                "Native Hessian method is unverified; use a separately reviewed "
                "analdrv or numerical Hessian path"
            )
        if geo.get("analytic_hessian") and geo.get("use_analdrv", True) is False:
            if xc not in NATIVE_HESSIAN_METHODS or ctrl.get("spin_polarization"):
                errors.append("Legacy geometric analytic Hessian requires reviewed closed-shell XC")
    ghost = geom.get("ghost")
    if isinstance(ghost, str):
        # Upstream ignores unmatched lines. Require its decimal notation so an
        # apparently successful card cannot silently lose a ghost/point charge.
        decimal = r"[+-]?\d+\.\d+"
        patterns = (
            rf"basis\sset\s+[A-Z][a-z]?\s+{decimal}\s+{decimal}\s+{decimal}",
            rf"point\scharge\s+{decimal}\s+{decimal}\s+{decimal}\s+{decimal}",
            rf"potential\s+[\w.\\]+\s+{decimal}\s+{decimal}\s+{decimal}",
        )
        for line in ghost.splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                if not any(re.fullmatch(pattern, line.strip()) for pattern in patterns):
                    errors.append(
                        "Ghost line requires reviewed REST syntax and explicit "
                        "decimal coordinates/charge: " + line
                    )
    if xc in NLC_METHODS:
        if ctrl.get("empirical_dispersion"):
            errors.append("VV10-containing methods must not add empirical dispersion")
        if job in {"force", "opt"} and ctrl.get("numerical_force") is not True:
            errors.append("VV10 derivative path is unverified; require numerical_force=true")
        if analytic or "tddft" in options:
            errors.append("VV10 analytic Hessian/response combinations are not yet verified")
    if str(xc).endswith(("-D3", "-D3BJ")) and ctrl.get("empirical_dispersion"):
        errors.append("Embedded dispersion and empirical_dispersion cannot coexist")
    if ctrl.get("post_ai_correction") and xc != "R-xDH7":
        errors.append("SCC15 requires R-xDH7")
    for field, allowed in (
        ("post_xc", None),
        ("post_correlation", {"PT2", "sBGE2", "RPA", "scsRPA"}),
    ):
        for method in ctrl.get(field, []):
            if (allowed is not None and method not in allowed) or (
                allowed is None and normalize_xc(method, "legacy") is None
            ):
                errors.append(f"Uncovered {field} method: {method}")
    if ctrl.get("smear") and not ctrl.get("smear_sigma"):
        errors.append("Smearing requires a positive smear_sigma in hartree")
    if ctrl.get("smear_anneal") and not ctrl.get("smear"):
        errors.append("Smear annealing requires smear and smear_sigma")
    rij = options.get("ctrl.ri_jk", {})
    if isinstance(rij.get("pair_screen_threshold"), (int, float)):
        if rij.get("pair_screen_threshold", 0) > 0 and (
            analytic
            or bool(tasks)
            or "tddft" in options
            or ctrl.get("numerical_force")
            or job not in {"energy", "force", "opt"}
        ):
            errors.append("AO pair pruning is incompatible with this derivative/response task")
    errors.extend(_rrs_errors(ctrl, geom, atoms))
    return errors


def _tddft_errors(ctrl: dict[str, Any], data: dict[str, Any], xc: str | None) -> list[str]:
    errors: list[str] = []
    unrestricted = ctrl.get("spin_polarization", False)
    response = data.get("response_tddft", False)
    feast = data.get("tddft_feast_solver", False)
    grad = data.get("tddft_grad_state", 0)
    stability = data.get("stability", "off") != "off" or ctrl.get("check_stab", "off") != "off"
    if response and unrestricted:
        errors.append("Frequency-domain response TDDFT requires a restricted reference")
    if feast and unrestricted:
        errors.append("FEAST TDDFT does not support unrestricted references")
    if feast and data.get("tddft_mode", "mo") != "mo":
        errors.append("FEAST TDDFT requires MO mode")
    if unrestricted and data.get("tddft_mode", "mo") == "ao":
        if data.get("tddft_fxc_driver") == "mo":
            errors.append("Unrestricted AO TDDFT fxc driver must be semitrans or dm")
    if response and (feast or grad or data.get("pysoc")):
        errors.append("Response TDDFT skips the eigenvalue run; split FEAST/gradient/PySOC tasks")
    if stability and (response or feast or grad or data.get("pysoc")):
        errors.append("Split stability analysis from excitation/response tasks")
    if feast and data.get("tddft_feast_eigenrange_min", 0) >= data.get(
        "tddft_feast_eigenrange_max", 0.5
    ):
        errors.append("FEAST energy range must have maximum greater than minimum")
    if grad:
        # src/ri_tddft/tddft_grad.rs rejects RSH and non-LDA/GGA kernels.
        if xc not in NATIVE_HESSIAN_METHODS:
            errors.append("TDDFT gradient method requires reviewed HF/LDA/GGA/ordinary hybrid")
        if unrestricted:
            errors.append("TDDFT analytic gradient requires a restricted reference")
        if ctrl.get("job_type") != "force" or ctrl.get("numerical_force"):
            errors.append("TDDFT analytic gradient currently requires an analytic force task")
        if grad > data.get("nroots", 6):
            errors.append("TDDFT gradient state exceeds nroots")
        if data.get("tddft_spin") == "both" or feast:
            errors.append("Gradient with combined spin channels or FEAST is not yet verified")
    if data.get("pysoc") and (unrestricted or data.get("tddft_spin") != "both"):
        errors.append("PySOC export requires restricted tddft_spin=both and AO mode")
    for axis in "xyz":
        if data.get(f"response_tddft_{axis}_start", 0) > data.get(f"response_tddft_{axis}_end", 1):
            errors.append(f"Response grid {axis} end must not precede start")
    return errors


def _rrs_errors(ctrl: dict[str, Any], geom: dict[str, Any], atoms: int) -> list[str]:
    if not geom.get("rrs_pbc"):
        return []
    errors: list[str] = []
    if ctrl.get("spin", 1) != 1 or ctrl.get("spin_polarization"):
        errors.append("RRS-PBC requires a closed-shell reference")
    if ctrl.get("job_type") != "energy":
        errors.append("Prepare RRS-PBC post-SCF analysis as an energy task")
    dimension = geom.get("pbc_dim", 1)
    indices = geom.get("unit_cell_index", [])
    if not indices or len(set(indices)) != len(indices) or any(v >= atoms for v in indices):
        errors.append("RRS-PBC unit_cell_index requires unique, in-range atom indices")
    vectors = geom.get("rrs_pbc_vec", [])
    if len(vectors) != dimension * 3:
        errors.append("RRS-PBC rrs_pbc_vec requires 3 numbers per periodic dimension")
    elif any(not any(vectors[i : i + 3]) for i in range(0, len(vectors), 3)):
        errors.append("RRS-PBC lattice vectors must be nonzero")
    for field in ("max_step", "k_points"):
        values = geom.get(field, [])
        if len(values) != dimension:
            errors.append(f"RRS-PBC {field} length must equal pbc_dim")
        if field == "k_points" and any(v <= 0 for v in values):
            errors.append("RRS-PBC k_points entries must be positive")
    # The pinned 3D branch uses interval counts instead of point counts to
    # decode its flat index. Do not certify that unreviewed sampling branch.
    if dimension == 3:
        errors.append("3D RRS-PBC sampling is not verified at the pinned source")
    return errors


def capability_view(section: str | None = None) -> dict[str, Any]:
    """Small overview by default; fetch one field schema instead of dumping all."""
    from aifs.rest.catalogs import ALL_METHODS, JOB_TYPES

    result: dict[str, Any] = {
        "source_commit": UPSTREAM_COMMIT,
        "source_url": UPSTREAM_URL,
        "checked_date": CHECKED_DATE,
        "validation_scope": "AIFS input checks; REST not executed",
        "job_types": sorted(JOB_TYPES),
        "methods": {"legacy": sorted(ALL_METHODS), "parse_xc": sorted(PARSE_XC_METHODS.values())},
        "sections": list(SECTIONS),
        "pending": [
            "arbitrary parse_xc expressions and additional LibXC names",
            "MD/AIMD/QM-MM/pure-MM",
            "GW/BSE",
            "3D RRS-PBC sampling",
            "post-SCF multipole density export",
            "TDDFT excited-state optimization and RSH/mGGA/FEAST/combined-spin gradients",
        ],
        "notes": [
            "Extension options cannot override confirmed core fields",
            "Native thermo pressure is atm; geometric_pyo3 thermo pressure is bar",
            "Convergence keys are convergence_*, as read by upstream source",
            "analdrv_tasks selects hessian/multipole; multipole_origin is always bohr",
            "RRS-PBC is finite-cluster post-SCF reconstruction, not periodic SCF",
            "VV10 energies are wired in pinned source; derivative/response combinations "
            "need separate verification",
        ],
    }
    if section is not None:
        if section not in SECTIONS:
            raise ValueError(f"Unknown AIFS extension section: {section}")
        result["keywords"] = {key: asdict(spec) for key, spec in SECTIONS[section].items()}
    return result
