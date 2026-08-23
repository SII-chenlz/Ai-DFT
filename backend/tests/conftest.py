"""Shared fixtures for the AIFS backend test suite."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest

from aifs.config import get_settings
from aifs.models import RestInputRequest

#: Value of AIFS_BASIS_SET_POOL injected into the process environment for
#: every test, so the suite never depends on the developer's deployment.
TEST_BASIS_SET_POOL = "/data/rest/basis_sets"

VALID_REQUEST_KWARGS: dict[str, Any] = {
    "system_name": "water",
    "position": "O 0.0 0.0 0.0\nH 0.757 0.586 0.0\nH -0.757 0.586 0.0",
    "job_type": "energy",
    "xc": "B3LYP",
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


@pytest.fixture(autouse=True)
def _pool_configured(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point AIFS_BASIS_SET_POOL at a stable test path for every test."""
    monkeypatch.setenv("AIFS_BASIS_SET_POOL", TEST_BASIS_SET_POOL)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def make_request() -> Callable[..., RestInputRequest]:
    """Build a valid RestInputRequest, allowing any field to be overridden."""

    def _make(**overrides: Any) -> RestInputRequest:
        kwargs = dict(VALID_REQUEST_KWARGS)
        kwargs.update(overrides)
        return RestInputRequest(**kwargs)

    return _make


@pytest.fixture
def request_payload() -> dict[str, Any]:
    """A valid JSON payload for POST /v1/rest-inputs."""
    return dict(VALID_REQUEST_KWARGS)


@pytest.fixture
def valid_card() -> str:
    """A renderer-independent REST card accepted by the validator."""
    return VALID_CARD
