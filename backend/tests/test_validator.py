"""Tests for the independent REST TOML validator in aifs.rest.validator.

Cards under test are built from the renderer-independent ``valid_card``
fixture, so validator behavior never depends on the renderer implementation.
"""

from collections.abc import Callable

from aifs.models import RestInputRequest
from aifs.rest.renderer import render_rest_input
from aifs.rest.validator import validate_rest_input


def test_accepts_renderer_output(make_request: Callable[..., RestInputRequest]) -> None:
    card = render_rest_input(make_request()).rest_input
    result = validate_rest_input(card)
    assert result.valid is True
    assert result.errors == []
    assert result.warnings == []
    assert result.parsed_sections == ["ctrl", "geom"]


def test_accepts_minimal_valid_card(valid_card: str) -> None:
    result = validate_rest_input(valid_card)
    assert result.valid is True


def test_missing_ctrl_section_rejected(valid_card: str) -> None:
    card = valid_card.replace("[ctrl]", "[other]")
    result = validate_rest_input(card)
    assert result.valid is False
    assert [e.code for e in result.errors] == ["missing_section"]


def test_missing_geom_section_rejected(valid_card: str) -> None:
    card = valid_card.replace("[geom]", "[other]")
    result = validate_rest_input(card)
    assert result.valid is False
    assert any(e.code == "missing_section" for e in result.errors)


def test_forged_keyword_method_rejected(valid_card: str) -> None:
    card = valid_card.replace('xc = "PBE"', 'method = "PBE"')
    result = validate_rest_input(card)
    assert any(
        e.code == "forbidden_keyword" and e.field == "method" for e in result.errors
    )


def test_forged_keyword_coord_rejected(valid_card: str) -> None:
    card = valid_card.replace('name = "water"', 'coord = "O 0 0 0"')
    result = validate_rest_input(card)
    assert any(
        e.code == "forbidden_keyword" and e.field == "coord" for e in result.errors
    )


def test_forged_keyword_molecule_rejected(valid_card: str) -> None:
    card = valid_card.replace('job_type = "energy"', 'molecule = "water"')
    result = validate_rest_input(card)
    assert any(
        e.code == "forbidden_keyword" and e.field == "molecule" for e in result.errors
    )


def test_spin_in_geom_rejected(valid_card: str) -> None:
    card = valid_card + "\n[geom.spin]\nvalue = 1\n"
    result = validate_rest_input(card)
    assert any(
        e.code == "field_in_wrong_section" and e.field == "spin" for e in result.errors
    )


def test_charge_in_geom_rejected(valid_card: str) -> None:
    card = valid_card.replace('name = "water"', 'name = "water"\ncharge = 0.0')
    result = validate_rest_input(card)
    assert any(
        e.code == "field_in_wrong_section" and e.field == "charge"
        for e in result.errors
    )


def test_spin_polarization_in_geom_rejected(valid_card: str) -> None:
    card = valid_card.replace(
        'name = "water"', 'name = "water"\nspin_polarization = true'
    )
    result = validate_rest_input(card)
    assert any(
        e.code == "field_in_wrong_section" and e.field == "spin_polarization"
        for e in result.errors
    )


def test_position_in_ctrl_rejected(valid_card: str) -> None:
    card = valid_card.replace("spin_polarization = false", 'position = "O 0 0 0"')
    result = validate_rest_input(card)
    assert any(
        e.code == "field_in_wrong_section" and e.field == "position"
        for e in result.errors
    )


def test_toml_syntax_error_returns_only_syntax_issue() -> None:
    result = validate_rest_input("ctrl = = = not toml")
    assert result.valid is False
    assert len(result.errors) == 1
    assert result.errors[0].code == "toml_syntax"
    assert result.errors[0].line == 1
    assert result.parsed_sections == []


def test_unknown_xc_rejected(valid_card: str) -> None:
    card = valid_card.replace('xc = "PBE"', 'xc = "PBE99"')
    result = validate_rest_input(card)
    assert any(e.code == "unknown_method" for e in result.errors)


def test_xc_case_insensitive_accepted(valid_card: str) -> None:
    card = valid_card.replace('xc = "PBE"', 'xc = "pbe"')
    result = validate_rest_input(card)
    assert result.valid is True


def test_invalid_job_type_rejected(valid_card: str) -> None:
    card = valid_card.replace('job_type = "energy"', 'job_type = "freq"')
    result = validate_rest_input(card)
    assert any(e.code == "invalid_job_type" for e in result.errors)


def test_empty_basis_path_rejected(valid_card: str) -> None:
    card = valid_card.replace('basis_path = "/pool/def2-TZVPP"', 'basis_path = ""')
    result = validate_rest_input(card)
    assert any(
        e.code == "invalid_basis_path" and e.field == "basis_path"
        for e in result.errors
    )


def test_missing_basis_path_rejected(valid_card: str) -> None:
    card = valid_card.replace('basis_path = "/pool/def2-TZVPP"\n', "")
    result = validate_rest_input(card)
    assert any(
        e.code == "missing_required_field" and e.field == "basis_path"
        for e in result.errors
    )


def test_spin_zero_rejected(valid_card: str) -> None:
    card = valid_card.replace("spin = 1", "spin = 0")
    result = validate_rest_input(card)
    assert any(
        e.code == "out_of_range" and e.field == "spin" for e in result.errors
    )


def test_num_threads_zero_rejected(valid_card: str) -> None:
    card = valid_card.replace("num_threads = 10", "num_threads = 0")
    result = validate_rest_input(card)
    assert any(
        e.code == "out_of_range" and e.field == "num_threads" for e in result.errors
    )


def test_print_level_negative_rejected(valid_card: str) -> None:
    card = valid_card.replace("print_level = 1", "print_level = -1")
    result = validate_rest_input(card)
    assert any(
        e.code == "out_of_range" and e.field == "print_level" for e in result.errors
    )


def test_singlet_with_spin_polarization_warns(valid_card: str) -> None:
    card = valid_card.replace("spin_polarization = false", "spin_polarization = true")
    result = validate_rest_input(card)
    assert result.valid is True
    assert any(w.code == "singlet_spin_polarization" for w in result.warnings)


def test_high_spin_without_polarization_warns_rohf(valid_card: str) -> None:
    card = valid_card.replace("spin = 1", "spin = 3")
    result = validate_rest_input(card)
    assert result.valid is True
    assert any(w.code == "rohf_high_spin_limitation" for w in result.warnings)


def test_high_spin_with_polarization_clean(valid_card: str) -> None:
    card = valid_card.replace("spin = 1", "spin = 3").replace(
        "spin_polarization = false", "spin_polarization = true"
    )
    result = validate_rest_input(card)
    assert result.valid is True
    assert result.warnings == []


def test_invalid_dispersion_value_rejected(valid_card: str) -> None:
    card = valid_card.replace(
        'job_type = "energy"', 'job_type = "energy"\nempirical_dispersion = "d5"'
    )
    result = validate_rest_input(card)
    assert any(e.code == "invalid_dispersion" for e in result.errors)


def test_dispersion_case_insensitive_accepted(valid_card: str) -> None:
    card = valid_card.replace(
        'job_type = "energy"', 'job_type = "energy"\nempirical_dispersion = "D3BJ"'
    )
    result = validate_rest_input(card)
    assert result.valid is True


def test_double_hybrid_with_dispersion_rejected(valid_card: str) -> None:
    card = valid_card.replace('xc = "PBE"', 'xc = "XYG3"').replace(
        'job_type = "energy"', 'job_type = "energy"\nempirical_dispersion = "d3bj"'
    )
    result = validate_rest_input(card)
    assert any(e.code == "empirical_dispersion_not_needed" for e in result.errors)


def test_position_without_coordinates_rejected(valid_card: str) -> None:
    card = valid_card.replace(
        'position = """\nO 0.0 0.0 0.0\nH 0.0 0.0 1.0\n"""',
        'position = "no coordinates here"',
    )
    result = validate_rest_input(card)
    assert any(e.code == "invalid_position_line" for e in result.errors)


def test_position_line_with_bad_number_reports_line(valid_card: str) -> None:
    card = valid_card.replace("O 0.0 0.0 0.0", "O 0.0 zero 0.0")
    result = validate_rest_input(card)
    issues = [e for e in result.errors if e.code == "invalid_position_line"]
    assert issues
    assert issues[0].line == 1
    assert issues[0].field == "position"
    assert issues[0].section == "geom"


def test_position_not_a_string_rejected(valid_card: str) -> None:
    card = valid_card.replace(
        'position = """\nO 0.0 0.0 0.0\nH 0.0 0.0 1.0\n"""',
        'position = ["O", "0.0", "0.0", "0.0"]',
    )
    result = validate_rest_input(card)
    assert any(
        e.code == "invalid_type" and e.field == "position" for e in result.errors
    )


def test_missing_required_ctrl_field_rejected(valid_card: str) -> None:
    card = valid_card.replace("num_threads = 10\n", "")
    result = validate_rest_input(card)
    assert any(
        e.code == "missing_required_field" and e.field == "num_threads"
        for e in result.errors
    )


def test_missing_spin_polarization_rejected(valid_card: str) -> None:
    card = valid_card.replace("spin_polarization = false\n", "")
    result = validate_rest_input(card)
    assert any(
        e.code == "missing_required_field" and e.field == "spin_polarization"
        for e in result.errors
    )


def test_integer_charge_accepted(valid_card: str) -> None:
    card = valid_card.replace("charge = 0.0", "charge = 0")
    result = validate_rest_input(card)
    assert result.valid is True


def test_bool_is_not_a_valid_spin(valid_card: str) -> None:
    card = valid_card.replace("spin = 1", "spin = true")
    result = validate_rest_input(card)
    assert any(
        e.code == "invalid_type" and e.field == "spin" for e in result.errors
    )


def test_unknown_output_item_rejected(valid_card: str) -> None:
    card = valid_card.replace(
        'job_type = "energy"', 'job_type = "energy"\noutputs = ["spectra"]'
    )
    result = validate_rest_input(card)
    assert any(e.code == "unknown_output" for e in result.errors)


def test_rest_outputs_accepted(valid_card: str) -> None:
    card = valid_card.replace(
        'job_type = "energy"', 'job_type = "energy"\noutputs = ["dipole", "molden"]'
    )
    result = validate_rest_input(card)
    assert result.valid is True


def test_top_level_scalar_key_rejected(valid_card: str) -> None:
    card = "scalar = 1\n" + valid_card
    result = validate_rest_input(card)
    assert any(e.code == "invalid_section" for e in result.errors)


def test_error_order_is_stable() -> None:
    card = (
        "[ctrl]\n"
        'xc = "NOT-A-METHOD"\n'
        'method = "PBE"\n'
        "spin = 0\n"
        'job_type = "freq"\n'
        "\n"
        "[geom]\n"
        "spin_polarization = true\n"
        'position = "garbage"\n'
    )
    result = validate_rest_input(card)
    assert [e.code for e in result.errors] == [
        "forbidden_keyword",
        "missing_required_field",
        "missing_required_field",
        "missing_required_field",
        "missing_required_field",
        "missing_required_field",
        "missing_required_field",
        "field_in_wrong_section",
        "unknown_method",
        "invalid_job_type",
        "out_of_range",
        "invalid_position_line",
        "invalid_position",
    ]
