from functional_advisor.knowledge import build_job_spec
from functional_advisor.models import DftJobSpec, FunctionalRecommendation, UserRequirement
from functional_advisor.renderers import render_inputs


def test_render_vasp_inputs():
    req = UserRequirement(system_description="Fe slab", task="adsorption energy", code="vasp")
    rec = FunctionalRecommendation(
        functional="PBE",
        dispersion="D3(BJ)",
        rationale="reasonable default",
        parameters={"IVDW": 11},
    )
    spec = build_job_spec(req, rec)
    inputs = render_inputs(spec)
    assert inputs["INCAR"].startswith("SYSTEM = Fe slab")
    assert "IVDW = 11" in inputs["INCAR"]
    assert "KPOINTS" in inputs


def test_render_qe_inputs():
    spec = DftJobSpec(
        code="qe",
        system_name="water",
        task="geometry optimization and single-point energy",
        functional="PBE",
        parameters={"ecutwfc": 60, "ecutrho": 480},
    )
    inputs = render_inputs(spec)
    assert "calculation = 'relax'" in inputs["pw.x.in"]
    assert "ecutwfc = 60" in inputs["pw.x.in"]
