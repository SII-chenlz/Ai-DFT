"""Orchestration: requirement -> recommendation -> job spec -> input cards."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from functional_advisor.knowledge import (
    build_job_spec,
    knowledge_summary,
    rule_based_recommendation,
)
from functional_advisor.llm import DeepSeekClient
from functional_advisor.models import DftJobSpec, FunctionalRecommendation, UserRequirement
from functional_advisor.renderers import render_inputs

SYSTEM_PROMPT = """You are a senior computational materials scientist who selects density-functional-theory (DFT) exchange-correlation functionals and produces concrete input-card settings.

Rules:
1. Recommend a functional only when justified by the system type and requested task.
2. Explicitly state dispersion corrections, Hubbard U, spin, and hybrid settings when needed.
3. Never invent references; use empty lists when unsure.
4. Return valid JSON only, with this exact schema:
{
  "functional": "string",
  "dispersion": "string or empty string",
  "hubbard_u": {"element": number},
  "rationale": "string",
  "caveats": ["string"],
  "references": ["string"],
  "parameters": {"KEY": value}
}
Parameters must use code-native keys for the target code where possible (VASP: ENCUT, IVDW, LHFCALC, AEXX, LDAU, etc.; QE: ecutwfc, ecutrho, input_dft, etc.)."""


@dataclass
class RecommendationResult:
    """Structured output returned by the advisor."""

    requirement: UserRequirement
    recommendation: FunctionalRecommendation
    job_spec: DftJobSpec
    inputs: dict[str, str]
    llm_used: bool = False
    messages: list[str] = field(default_factory=list)


class FunctionalAdvisor:
    """DeepSeek-powered DFT functional recommender with a deterministic fallback."""

    def __init__(
        self,
        client: DeepSeekClient | None = None,
        *,
        use_llm: bool | None = None,
    ) -> None:
        self.client = client or DeepSeekClient()
        self.use_llm = self.client.available if use_llm is None else use_llm

    def parse_requirement(self, text: str, *, code: str = "vasp") -> UserRequirement:
        """Normalize a free-text user request.

        The current parser is conservative: it treats the whole text as a
        system description and detects a few explicit task/flag keywords. A
        future LLM extraction step can replace this with richer structured slots.
        """
        lowered = text.lower()
        task = "geometry optimization and single-point energy"
        task_keywords = [
            ("band structure", "band structure"),
            ("bandgap", "band gap"),
            ("band gap", "band gap"),
            ("optical", "optical absorption spectrum"),
            ("phonon", "phonon calculation"),
            ("elastic", "elastic constants"),
            ("adsorption", "adsorption energy"),
            ("transition state", "transition-state search"),
            ("neb", "NEB transition-state search"),
            ("barrier", "reaction barrier"),
            ("raman", "Raman spectrum"),
            ("能带", "band structure"),
            ("带隙", "band gap"),
            ("光学", "optical absorption spectrum"),
            ("声子", "phonon calculation"),
            ("弹性", "elastic constants"),
            ("吸附", "adsorption energy"),
            ("过渡态", "transition-state search"),
            ("势垒", "reaction barrier"),
            ("拉曼", "Raman spectrum"),
        ]
        for keyword, mapped in task_keywords:
            if keyword in lowered:
                task = mapped
                break

        return UserRequirement(
            system_description=text.strip(),
            task=task,
            code=code if code in {"vasp", "qe"} else "vasp",
            spin_polarized=any(k in lowered for k in ("magnetic", "ferromagnetic", "antiferromagnetic", "spin", "磁性", "铁磁", "反铁磁", "自旋")),
            charged=any(k in lowered for k in ("charged", "cation", "anion", "带电", "阳离子", "阴离子")),
            charge=0,
            precision=_detect_precision(lowered),
            extra_constraints=[
                item for item in ("fix bottom layers", "SOC", "spin-orbit coupling")
                if item.lower() in lowered
            ],
        )

    def recommend(self, text: str, *, code: str = "vasp", structure_file: str | None = None) -> RecommendationResult:
        """Run the full recommendation pipeline and render input files."""
        requirement = self.parse_requirement(text, code=code)
        messages: list[str] = []

        if self.use_llm:
            try:
                recommendation = self._llm_recommendation(requirement)
                messages.append("Used DeepSeek LLM recommendation.")
            except Exception as exc:  # noqa: BLE001 - fallback should survive any API failure
                recommendation = rule_based_recommendation(requirement)
                messages.append(f"LLM call failed, using rule-based fallback: {exc}")
        else:
            recommendation = rule_based_recommendation(requirement)
            messages.append("DEEPSEEK_API_KEY not set; using rule-based fallback.")

        job_spec = build_job_spec(requirement, recommendation)
        job_spec.structure_file = structure_file
        inputs = render_inputs(job_spec)
        return RecommendationResult(
            requirement=requirement,
            recommendation=recommendation,
            job_spec=job_spec,
            inputs=inputs,
            llm_used=self.use_llm,
            messages=messages,
        )

    def _llm_recommendation(self, requirement: UserRequirement) -> FunctionalRecommendation:
        user_prompt = f"""Knowledge base summary:
{knowledge_summary()}

User requirement:
- System: {requirement.system_description}
- Elements: {', '.join(requirement.elements) or 'unknown'}
- Task: {requirement.task}
- Target code: {requirement.code}
- Spin polarized: {requirement.spin_polarized}
- Charged: {requirement.charged}
- Precision: {requirement.precision}
- Constraints: {', '.join(requirement.extra_constraints) or 'none'}

Return one JSON object recommending functional and code-native parameters."""
        data = self.client.complete_json(SYSTEM_PROMPT, user_prompt)
        return FunctionalRecommendation(
            functional=str(data.get("functional", "PBE")),
            dispersion=str(data.get("dispersion", "")),
            hubbard_u=_normalise_hubbard_u(data.get("hubbard_u", {})),
            rationale=str(data.get("rationale", "")),
            caveats=[str(item) for item in data.get("caveats", [])],
            references=[str(item) for item in data.get("references", [])],
            parameters=_normalise_parameters(data.get("parameters", {})),
            recommended_for=[],
        )


def _detect_precision(lowered: str) -> str:
    if any(k in lowered for k in ("quick", "fast", "coarse", "cheap")):
        return "quick"
    if any(k in lowered for k in ("high precision", "accurate", "benchmark", "high-accuracy")):
        return "high"
    return "normal"


def _normalise_hubbard_u(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, float] = {}
    for key, item in value.items():
        try:
            result[str(key)] = float(item)
        except (TypeError, ValueError):
            continue
    return result


def _normalise_parameters(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def result_to_dict(result: RecommendationResult) -> dict[str, Any]:
    """JSON-friendly representation used by the CLI."""
    return {
        "requirement": result.requirement.model_dump(),
        "recommendation": result.recommendation.model_dump(),
        "job_spec": result.job_spec.model_dump(),
        "inputs": result.inputs,
        "llm_used": result.llm_used,
        "messages": result.messages,
    }
