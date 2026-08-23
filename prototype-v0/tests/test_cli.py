from functional_advisor.cli import main


def test_cli_rule_based(tmp_path):
    code = main([
        "有机分子晶体，做几何优化和单点能",
        "--code", "vasp",
        "--no-llm",
        "--out-dir", str(tmp_path / "run"),
    ])
    assert code == 0
    assert (tmp_path / "run" / "INCAR").exists()
    assert (tmp_path / "run" / "KPOINTS").exists()
