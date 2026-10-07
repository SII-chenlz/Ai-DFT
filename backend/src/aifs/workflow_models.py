"""Versioned molecular workflow contracts and deterministic plan checks."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from aifs.models import DomainValidationError
from aifs.rest.capabilities import normalize_xc, semantic_errors
from aifs.rest.catalogs import JOB_TYPES


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EvidenceRef(StrictModel):
    source: Literal["local", "web"]
    claim_type: (
        Literal["method_used", "comparative_benchmark", "author_recommendation", "other"] | None
    ) = None
    record_id: str | None = None
    url: str | None = None
    title: str | None = None
    note: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def check_reference(self) -> EvidenceRef:
        if self.source == "local" and not self.record_id:
            raise ValueError("local evidence requires record_id")
        if self.source == "web":
            try:
                parsed = urlsplit(self.url or "")
                valid_url = parsed.scheme in {"https", "http"} and bool(parsed.hostname)
            except ValueError:
                valid_url = False
            if not valid_url or not self.title:
                raise ValueError("web evidence requires an HTTP(S) url and title")
        if self.source == "web" and not self.note.startswith("未整理网页来源："):
            prefix = "未整理网页来源："
            if len(self.note) + len(prefix) > 2000:
                raise ValueError("web evidence note is too long after the uncurated label")
            self.note = prefix + self.note
        return self


class MethodDecision(StrictModel):
    xc: str = Field(min_length=1, max_length=100)
    xc_parser: Literal["legacy", "parse_xc"] = "legacy"
    basis: str | None = Field(default=None, min_length=1, max_length=200)
    empirical_dispersion: Literal["d3", "d3bj", "d4"] | None = None
    source: Literal["user", "evidence", "provisional"]
    rationale: str = Field(min_length=1, max_length=4000)
    uncertainty: str | None = None
    supporting: list[EvidenceRef] = Field(default_factory=list)
    opposing: list[EvidenceRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_source(self) -> MethodDecision:
        if self.source == "evidence" and not self.supporting:
            raise ValueError("evidence-based decision requires supporting references")
        if self.source == "evidence" and self.supporting:
            claim_types = {ref.claim_type for ref in self.supporting}
            if claim_types <= {"method_used"}:
                caution = "现有引用只说明方法被使用，不能证明相对优选。"
            elif "comparative_benchmark" not in claim_types:
                caution = "支持证据未包含明确的比较基准，不能据此证明相对优选。"
            else:
                caution = ""
            if caution and (not self.uncertainty or caution not in self.uncertainty):
                self.uncertainty = f"{caution} {self.uncertainty or ''}".strip()
        if any(ref.source == "web" for ref in (*self.supporting, *self.opposing)):
            caution = "网页来源未整理，泛函优选未核验。"
            if not self.uncertainty or caution not in self.uncertainty:
                self.uncertainty = f"{caution} {self.uncertainty or ''}".strip()
        return self


class MethodCandidate(StrictModel):
    xc: str = Field(min_length=1, max_length=100)
    basis: str | None = None
    rationale: str = Field(min_length=1, max_length=2000)
    supporting: list[EvidenceRef] = Field(default_factory=list)
    opposing: list[EvidenceRef] = Field(default_factory=list)


class TaskInputs(StrictModel):
    position: str | None = Field(default=None, max_length=200_000)
    position_unit: Literal["angstrom", "bohr"] | None = None
    position_source: Literal["user", "external_optimized", "prior_result"] | None = None
    position_from_task: str | None = None
    charge: float | None = None
    charge_source: Literal["user", "external"] | None = None
    spin: int | None = Field(default=None, ge=1)
    spin_source: Literal["user", "external"] | None = None


class PlanTask(StrictModel):
    task_id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
    title: str = Field(min_length=1, max_length=200)
    purpose: str = Field(min_length=1, max_length=2000)
    kind: Literal["rest", "analysis", "unsupported"]
    depends_on: list[str] = Field(default_factory=list)
    system_name: str | None = None
    job_type: str | None = None
    rest_options: dict[str, dict[str, JsonValue]] = Field(default_factory=dict)
    analysis_formula: str | None = None
    inputs: TaskInputs = Field(default_factory=TaskInputs)
    candidates: list[MethodCandidate] = Field(default_factory=list)
    decision: MethodDecision | None = None
    notes: str | None = None


class PlanDraft(StrictModel):
    question: str = Field(min_length=1, max_length=8000)
    goal: Literal[
        "reaction_energy", "binding_energy", "optimization_single_point", "force", "dipole", "other"
    ]
    tasks: list[PlanTask] = Field(min_length=1, max_length=100)
    assumptions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_graph(self) -> PlanDraft:
        by_id = {task.task_id: task for task in self.tasks}
        if len(by_id) != len(self.tasks):
            raise ValueError("task_id must be unique")
        for task in self.tasks:
            if len(set(task.depends_on)) != len(task.depends_on):
                raise ValueError(f"duplicate dependency in {task.task_id}")
            if any(dep not in by_id for dep in task.depends_on):
                raise ValueError(f"unknown dependency in {task.task_id}")
            if task.kind == "rest" and not task.job_type:
                raise ValueError(f"REST task {task.task_id} requires job_type")
            if task.kind == "analysis" and not task.analysis_formula:
                raise ValueError(f"analysis task {task.task_id} requires analysis_formula")
            if task.inputs.position_source == "prior_result":
                if (
                    not task.inputs.position_from_task
                    or task.inputs.position_from_task not in task.depends_on
                ):
                    raise ValueError(
                        f"{task.task_id}: prior_result needs a direct source dependency"
                    )
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str) -> None:
            if task_id in visiting:
                raise ValueError("task dependencies form a cycle")
            if task_id in visited:
                return
            visiting.add(task_id)
            for parent in by_id[task_id].depends_on:
                visit(parent)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in by_id:
            visit(task_id)
        jobs = [task for task in self.tasks if task.kind == "rest"]
        if self.goal in {"reaction_energy", "binding_energy"}:
            energy_ids = {task.task_id for task in jobs if task.job_type == "energy"}
            if len(energy_ids) < 2 or not any(
                task.kind == "analysis" and len(energy_ids.intersection(task.depends_on)) >= 2
                for task in self.tasks
            ):
                raise ValueError(
                    "energy-combination goal needs two energy tasks and an analysis task "
                    "depending on them"
                )
        if self.goal == "optimization_single_point" and not any(
            task.job_type == "energy"
            and any(by_id[dep].job_type == "opt" for dep in task.depends_on)
            for task in jobs
        ):
            raise ValueError(
                "optimization_single_point needs an energy task depending on optimization"
            )
        if self.goal in {"force", "dipole"}:
            required = "force" if self.goal == "force" else "numerical dipole"
            if not any(task.job_type == required for task in jobs):
                raise ValueError(f"{self.goal} goal needs a {required} task")
        return self


class PlanRevisionRequest(StrictModel):
    expected_version: int = Field(ge=1)
    change_reason: str = Field(min_length=1, max_length=2000)
    plan: PlanDraft


class TaskStatus(StrictModel):
    task_id: str
    state: Literal[
        "unsupported",
        "analysis_only",
        "needs_input",
        "needs_decision",
        "ready_for_card",
        "card_ready",
    ]
    blockers: list[str]


def task_status(
    task: PlanTask, by_id: dict[str, PlanTask], *, has_card: bool = False
) -> TaskStatus:
    if task.kind == "unsupported" or (task.kind == "rest" and task.job_type not in JOB_TYPES):
        return TaskStatus(
            task_id=task.task_id,
            state="unsupported",
            blockers=["This task is not covered by the current AIFS REST card interface"],
        )
    if task.kind == "analysis":
        return TaskStatus(task_id=task.task_id, state="analysis_only", blockers=[])
    if task.decision and normalize_xc(task.decision.xc, task.decision.xc_parser) is None:
        return TaskStatus(
            task_id=task.task_id,
            state="unsupported",
            blockers=["The selected method is not in the current AIFS REST card catalog"],
        )
    blockers: list[str] = []
    if not task.system_name:
        blockers.append("system_name is missing")
    if not task.inputs.position or not task.inputs.position_source:
        blockers.append("confirmed coordinates are missing")
    if task.inputs.position_unit is None:
        blockers.append("confirmed coordinate unit (angstrom or bohr) is missing")
    if task.inputs.charge is None or not task.inputs.charge_source:
        blockers.append("confirmed charge is missing")
    if task.inputs.spin is None or not task.inputs.spin_source:
        blockers.append("confirmed spin multiplicity is missing")
    if task.job_type == "energy" and any(by_id[dep].job_type == "opt" for dep in task.depends_on):
        if task.inputs.position_source not in {"prior_result", "external_optimized"}:
            blockers.append("optimized coordinates from the preceding task are required")
    if task.inputs.position_source == "prior_result" and task.inputs.position_from_task:
        if by_id[task.inputs.position_from_task].job_type != "opt":
            blockers.append("position source must be an optimization task")
    if blockers:
        return TaskStatus(task_id=task.task_id, state="needs_input", blockers=blockers)
    if task.decision is None:
        return TaskStatus(
            task_id=task.task_id, state="needs_decision", blockers=["method decision is missing"]
        )
    if task.decision.source == "provisional":
        return TaskStatus(
            task_id=task.task_id,
            state="needs_decision",
            blockers=["provisional method needs user confirmation or evidence"],
        )
    if task.decision.basis is None:
        return TaskStatus(
            task_id=task.task_id,
            state="needs_decision",
            blockers=["basis decision is missing; selecting a functional does not select a basis"],
        )
    ctrl = {
        **task.rest_options.get("ctrl", {}),
        "xc": task.decision.xc,
        "xc_parser": task.decision.xc_parser,
        "job_type": task.job_type,
        "spin": task.inputs.spin,
        "spin_polarization": task.inputs.spin > 1,
        "empirical_dispersion": task.decision.empirical_dispersion,
    }
    geom = {**task.rest_options.get("geom", {}), "position": task.inputs.position}
    option_blockers = semantic_errors(ctrl, geom, task.rest_options)
    if option_blockers:
        return TaskStatus(task_id=task.task_id, state="needs_input", blockers=option_blockers)
    return TaskStatus(
        task_id=task.task_id, state="card_ready" if has_card else "ready_for_card", blockers=[]
    )


def require_card_ready(task: PlanTask, by_id: dict[str, PlanTask]) -> None:
    status = task_status(task, by_id)
    if status.state != "ready_for_card":
        raise DomainValidationError(
            "task_not_ready", f"{task.task_id}: {', '.join(status.blockers) or status.state}"
        )
