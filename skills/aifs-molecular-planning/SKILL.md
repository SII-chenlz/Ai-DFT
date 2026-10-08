---
name: aifs-molecular-planning
description: Use for REST input-file preparation, functional/basis selection and molecular workflows with prerequisite calculations or energy comparisons.
---

# AIFS REST planning

AIFS prepares REST input files and retains dependent calculation workflows. DSH supplies the model, conversation, web tools, selection panels and file delivery. The model proposes the science; AIFS checks structured inputs, saved dependencies and integrated REST contracts. AIFS does not run calculations, parse results or certify free-text scientific formulas.

## Load only the relevant detail

Resolve relative files against the directory `resourceBase` returned by DSH's Skill loader, not the user's workspace. Read:

- [methods.md](references/methods.md) when proposing or confirming functionals/bases: per-stage choices, exact variants, double hybrids and derivative limits.
- [observables.md](references/observables.md) for energy differences, experimental comparison, ZPE/thermal corrections or spectroscopy. Plan from the quantity and actual states, not a test molecule.
- [rest-operations.md](references/rest-operations.md) for frequencies, thermochemistry, multipoles, excited states, TS/IRC, constraints or RRS-PBC. Pair the mapping with the current capability tool; AIFS integration gaps are not proof that REST lacks a feature.

Use the complete create/revise tool schemas. The user's workspace need not contain backend source. Query `get_rest_capabilities` before offering REST-ready choices; reuse that result and query only relevant sections for exact types, units and operation limits.

## Choose the delivery path

**Independent calculations: prepare input files directly.** Confirm coordinates/unit, charge, multiplicity, functional and basis; call `generate_rest_input` for each ready calculation. It generates and independently validates in one backend call, returning `rest_input`, `filename` and `validation`. Export that exact body as the `.in` file. Several unrelated files do not require a plan. Missing scientific inputs are questions to resolve, not defaults to invent. No plan IDs, candidates or evidence arrays are needed in a direct card request.

**Dependent or combined calculations: save the workflow automatically.** Optimization followed by a single point/frequency/property, or an energy difference assembled from several calculations, needs a saved graph even when the user only asks for input files. Explain the scientific steps briefly, save them with `create_aifs_plan`, then deliver ready files with `generate_aifs_task_card`; leave later steps waiting for actual results. Do not ask a novice to choose whether to create a plan. A user may also request saving one independent calculation or resuming an existing plan. This is independent of DSH's planning mode.

### Direct card example

When the user explicitly supplies these coordinates/unit, charge/multiplicity and PBE/def2-TZVP for an H2 single point, the entire `generate_rest_input` request is:

```json
{
  "system_name": "H2",
  "position": "H 0 0 0\nH 0 0 0.74",
  "position_unit": "angstrom",
  "charge": 0,
  "spin": 1,
  "xc": "PBE",
  "basis": "def2-TZVP",
  "job_type": "energy"
}
```

This is an input-shape example, not a universal method recommendation. Different properties may require additional reviewed `rest_options` sections and the appropriate `xc_parser`.

## Prepare the science and retain the required steps

1. Identify the requested observable and species/states, available structures, confirmed methods and precision/cost constraints. Explain plausible interpretations in plain language. Ask only about unresolved information that changes the calculation. Keep unsupported operations as explicit pending steps, preserving their purpose and dependencies.
2. Identify each calculation's purpose and prerequisite results. Reaction differences need participating species and stoichiometry; binding differences need complex/fragments and geometry/BSSE assumptions. Later single points, frequencies or properties use the required structure, not a guessed result. In a saved workflow, give tasks stable IDs and `depends_on`.
3. Keep unknown values unresolved. Explain proposed charge/multiplicity with the scientific rationale; only submit resolved inputs for direct cards. In saved workflows use null plus notes/assumptions for unknowns and record source fields. `charge` is net charge; `spin` is multiplicity 2S+1. A user-confirmed proposal has source `user`; `external` requires an actual external record. Source labels record your attribution; they do not independently authenticate the user's answer.
4. Confirm the functional and basis separately for each unresolved calculation stage, unless the user requests preset combinations. Optimization and final-energy decisions may differ; energies subtracted within one comparison use a consistent final protocol. Selecting a functional does not select a basis. Preserve confirmed choices and offer several applicable alternatives with reasons; there is no fixed three-option cap or universal most-accurate functional.
5. Explain method rationale, limitations and relevant opposing evidence. For saved workflows, store concise candidates/evidence and use decision source `user` for a confirmed choice, `evidence` for a relevant supporting source, and `provisional` for an unconfirmed model proposal. A reference needs its URL/record ID and a relevant claim, not a full paper summary repeated across tasks. Provisional proposals allow planning but do not authorize formal cards. Missing literature does not prevent the user choosing a method.
6. For a saved workflow, create its complete task graph once, keeping purpose, rationale and evidence concise. Save unknown future results as null and include the steps needed for the requested observable. The model still constructs this initial graph; there is no backend recipe or automatic plan builder. Before revising, read the latest `get_aifs_plan` record, then submit `plan_id`, its `expected_version`, `change_reason` and a compact `patch`. `patch.tasks` contains only changed tasks, identified by their existing `task_id`, with only the fields being changed. Supplied `inputs` and `decision` fields merge into the stored objects; omitted fields remain unchanged, and explicit null clears a nullable field. Other lists and dictionaries (including dependencies, evidence lists and `rest_options`) replace that entire field. Add complete new tasks through `patch.add_tasks`; remove tasks through `patch.remove_task_ids` after checking their dependents. The backend validates the merged complete plan and saves a new version. A full `plan` remains a compatibility option; send exactly one of `patch` or `plan`. Resume with `list_aifs_plans` / `get_aifs_plan`.
7. Use `generate_rest_input` for direct delivery or `generate_aifs_task_card` for a saved task. Both perform independent card validation before success. `validate_rest_input` checks an existing or edited card, not a required extra call after successful preparation. Explain backend blockers and correct the parameters; do not substitute another selected method to bypass a limitation.

### Result coordinates and units

For a step awaiting optimization, use a saved workflow with `position_source=prior_result`, its actual `position_from_task` and dependency, leaving coordinates and unit null. The initial geometry or an input card is not an optimization result; do not blindly inherit the starting unit. When the user provides a result, update every intended consumer of that geometry with its coordinates and confirmed unit in one compact patch. After changing the upstream calculation, read the recomputed blockers: old downstream coordinates must not be reused as the new result. Consumers not updated alongside a replaced result return to waiting.

REST `[geom] unit` supports `angstrom` and `bohr`; AIFS writes it explicitly and preserves the coordinate numbers. Record Å/Angstrom as `angstrom`, Bohr/a0 as `bohr`. Do not infer units from distances or perform silent conversions. Unknown units block cards. Historical cards marked `position_unit_status=not_recorded` retain their original body; revise with confirmed units to prepare a new card. These geometry conventions do not establish future output units. Revisit the pinned convention only for a different REST version or contradictory source.

## Evidence supports model reasoning

Use base-model reasoning to propose a useful scientific route; web and local sources strengthen or challenge it. For new evidence, use DSH `web_search`, then `web_fetch` to read a cited source. Reuse applicable already-read sources across related tasks rather than searching for every step again. Local `retrieve_functional_evidence` is supplementary, and an empty store does not stop planning. Do not automatically import web pages into the knowledge graph.

For routine planning use a shared bounded pass: at most two focused searches and three fetch attempts, including retries; stop early with sufficient evidence or after two consecutive fetch failures. Do not pursue shell/network diagnostics to finish a chemistry request. An explicit literature-review request may justify further research. These are model instructions, not DSH timeout controls. After a gap, save a provisional proposal, explain its assumptions and obtain any needed method confirmation; omit unverified experimental numbers and invented error estimates.

When saving a workflow, web references use `source=web`, URL, title, precise `note` and `claim_type`: `method_used`, `comparative_benchmark`, `author_recommendation` or `other`. They remain uncurated. Local references need `source=local` and `record_id`. A method's use in a paper is not proof of comparative superiority. Keep opposing evidence and scope/protocol differences. Do not label a user choice or model suggestion as a literature recommendation.

## Confirm through DSH

Use the current `ask_user_question` tool when available, following its actual schema and limits. Provide concise headings, scientifically justified options and short reasons/cost tradeoffs; allow custom answers and place a recommended option first when justified. Batch independent questions. Resolve functional-dependent basis choices after the functional answer. A preselection, pending/failed call, cancellation or “不确定” is not confirmation. If the panel tool is unavailable, ask briefly in chat and state that limitation.

## Deliver the result accurately

Before replying, check current task decisions, geometry sources, analysis formulas, blockers and actual card results. Read the current plan if needed. Preserve species, geometry labels, coefficients and ZPE sources in equations; explain and revise a scientifically wrong saved formula instead of treating it as authoritative. A valid card or saved analysis task is not a completed calculation or proof of an available run environment.

Use concise scientific step names and plain-language progress. Deliver the actual prepared `.in` files, say which later steps await results, and give the next required information/action. Explain a literature gap briefly. Keep internal IDs, statuses, hashes and API details for requested debugging/audit. Use normal Markdown. A task awaiting optimization results needs those results; it does not need a generic preview-versus-wait menu.

For a beginner, when first introducing a task-relevant scientific term in this conversation, give a readable name and one short explanation. For example, use **ADE（含零点能修正的绝热电子脱附能）** for ADE_0; if 0–0 is relevant, explain that both species are in their lowest vibrational levels. Explain other terms according to the actual task. Preserve correct formulas and terminology, reuse the short name for terms already explained in this conversation, and expand when the user asks.

With DSH write/present tools, resolve the returned `export_relative_path` under the permitted workspace, create its parent directories through the permitted file tools, and export the exact `rest_input` (direct card) or `content` (saved card). Present the resulting file. The backend chooses stable calculation/plan/task directories and versioned filenames; use that path for subsequent steps too. If a file already exists there, read it: identical content is reused; different content is an export conflict, reported without overwriting it. Never claim file export succeeded before the write succeeds. Direct cards have no backend download URL or plan history; if file tools are unavailable, show the validated body. Saved cards also support a current download URL. On an expired saved-card link, use `get_aifs_card` for current content/URL and export or display it; do not regenerate the science just to repair delivery.

A saved card can come from an older version yet still match the current task. Use `is_applicable_to_current_plan` when deciding whether it can be used now; `is_current_plan_version` only describes its original version. Reuse a card the backend marks applicable, rather than regenerating an unchanged input. If it is not applicable, keep it as history and prepare the current task's card only when ready.

AIFS tool availability, backend readiness and installed package state are distinct facts. On a missing/failed operation, report that saving or card generation remains pending, continue the useful scientific proposal and offer one recovery action supported by the observed error. A Markdown plan or shell-written card does not replace an AIFS record. Export a planning document only when requested; an explicitly requested manual draft is marked unsaved/unvalidated.

After a failed/interrupted tool call, read the current saved plan before retrying: an earlier successful call may already have saved a version or card. A transport or JSON parsing failure is not confirmation of a successful write. Use only declared schema fields for the next request.

## Plan contract example


The tools expose full draft and partial revision schemas. Use those schemas without searching the workspace for backend files. `goal` is one of `reaction_energy`, `binding_energy`, `optimization_single_point`, `force`, `dipole`, `other`. `job_type` for supported REST tasks is `energy`, `opt`, `force`, or `numerical dipole`. `position_source` is `user`, `external_optimized`, or `prior_result`; charge/spin sources are `user` or `external`. A newly created candidate or decision requires `rationale`; a patch preserves its existing rationale when omitted. Do not submit `status`, plan IDs, versions or card metadata inside a draft; the backend derives them.

Example: the user supplies H2 in Angstrom, charge 0, multiplicity 1 and explicitly requests PBE/def2-TZVP optimization followed by XYG7/def2-TZVPP energy. This illustrates separate confirmed methods, not a universal recommendation. Only optimization is initially eligible for a card. For the later revision, fill the single-point `position` and `position_unit` from the user's actual optimization result.

```json
{
  "question": "Optimize H2 with PBE/def2-TZVP, then evaluate energy with user-selected XYG7/def2-TZVPP",
  "goal": "optimization_single_point",
  "tasks": [
    {
      "task_id": "opt_H2", "title": "Optimize H2", "purpose": "Obtain optimized coordinates",
      "kind": "rest", "depends_on": [], "system_name": "H2", "job_type": "opt",
      "inputs": {
        "position": "H 0 0 0\nH 0 0 0.74", "position_unit": "angstrom", "position_source": "user",
        "charge": 0, "charge_source": "user", "spin": 1, "spin_source": "user"
      },
      "decision": {"xc": "PBE", "basis": "def2-TZVP", "source": "user", "rationale": "Explicit user choice; no literature ranking claimed."}
    },
    {
      "task_id": "sp_H2", "title": "Single-point H2 energy", "purpose": "Use the optimized geometry",
      "kind": "rest", "depends_on": ["opt_H2"], "system_name": "H2", "job_type": "energy",
      "inputs": {
        "position": null, "position_unit": null, "position_source": "prior_result", "position_from_task": "opt_H2",
        "charge": 0, "charge_source": "user", "spin": 1, "spin_source": "user"
      },
      "decision": {"xc": "XYG7", "basis": "def2-TZVPP", "source": "user", "rationale": "Separate user-selected final-energy method on PBE-optimized geometry; wait for optimized coordinates and their unit."}
    }
  ],
  "assumptions": ["Electronic energy only; calculations are run outside AIFS."]
}
```

### Compact revision example

If the latest saved version is 1 and the user supplies the actual optimized coordinates below in Bohr, only `sp_H2.inputs` changes. Use the real saved plan ID in place of the placeholder:

```json
{
  "plan_id": "<saved-plan-id>",
  "expected_version": 1,
  "change_reason": "User supplied optimized coordinates and confirmed Bohr",
  "patch": {
    "tasks": [{
      "task_id": "sp_H2",
      "inputs": {"position": "H 0 0 0\nH 0 0 1.4", "position_unit": "bohr"}
    }]
  }
}
```

The stored method, charge, multiplicity, geometry source, dependencies and optimization task are preserved. For a basis-only change, the task update is `{"task_id":"sp_H2","decision":{"basis":"def2-TZVP"}}`; it preserves the chosen functional and evidence. A new decision where none existed needs its complete required fields. A new frequency/ZPE step needs a complete entry in `add_tasks` and any changed analysis formula/dependency list in `tasks`, rather than a repeated full workflow.

REST card validation checks format and the current catalog. It does not run a calculation or prove that the basis files and executable exist on the user's computer.
