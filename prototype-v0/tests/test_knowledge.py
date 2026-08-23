from functional_advisor.advisor import FunctionalAdvisor
from functional_advisor.knowledge import load_knowledge_base, rule_based_recommendation
from functional_advisor.models import UserRequirement


def test_knowledge_base_has_defaults():
    kb = load_knowledge_base()
    assert kb["defaults"]["vasp"]["ENCUT"] > 0
    assert kb["rules"]


def test_rule_based_surface_recommendation():
    req = UserRequirement(
        system_description="TiO2(110) surface adsorbs water",
        elements=["Ti", "O", "H"],
        task="adsorption energy",
        code="vasp",
    )
    rec = rule_based_recommendation(req)
    assert rec.functional in {"optB88-vdW", "PBE"}
    assert rec.rationale


def test_advisor_fallback_renders_vasp_inputs():
    advisor = FunctionalAdvisor(use_llm=False)
    result = advisor.recommend("TiO2(110) surface adsorbs water", code="vasp")
    assert result.llm_used is False
    assert "INCAR" in result.inputs
    assert "POTCAR.placeholder" in result.inputs
    assert "ENCUT" in result.inputs["INCAR"]
