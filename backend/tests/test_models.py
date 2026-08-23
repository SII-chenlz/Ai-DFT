"""Tests for the Pydantic domain models in aifs.models."""

from collections.abc import Callable

import pytest
from pydantic import ValidationError

from aifs.models import RestInputRequest, ValidateInputRequest


def test_valid_request_roundtrip(make_request: Callable[..., RestInputRequest]) -> None:
    request = make_request()
    assert request.xc == "B3LYP"
    assert request.spin == 1
    assert request.num_threads == 10
    assert request.print_level == 1
    assert request.charge == 0.0


def test_extra_fields_rejected(make_request: Callable[..., RestInputRequest]) -> None:
    with pytest.raises(ValidationError):
        make_request(not_a_rest_keyword="boom")


def test_spin_zero_rejected(make_request: Callable[..., RestInputRequest]) -> None:
    with pytest.raises(ValidationError):
        make_request(spin=0)


def test_spin_negative_rejected(make_request: Callable[..., RestInputRequest]) -> None:
    with pytest.raises(ValidationError):
        make_request(spin=-3)


def test_num_threads_zero_rejected(make_request: Callable[..., RestInputRequest]) -> None:
    with pytest.raises(ValidationError):
        make_request(num_threads=0)


def test_print_level_negative_rejected(make_request: Callable[..., RestInputRequest]) -> None:
    with pytest.raises(ValidationError):
        make_request(print_level=-1)


def test_blank_position_rejected(make_request: Callable[..., RestInputRequest]) -> None:
    with pytest.raises(ValidationError):
        make_request(position="  \n\t ")


def test_blank_system_name_rejected(make_request: Callable[..., RestInputRequest]) -> None:
    with pytest.raises(ValidationError):
        make_request(system_name="   ")


def test_system_name_too_long_rejected(make_request: Callable[..., RestInputRequest]) -> None:
    with pytest.raises(ValidationError):
        make_request(system_name="x" * 121)


def test_system_name_max_length_accepted(make_request: Callable[..., RestInputRequest]) -> None:
    request = make_request(system_name="x" * 120)
    assert len(request.system_name) == 120


def test_blank_basis_set_pool_rejected(make_request: Callable[..., RestInputRequest]) -> None:
    with pytest.raises(ValidationError):
        make_request(basis_set_pool="   ")


def test_unknown_xc_rejected(make_request: Callable[..., RestInputRequest]) -> None:
    with pytest.raises(ValidationError):
        make_request(xc="PBE99")


def test_invalid_job_type_rejected(make_request: Callable[..., RestInputRequest]) -> None:
    with pytest.raises(ValidationError):
        make_request(job_type="freq")


def test_invalid_empirical_dispersion_rejected(
    make_request: Callable[..., RestInputRequest],
) -> None:
    with pytest.raises(ValidationError):
        make_request(empirical_dispersion="d3b")


def test_invalid_output_item_rejected(make_request: Callable[..., RestInputRequest]) -> None:
    with pytest.raises(ValidationError):
        make_request(outputs=["spectra"])


def test_rest_supported_outputs_accepted(make_request: Callable[..., RestInputRequest]) -> None:
    request = make_request(outputs=["dipole", "fchk", "cube_orb", "molden"])
    assert request.outputs == ["dipole", "fchk", "cube_orb", "molden"]


def test_nonfinite_charge_rejected(make_request: Callable[..., RestInputRequest]) -> None:
    with pytest.raises(ValidationError):
        make_request(charge=float("nan"))


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("b3lyp", "B3LYP"),
        ("B3LYP", "B3LYP"),
        ("hf", "HF"),
        ("xpbe", "xPBE"),
        ("m06-2x", "M06-2X"),
        ("xdh-pbe0", "xDH-PBE0"),
        ("rpa@pbe", "RPA@PBE"),
        ("sbge2", "sBGE2"),
        ("xygjos", "XYGJOS"),
        ("scsrpa", "scsRPA"),
    ],
)
def test_xc_case_normalized(
    make_request: Callable[..., RestInputRequest], raw: str, canonical: str
) -> None:
    request = make_request(xc=raw)
    assert request.xc == canonical


def test_empty_basis_becomes_none(make_request: Callable[..., RestInputRequest]) -> None:
    request = make_request(basis="   ")
    assert request.basis is None


def test_strings_are_stripped(make_request: Callable[..., RestInputRequest]) -> None:
    request = make_request(system_name="  water  ", basis_set_pool="  /pool  ")
    assert request.system_name == "water"
    assert request.basis_set_pool == "/pool"


def test_validate_input_request_rejects_empty_rest_input() -> None:
    with pytest.raises(ValidationError):
        ValidateInputRequest(rest_input="   ")


def test_validate_input_request_rejects_oversized_rest_input() -> None:
    with pytest.raises(ValidationError):
        ValidateInputRequest(rest_input="x" * 500_001)


def test_validate_input_request_accepts_max_size() -> None:
    request = ValidateInputRequest(rest_input="x" * 500_000)
    assert len(request.rest_input) == 500_000
