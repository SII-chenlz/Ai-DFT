"""Versioned REST keyword catalogs.

Baseline entries come from the official REST README:

    https://gitee.com/restgroup/rest/blob/master/README.md

read on 2026-10-04. Added methods are checked against the source dispatch
at the commit recorded in capabilities.py.
The catalogs are plain in-process data: runtime error
messages never depend on the network.
"""

from __future__ import annotations

SOURCE_URL = "https://gitee.com/restgroup/rest/blob/master/README.md"
SOURCE_READ_DATE = "2026-10-04"

# Geometry keyword checked separately from the older method catalog.
# REST README, [geom] section, read 2026-10-03. Never rely on an omitted unit.
GEOMETRY_UNITS = frozenset({"angstrom", "bohr"})
GEOMETRY_SOURCE_READ_DATE = "2026-10-03"

# Self-consistent-field methods. Default basis set: def2-TZVPP.
SCF_METHODS: frozenset[str] = frozenset(
    {
        "HF",
        # LDA is a family, not a recognized name in the pinned legacy parser.
        "SVWN",
        "SVWN-RPA",
        "PZ-LDA",
        "PW-LDA",
        "LDA_X_SLATER",
        "BLYP",
        "PBE",
        "xPBE",
        "XLYP",
        "SCAN",
        "M06-L",
        "MN15-L",
        "TPSS",
        "B3LYP",
        "X3LYP",
        "PBE0",
        "M05",
        "M05-2X",
        "M06",
        "M06-2X",
        "SCAN0",
        "MN15",
        # Additional legacy dispatch in src/dft/libxc_helper.rs at pinned commit.
        "wB97X",
        "CAM-B3LYP",
        "LC-BLYP",
        "LC-wPBE",
        "HSE06",
        "HSE03",
        "r2SCAN",
        "revSCAN",
        "TPSSh",
    }
)

# Post-SCF methods. Default basis set: def2-QZVPP.
POST_SCF_METHODS: frozenset[str] = frozenset(
    {
        "MP2",
        "XYG3",
        "XYGJOS",
        "XYG7",
        "xDH-PBE0",
        "sBGE2",
        "ZRPS",
        "scsRPA",
        "R-xDH7",
        "RPA@PBE",
        "RPA@B3LYP",
    }
)

ALL_METHODS: frozenset[str] = SCF_METHODS | POST_SCF_METHODS

# The REST README states that XYG3-type double hybrids and RPA methods
# (XYG3, XYG7, XYGJOS, scsRPA, R-xDH7, RPA, ...) do not need empirical
# dispersion. Requesting empirical_dispersion for them is a domain error and
# is never silently dropped.
NO_DISPERSION_METHODS: frozenset[str] = frozenset(POST_SCF_METHODS - {"MP2"})

DEFAULT_BASIS_BY_CATEGORY: dict[str, str] = {
    "scf": "def2-TZVPP",
    "post_scf": "def2-QZVPP",
}

# Empirical dispersion corrections supported by REST.
DISPERSION_VALUES: frozenset[str] = frozenset({"d3", "d3bj", "d4"})

# Canonical REST job types (the API accepts exactly these, no aliases).
JOB_TYPES: frozenset[str] = frozenset({"energy", "opt", "force", "numerical dipole"})

# REST-supported output items (the API allows this subset).
ALLOWED_OUTPUTS: frozenset[str] = frozenset(
    {
        "dipole",
        "fchk",
        "cube_orb",
        "molden",
        "geometry",
        "force",
        "force_for_ghost_point_charges",
    }
)

_METHOD_LOOKUP: dict[str, str] = {name.lower(): name for name in ALL_METHODS}


def normalize_method_name(value: str) -> str | None:
    """Return the canonical method name for any casing, or None if unknown."""
    return _METHOD_LOOKUP.get(value.strip().lower())


def method_category(name: str) -> str:
    """Return "scf" or "post_scf" for a canonical method name."""
    return "post_scf" if name in POST_SCF_METHODS else "scf"


def default_basis(category: str) -> str:
    """Return the default basis set for a method category."""
    return DEFAULT_BASIS_BY_CATEGORY[category]
