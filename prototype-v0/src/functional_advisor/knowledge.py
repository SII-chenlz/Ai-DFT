"""Curated DFT functional-selection knowledge base and rule-based fallback."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

from functional_advisor.models import DftCode, DftJobSpec, FunctionalRecommendation, UserRequirement

DATA_PATH = files("functional_advisor").joinpath("data", "functional_rules.json")


def load_knowledge_base() -> dict[str, Any]:
    """Load the bundled functional-rules JSON."""
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def rule_based_recommendation(requirement: UserRequirement) -> FunctionalRecommendation:
    """Select a sensible functional without calling an LLM.

    Scoring is intentionally simple: count keyword hits against a curated rule
    table. It provides a safe, explainable fallback when no API key is present.
    """
    kb = load_knowledge_base()
    text = " ".join(
        [
            requirement.system_description,
            requirement.task,
            " ".join(requirement.extra_constraints),
            " ".join(requirement.elements),
        ]
    ).lower()

    best_rule = None
    best_score = -1
    for rule in kb["rules"]:
        score = sum(1 for keyword in rule["keywords"] if keyword.lower() in text)
        if score > best_score:
            best_score = score
            best_rule = rule

    matched_id = best_rule["id"] if (best_rule is not None and best_score > 0) else "general_default"

    if best_rule is None or best_score == 0:
        rec = {
            "functional": "PBE",
            "dispersion": "D3(BJ)",
            "rationale": "No specific system class matched the rule base; PBE-D3(BJ) is a conservative general default.",
            "caveats": ["Review the generated settings before production runs."],
            "references": [],
            "parameters": {"IVDW": 11},
        }
    else:
        rec = best_rule["recommendation"]

    if requirement.spin_polarized:
        rec.setdefault("parameters", {})["ISPIN"] = 2
    if requirement.charged:
        rec.setdefault("caveats", []).append(
            "System is charged; verify cell neutrality/counterions and enable the code's charge keyword."
        )

    return FunctionalRecommendation(
        functional=rec["functional"],
        dispersion=rec.get("dispersion", ""),
        rationale=rec["rationale"],
        caveats=rec.get("caveats", []),
        references=rec.get("references", []),
        parameters=rec.get("parameters", {}),
        recommended_for=[matched_id],
    )




def code_defaults(code: DftCode) -> dict[str, Any]:
    kb = load_knowledge_base()
    return dict(kb["defaults"][code])


def build_job_spec(
    requirement: UserRequirement, recommendation: FunctionalRecommendation
) -> DftJobSpec:
    """Merge user requirements, recommendation, and code defaults into one spec."""
    params = code_defaults(requirement.code)
    params.update(recommendation.parameters)
    if requirement.spin_polarized:
        params["ISPIN"] = 2
    if requirement.charged or requirement.charge != 0:
        if requirement.code == "vasp":
            # VASP requires total valence electron count; leave a placeholder for later
            # structure-aware ingestion to fill after reading POTCAR/POSCAR.
            params["_charge_note"] = "set NELECT from total valence electrons minus net charge"
        else:
            params["tot_charge"] = requirement.charge

    notes = list(recommendation.caveats)
    if requirement.precision == "quick":
        notes.append("Quick mode: use low k-mesh, EDIFF=1e-4, and turn off expensive output.")
    elif requirement.precision == "high":
        notes.append("High mode: increase ENCUT/ecutwfc, tighten EDIFF, and use denser k-mesh.")

    return DftJobSpec(
        code=requirement.code,
        system_name=requirement.system_description[:60],
        task=requirement.task,
        functional=recommendation.functional,
        dispersion=recommendation.dispersion,
        hubbard_u=recommendation.hubbard_u,
        spin_polarized=requirement.spin_polarized,
        charged=requirement.charged,
        charge=requirement.charge,
        parameters=params,
        notes=notes,
    )


def knowledge_summary(max_rules: int | None = None) -> str:
    """Return a compact, prompt-ready summary of the knowledge base."""
    kb = load_knowledge_base()
    lines = []
    rules = kb["rules"]
    if max_rules is not None:
        rules = rules[:max_rules]
    for rule in rules:
        rec = rule["recommendation"]
        lines.append(
            f"- {rule['id']} (keywords: {', '.join(rule['keywords'])}): "
            f"{rec['functional']} / {rec.get('dispersion', 'none')}. {rec['rationale']}"
        )
    return "\n".join(lines)
