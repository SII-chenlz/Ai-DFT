"""Tests for the REST TOML renderer in aifs.rest.renderer."""

from collections.abc import Callable

import pytest

from aifs.config import ConfigurationError, get_settings
from aifs.models import DomainValidationError, RestInputRequest, RestInputResponse
from aifs.rest import tomllib
from aifs.rest.renderer import render_rest_input


def test_b3lyp_gets_default_basis_def2_tzvpp(
    make_request: Callable[..., RestInputRequest],
) -> None:
    response = render_rest_input(make_request(xc="B3LYP"))
    data = tomllib.loads(response.rest_input)
    assert data["ctrl"]["basis_path"] == "/data/rest/basis_sets/def2-TZVPP"
    assert "basis=def2-TZVPP" in response.defaults_applied
    assert response.effective_settings["basis"] == "def2-TZVPP"


def test_xyg3_gets_default_basis_def2_qzvpp(
    make_request: Callable[..., RestInputRequest],
) -> None:
    response = render_rest_input(make_request(xc="XYG3"))
    data = tomllib.loads(response.rest_input)
    assert data["ctrl"]["basis_path"] == "/data/rest/basis_sets/def2-QZVPP"
    assert "basis=def2-QZVPP" in response.defaults_applied


def test_mp2_gets_default_basis_def2_qzvpp(
    make_request: Callable[..., RestInputRequest],
) -> None:
    response = render_rest_input(make_request(xc="MP2"))
    data = tomllib.loads(response.rest_input)
    assert data["ctrl"]["basis_path"].endswith("/def2-QZVPP")


def test_explicit_basis_wins_without_default(
    make_request: Callable[..., RestInputRequest],
) -> None:
    response = render_rest_input(make_request(xc="PBE", basis="def2-SVP"))
    data = tomllib.loads(response.rest_input)
    assert data["ctrl"]["basis_path"] == "/data/rest/basis_sets/def2-SVP"
    assert not any(item.startswith("basis=") for item in response.defaults_applied)


def test_basis_path_joins_configured_pool_and_basis(
    make_request: Callable[..., RestInputRequest], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AIFS_BASIS_SET_POOL", "/opt/rest/pool")
    get_settings.cache_clear()
    response = render_rest_input(make_request())
    data = tomllib.loads(response.rest_input)
    assert data["ctrl"]["basis_path"] == "/opt/rest/pool/def2-TZVPP"


@pytest.mark.parametrize(
    "basis",
    [
        "/etc/evil",
        "C:\\evil",
        "..",
        "../evil",
        "sub/../../evil",
        "..\\evil",
        ".",
        "sub/./evil",
    ],
)
def test_basis_escaping_pool_is_rejected(
    make_request: Callable[..., RestInputRequest], basis: str
) -> None:
    with pytest.raises(DomainValidationError) as excinfo:
        render_rest_input(make_request(basis=basis))
    assert excinfo.value.code == "basis_outside_pool"


def test_basis_nested_inside_pool_is_allowed(
    make_request: Callable[..., RestInputRequest],
) -> None:
    response = render_rest_input(make_request(basis="sub/def2-SVP"))
    data = tomllib.loads(response.rest_input)
    assert data["ctrl"]["basis_path"] == "/data/rest/basis_sets/sub/def2-SVP"


def test_missing_pool_configuration_is_infrastructure_error(
    make_request: Callable[..., RestInputRequest], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AIFS_BASIS_SET_POOL", raising=False)
    get_settings.cache_clear()
    with pytest.raises(ConfigurationError):
        render_rest_input(make_request())


def test_d3bj_emitted_as_separate_empirical_dispersion_key(
    make_request: Callable[..., RestInputRequest],
) -> None:
    response = render_rest_input(make_request(xc="B3LYP", empirical_dispersion="d3bj"))
    assert 'empirical_dispersion = "d3bj"' in response.rest_input
    data = tomllib.loads(response.rest_input)
    assert data["ctrl"]["empirical_dispersion"] == "d3bj"


def test_no_empirical_dispersion_key_when_not_requested(
    make_request: Callable[..., RestInputRequest],
) -> None:
    response = render_rest_input(make_request(xc="PBE"))
    assert "empirical_dispersion" not in tomllib.loads(response.rest_input)["ctrl"]


@pytest.mark.parametrize(
    "xc",
    ["XYG3", "XYG7", "XYGJOS", "xDH-PBE0", "sBGE2", "ZRPS", "scsRPA", "R-xDH7",
     "RPA@PBE", "RPA@B3LYP"],
)
def test_double_hybrid_rpa_rejects_empirical_dispersion(
    make_request: Callable[..., RestInputRequest], xc: str
) -> None:
    with pytest.raises(DomainValidationError) as excinfo:
        render_rest_input(make_request(xc=xc, empirical_dispersion="d3"))
    assert excinfo.value.code == "empirical_dispersion_not_needed"


def test_mp2_with_dispersion_is_not_a_double_hybrid(
    make_request: Callable[..., RestInputRequest],
) -> None:
    response = render_rest_input(make_request(xc="MP2", empirical_dispersion="d3"))
    data = tomllib.loads(response.rest_input)
    assert data["ctrl"]["empirical_dispersion"] == "d3"


def test_rendered_card_is_parseable_toml(
    make_request: Callable[..., RestInputRequest],
) -> None:
    response = render_rest_input(make_request())
    data = tomllib.loads(response.rest_input)
    assert "ctrl" in data
    assert "geom" in data


def test_rendered_card_has_correct_sections_and_field_positions(
    make_request: Callable[..., RestInputRequest],
) -> None:
    response = render_rest_input(make_request())
    data = tomllib.loads(response.rest_input)
    ctrl = data["ctrl"]
    required_ctrl = {"xc", "basis_path", "print_level", "num_threads", "job_type",
                     "charge", "spin", "spin_polarization"}
    assert required_ctrl <= set(ctrl)
    assert "position" not in ctrl
    geom = data["geom"]
    assert set(geom) >= {"name", "position"}
    for keyword in ("spin", "charge", "spin_polarization"):
        assert keyword not in geom


def test_default_num_threads_is_ten(
    make_request: Callable[..., RestInputRequest],
) -> None:
    response = render_rest_input(make_request())
    assert tomllib.loads(response.rest_input)["ctrl"]["num_threads"] == 10


def test_spin_one_derives_spin_polarization_false(
    make_request: Callable[..., RestInputRequest],
) -> None:
    response = render_rest_input(make_request(spin=1))
    assert tomllib.loads(response.rest_input)["ctrl"]["spin_polarization"] is False
    assert "spin_polarization=false" in response.defaults_applied


def test_spin_gt_one_derives_spin_polarization_true(
    make_request: Callable[..., RestInputRequest],
) -> None:
    response = render_rest_input(make_request(spin=3))
    assert tomllib.loads(response.rest_input)["ctrl"]["spin_polarization"] is True
    assert "spin_polarization=true" in response.defaults_applied


def test_explicit_spin_polarization_kept_without_default(
    make_request: Callable[..., RestInputRequest],
) -> None:
    response = render_rest_input(make_request(spin=1, spin_polarization=True))
    assert tomllib.loads(response.rest_input)["ctrl"]["spin_polarization"] is True
    assert not any(
        item.startswith("spin_polarization=") for item in response.defaults_applied
    )


def test_position_uses_triple_double_quoted_multiline_string(
    make_request: Callable[..., RestInputRequest],
) -> None:
    response = render_rest_input(make_request())
    assert 'position = """' in response.rest_input
    assert "position = '''" not in response.rest_input


def test_position_roundtrips_quotes_and_backslashes(
    make_request: Callable[..., RestInputRequest],
) -> None:
    tricky = 'O 0 0 0\nH "quoted" 0 \\\\ 0\nH 0 0 0'
    response = render_rest_input(make_request(position=tricky))
    assert tomllib.loads(response.rest_input)["geom"]["position"] == tricky


def test_outputs_omitted_when_empty(
    make_request: Callable[..., RestInputRequest],
) -> None:
    response = render_rest_input(make_request())
    assert "outputs" not in tomllib.loads(response.rest_input)["ctrl"]


def test_outputs_emitted_when_requested(
    make_request: Callable[..., RestInputRequest],
) -> None:
    response = render_rest_input(make_request(outputs=["dipole", "fchk"]))
    assert tomllib.loads(response.rest_input)["ctrl"]["outputs"] == ["dipole", "fchk"]


def test_stable_field_order_snapshot(
    make_request: Callable[..., RestInputRequest],
) -> None:
    response = render_rest_input(make_request())
    expected = (
        '[ctrl]\n'
        'xc = "B3LYP"\n'
        'basis_path = "/data/rest/basis_sets/def2-TZVPP"\n'
        "print_level = 1\n"
        "num_threads = 10\n"
        'job_type = "energy"\n'
        "charge = 0.0\n"
        "spin = 1\n"
        "spin_polarization = false\n"
        "\n"
        "[geom]\n"
        'name = "water"\n'
        'position = """\n'
        "O 0.0 0.0 0.0\n"
        "H 0.757 0.586 0.0\n"
        "H -0.757 0.586 0.0"
        '"""\n'
    )
    assert response.rest_input == expected


def test_numerical_dipole_job_type_renders(
    make_request: Callable[..., RestInputRequest],
) -> None:
    response = render_rest_input(make_request(job_type="numerical dipole"))
    assert tomllib.loads(response.rest_input)["ctrl"]["job_type"] == "numerical dipole"


def test_effective_settings_complete(
    make_request: Callable[..., RestInputRequest],
) -> None:
    response = render_rest_input(make_request(xc="PBE", empirical_dispersion="d4"))
    settings = response.effective_settings
    assert settings["xc"] == "PBE"
    assert settings["basis"] == "def2-TZVPP"
    assert settings["basis_path"] == "/data/rest/basis_sets/def2-TZVPP"
    assert settings["job_type"] == "energy"
    assert settings["charge"] == 0.0
    assert settings["spin"] == 1
    assert settings["spin_polarization"] is False
    assert settings["print_level"] == 1
    assert settings["num_threads"] == 10
    assert settings["empirical_dispersion"] == "d4"
    assert settings["outputs"] == []


def test_response_shape(make_request: Callable[..., RestInputRequest]) -> None:
    response = render_rest_input(make_request())
    assert isinstance(response, RestInputResponse)
    assert isinstance(response.warnings, list)
    assert response.warnings == []


def test_request_model_field_order_preserved_in_card(
    make_request: Callable[..., RestInputRequest],
) -> None:
    response = render_rest_input(make_request(charge=-1.0, spin=2, print_level=2))
    data = tomllib.loads(response.rest_input)
    assert data["ctrl"]["charge"] == -1.0
    assert data["ctrl"]["spin"] == 2
    assert data["ctrl"]["print_level"] == 2
