"""Versioned REST keyword catalogs.

Every entry below is derived from the official REST README:

    https://gitee.com/restgroup/rest/blob/master/README.md

read on 2026-08-23. The catalogs are plain in-process data: runtime error
messages never depend on the network.
"""

from __future__ import annotations

SOURCE_URL = "https://gitee.com/restgroup/rest/blob/master/README.md"
SOURCE_READ_DATE = "2026-08-23"

# Self-consistent-field methods. Default basis set: def2-TZVPP.
SCF_METHODS: frozenset[str] = frozenset(
    {
        "HF",
        "LDA",
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
    if name in SCF_METHODS:
        return "scf"
    return "post_scf"


def default_basis(category: str) -> str:
    """Return the default basis set for a method category."""
    return DEFAULT_BASIS_BY_CATEGORY[category]
