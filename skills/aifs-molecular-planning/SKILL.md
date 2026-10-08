---
name: aifs-molecular-planning
description: Turn a REST calculation request into task-level method choices, a saved AIFS plan and validated input cards. Use for functional/basis selection and multi-step molecular or supported REST property workflows.
---

# AIFS REST planning

AIFS prepares calculation plans and input files. DSH supplies the model, conversation, web tools, selection panels and file delivery. The model proposes the science; AIFS checks structured inputs, dependencies and integrated REST contracts. AIFS does not run calculations, parse results or certify free-text scientific formulas.

## Load only the relevant detail

Resolve relative files against the directory `resourceBase` returned by DSH's Skill loader, not the user's workspace. Read:

- [methods.md](references/methods.md) when proposing or confirming functionals/bases: per-stage choices, exact variants, double hybrids and derivative limits.
- [observables.md](references/observables.md) for energy differences, experimental comparison, ZPE/thermal corrections or spectroscopy. Plan from the quantity and actual states, not a test molecule.
- [rest-operations.md](references/rest-operations.md) for frequencies, thermochemistry, multipoles, excited states, TS/IRC, constraints or RRS-PBC. Pair the mapping with the current capability tool; AIFS integration gaps are not proof that REST lacks a feature.

Use the complete create/revise tool schemas. The user's workspace need not contain backend source. Query `get_rest_capabilities` before offering REST-ready choices; reuse that result and query only relevant sections for exact types, units and operation limits.

## Prepare and save the workflow

1. Identify the requested observable and species/states, available structures, confirmed methods and precision/cost constraints. Explain plausible interpretations in plain language. Ask only about unresolved information that changes the calculation. Keep unsupported operations as explicit pending steps, preserving their purpose and dependencies.
2. Build tasks with stable IDs, named scientific purposes and `depends_on`. Reaction differences need participating species and stoichiometry; binding differences need complex/fragments and geometry/BSSE assumptions. Later single points, frequencies or properties use the required structure, not a guessed result.
3. Store unknown values as null. Record proposed charge/multiplicity in notes/assumptions with the scientific rationale; only fill confirmed inputs and their source fields. `charge` is net charge; `spin` is multiplicity 2S+1. A user-confirmed proposal has source `user`; `external` requires an actual external record.
4. Confirm the functional and basis separately for each unresolved calculation stage, unless the user requests preset combinations. Optimization and final-energy decisions may differ; energies subtracted within one comparison use a consistent final protocol. Selecting a functional does not select a basis. Preserve confirmed choices and offer several applicable alternatives with reasons; there is no fixed three-option cap or universal most-accurate functional.
5. Save candidates and task-level evidence with their rationale, limitations and opposing evidence. Use decision source `user` for a confirmed choice, `evidence` for a relevant supporting source, and `provisional` for an unconfirmed model proposal. Provisional proposals allow planning but do not authorize formal cards. Missing literature does not prevent the user choosing a method.
6. Call `create_aifs_plan` before multi-step card generation. To change a plan, use the latest `get_aifs_plan` record and `revise_aifs_plan` with its expected version and the complete revised draft. Preserve stable task IDs and previous records. Resume with `list_aifs_plans` / `get_aifs_plan`.
7. Generate a saved task's card with `generate_aifs_task_card` only when the backend permits it. That operation independently validates and saves the card. An isolated `generate_rest_input` needs `validate_rest_input` before claiming validation. Explain backend blockers and correct the parameters; do not substitute another selected method to bypass a limitation.

### Result coordinates and units

For a step awaiting optimization, use `position_source=prior_result`, its actual `position_from_task` and dependency, leaving coordinates and unit null. The initial geometry or an input card is not an optimization result. When the result arrives, record its own confirmed coordinates/unit; do not blindly inherit the starting unit.

REST `[geom] unit` supports `angstrom` and `bohr`; AIFS writes it explicitly and preserves the coordinate numbers. Record Å/Angstrom as `angstrom`, Bohr/a0 as `bohr`. Do not infer units from distances or perform silent conversions. Unknown units block cards. Historical cards marked `position_unit_status=not_recorded` retain their original body; revise with confirmed units to prepare a new card. These geometry conventions do not establish future output units. Revisit the pinned convention only for a different REST version or contradictory source.

## Evidence supports model reasoning

Use base-model reasoning to propose a useful scientific route; web and local sources strengthen or challenge it. For new evidence, use DSH `web_search`, then `web_fetch` to read a cited source. Reuse applicable already-read sources across related tasks rather than searching for every step again. Local `retrieve_functional_evidence` is supplementary, and an empty store does not stop planning. Do not automatically import web pages into the knowledge graph.

For routine planning use a shared bounded pass: at most two focused searches and three fetch attempts, including retries; stop early with sufficient evidence or after two consecutive fetch failures. Do not pursue shell/network diagnostics to finish a chemistry request. An explicit literature-review request may justify further research. These are model instructions, not DSH timeout controls. After a gap, save a provisional proposal, explain its assumptions and obtain any needed method confirmation; omit unverified experimental numbers and invented error estimates.

Save web references with `source=web`, URL, title, precise `note` and `claim_type`: `method_used`, `comparative_benchmark`, `author_recommendation` or `other`. They remain uncurated. Local references need `source=local` and `record_id`. A method's use in a paper is not proof of comparative superiority. Keep opposing evidence and scope/protocol differences. Do not label a user choice or model suggestion as a literature recommendation.

## Confirm through DSH

Use the current `ask_user_question` tool when available, following its actual schema and limits. Provide concise headings, scientifically justified options and short reasons/cost tradeoffs; allow custom answers and place a recommended option first when justified. Batch independent questions. Resolve functional-dependent basis choices after the functional answer. A preselection, pending/failed call, cancellation or “不确定” is not confirmation. If the panel tool is unavailable, ask briefly in chat and state that limitation.

## Deliver the result accurately

Before replying, check current task decisions, geometry sources, analysis formulas, blockers and actual card results. Read the current plan if needed. Preserve species, geometry labels, coefficients and ZPE sources in equations; explain and revise a scientifically wrong saved formula instead of treating it as authoritative. A valid card or saved analysis task is not a completed calculation or proof of an available run environment.

Use concise scientific step names and plain-language progress. Deliver the actual prepared `.in` files and give the next required information/action. Explain a literature gap briefly. Keep internal IDs, statuses, hashes and API details for requested debugging/audit. Use normal Markdown. A task awaiting optimization results needs those results; it does not need a generic preview-versus-wait menu.

For a beginner, when first introducing a task-relevant scientific term in this conversation, give a readable name and one short explanation. For example, use **ADE（含零点能修正的绝热电子脱附能）** for ADE_0; if 0–0 is relevant, explain that both species are in their lowest vibrational levels. Explain other terms according to the actual task. Preserve correct formulas and terminology, reuse the short name for terms already explained in this conversation, and expand when the user asks.

With DSH write/present tools, export the exact AIFS card `content` using its `filename` to the permitted workspace and present it. Preserve the body and provenance. Otherwise provide the current download URL; show the saved body when requested. On an expired localhost link, use `get_aifs_card` for current content/URL and export or display it; do not regenerate the science just to repair delivery.

AIFS tool availability, backend readiness and installed package state are distinct facts. On a missing/failed operation, report that saving or card generation remains pending, continue the useful scientific proposal and offer one recovery action supported by the observed error. A Markdown plan or shell-written card does not replace an AIFS record. Export a planning document only when requested; an explicitly requested manual draft is marked unsaved/unvalidated.

## Plan contract example


The create/revise tools expose the complete nested schema. Use that schema without searching the workspace for backend files. `goal` is one of `reaction_energy`, `binding_energy`, `optimization_single_point`, `force`, `dipole`, `other`. `job_type` for supported REST tasks is `energy`, `opt`, `force`, or `numerical dipole`. `position_source` is `user`, `external_optimized`, or `prior_result`; charge/spin sources are `user` or `external`. Candidates and decisions both require `rationale`. Do not submit `status`, plan IDs, versions or card metadata inside a draft; the backend derives them.

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

REST card validation checks format and the current catalog. It does not run a calculation or prove that the basis files and executable exist on the user's computer.
