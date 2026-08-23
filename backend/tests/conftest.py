"""Shared fixtures for the AIFS backend test suite."""

from collections.abc import Callable
from typing import Any

import pytest

from aifs.models import RestInputRequest

VALID_REQUEST_KWARGS: dict[str, Any] = {
    "system_name": "water",
    "position": "O 0.0 0.0 0.0\nH 0.757 0.586 0.0\nH -0.757 0.586 0.0",
    "job_type": "energy",
    "xc": "B3LYP",
    "basis_set_pool": "/data/rest/basis_sets",
}

# A minimal, renderer-independent REST card that every rule in the validator
# accepts. Built as a plain string so validator tests do not depend on the
# renderer implementation.
VALID_CARD = """\
[ctrl]
xc = "PBE"
basis_path = "/pool/def2-TZVPP"
print_level = 1
num_threads = 10
job_type = "energy"
charge = 0.0
spin = 1
spin_polarization = false

[geom]
name = "water"
position = \"\"\"
O 0.0 0.0 0.0
H 0.0 0.0 1.0
\"\"\"
"""


@pytest.fixture
def make_request() -> Callable[..., RestInputRequest]:
    """Build a valid RestInputRequest, allowing any field to be overridden."""

    def _make(**overrides: Any) -> RestInputRequest:
        kwargs = dict(VALID_REQUEST_KWARGS)
        kwargs.update(overrides)
        return RestInputRequest(**kwargs)

    return _make
