---
name: aifs-molecular-planning
description: Plan molecular REST calculations from a research question, record task-level method evidence, and prepare validated AIFS input cards. Use for molecular REST workflows, functional selection, electronic energies, optimization, force, dipole, frequency/thermochemistry, transition-state/IRC and excited-state planning.
---

# AIFS molecular planning

Use AIFS plan tools for durable work. The chat explanation is not the plan record. This skill helps propose tasks; the AIFS backend checks dependencies, missing inputs, REST capability and cards.

For normal calculation requests, the saved plan is the AIFS tool record and the formal input card is the AIFS-generated, independently validated file. A separate Markdown plan is an optional export when requested. If AIFS tools are unavailable or return a failure, continue explaining the scientific proposal, identify the unfinished saving/card step, and give a relevant recovery action supported by the observed condition. Do not replace unavailable AIFS operations with shell-written cards. An explicitly requested manual draft is labeled unvalidated and unsaved. Installation, backend readiness and current conversation tool access are separate facts; unavailable tools alone do not prove that the user disabled the plugin.

Use your molecular reasoning to interpret the goal, propose a task graph and compare candidate parameters and methods. Web sources and the local knowledge base strengthen or challenge that reasoning. Unavailable retrieval or an empty knowledge base still permits a useful provisional proposal, with assumptions, reasons and uncertainty.

For missing charge or multiplicity, offer candidates conditional on the species, ionization and electronic state when those facts support a proposal. Explain what the user must confirm or supply to distinguish alternatives. Save unconfirmed proposals in task `notes` or plan `assumptions`, leaving the corresponding input values and source fields null. A user-confirmed suggestion uses source `user`; `external` requires an actual supplied external record. Coordinates and units need their own confirmation. Save model-proposed methods in `candidates` with a rationale; without references or user approval, use decision source `provisional` and empty evidence lists. Preserve the reasoning when the user confirms a method and its source becomes `user`.

1. Identify the requested quantity, molecular species, structures, charge, spin, precision/cost constraints and any method the user has explicitly chosen. Keep unknowns unknown. Distinguish electronic energy from enthalpy or free energy.
2. Draft REST calculation tasks and non-REST analysis tasks with stable IDs and explicit `depends_on`. For reaction electronic energy, include energy jobs for each species and an analysis task expressing the stoichiometric combination. For binding electronic energy, include complex and fragment energy jobs and a combination task; state the geometry and BSSE assumptions. For optimization followed by single-point energy, make the energy task depend on optimization. Force and numerical dipole map to their respective REST `job_type`.
3. If a step needs optimized coordinates that do not exist yet, leave `position` empty and explain that the card waits for the preceding result. Never use starting coordinates while calling the task “optimized-geometry single point.” For advanced operations, query `get_rest_capabilities` and the required section contract. Use the mappings below and backend blockers. Preserve operations still listed as pending as `kind=unsupported`, with their scientific purpose, dependencies and missing inputs. Do not say all REST versions lack them or invent a replacement card.
4. Associate applicable evidence with each task and method decision. Reuse sources already read in this plan/conversation when their system, electronic state, method and property match; related optimization and energy steps do not require separate searches for the same paper. For new evidence, start with DSH `web_search`, then `web_fetch` before citing a source; a snippet alone is insufficient. Search local AIFS records with `retrieve_functional_evidence` as a useful supplement or fallback, never as a prerequisite. Do not automatically import pages into the local evidence graph.
5. Save each cited web reference as `source=web` with URL, title, a precise `note`, and `claim_type` (`method_used`, `comparative_benchmark`, `author_recommendation`, or `other`). Use `source=local` with `record_id` for an imported record. State whether a paper merely used a method, compared methods under a relevant benchmark, or offered an author recommendation. Mere use is not a comparative result. Record relevant alternatives in each task's `candidates`, including supporting and opposing sources; retain system/protocol differences and uncertainty. Web sources remain uncurated even after reading them.
6. Set the chosen decision's `source` to `user` when the user selected it; to `evidence` only with supporting references whose scope matches the task; to `provisional` when search yields no relevant basis or conflicts remain unresolved. A provisional choice does not produce a card until the user confirms a method or evidence resolves it. Do not present user choice or thin evidence as a literature recommendation.
7. Call `create_aifs_plan` and explain the saved workflow using scientific step names and actionable progress. Use `get_aifs_plan` before a revision and `revise_aifs_plan` with the current version and complete revised plan. For each `ready_for_card` REST task, call `generate_aifs_task_card`; provide its actual `.in` download link. The saved-card tool already independently validates the card. Use `list_aifs_plans` and `get_aifs_plan` to resume later.

## Bounded evidence retrieval

For routine planning/card preparation, first explain the proposed scientific route. Use one shared evidence pass for the plan: at most two focused `web_search` calls and three `web_fetch` attempts total, including retries. Stop earlier when adequate relevant evidence is read. After two consecutive fetch failures/timeouts, stop web retrieval rather than cycling through mirrors/aggregators, inspecting network configuration or substituting shell fetches. These limits guide the model; AIFS does not control DSH's network timeout.

If evidence remains insufficient, explain the unverified gap, save a provisional plan, and offer a reasoned method proposal for user confirmation through `ask_user_question` when available. An unavailable exact experimental reference does not block explaining ADE/VDE or planning calculations; omit unverified numerical values and error estimates. Do not claim unread pages were verified. Confirmed parameters, card generation, file exports and download repair reuse applicable recorded evidence instead of starting research again. Revisit evidence when scientific scope changes or a conflict matters. Expand retrieval when the user explicitly requests a literature review, exhaustive comparison or additional verification.

## Task-specific methods and REST-first choices

Before literature retrieval or a method-choice panel, query `get_rest_capabilities` for exact integrated names/parsers and the needed operation contracts. Prefer methods that AIFS can express for that REST task. For accurate electronic-energy work, assess supported double hybrids such as XYG3/XYG7 and include one as an option when scientifically applicable. Explain exclusion if electronic structure, correlation assumptions, basis convergence, derivative coverage or resources make it unsuitable. Do not put unsupported wB97X-D or CCSD(T) in an ordinary REST-ready choice panel; an outside-REST reference calculation, if useful, is clearly separate. If the capability call fails, compatibility remains unchecked and the proposal provisional.

For the geometry panel, assess methods for structure optimization itself: supported GGA/meta-GGA candidates such as PBE, TPSS, r2SCAN/SCAN; conventional hybrids such as TPSSh, PBE0/SCAN0; appropriate range-separated and double hybrids. TPSS is a meta-GGA without exact exchange, whereas TPSSh is a distinct hybrid. A request for TPSS or broader optimization choices should expose applicable candidates as selectable options, with reasons for any exclusions. Neither a family label nor metal-cluster membership alone establishes geometry accuracy; filter by electronic state, derivative coverage and resources rather than listing the entire catalog.

DSH selection panels have no fixed three-option cap. When the user requests broader or higher-accuracy choices, expand the functional shortlist as useful (for example four to six applicable candidates), rather than truncating it to three or adding unsuitable methods to fill a quota. For suitable electronic-energy tasks, offer XYG3, XYG7 and/or XYGJOS as distinct selectable double-hybrid candidates with reasons and cost/uncertainty; mentioning them only in surrounding prose does not make them selectable. Their family alone does not establish higher accuracy for this system.

Geometry choices may include an applicable double hybrid using the reviewed numerical-force route: set `rest_options.ctrl.numerical_force=true` if selected, explain its higher optimization cost, and check the electronic state and operation restrictions. Do not imply analytic Hessian or TDDFT coverage for these methods. If a candidate is inappropriate for the optimization, explain why and consider it independently for the final single-point task. Preserve already confirmed choices.

### Separate functional and basis choices

Use separate questions for the functional and orbital basis, rather than options that lock them into preset pairs. First confirm unresolved functionals for the relevant stages (`geometry_xc`, `energy_xc`), then present basis questions (`geometry_basis`, `energy_basis`) appropriate to those selected functionals. Batch independent questions within the actual DSH tool limits; wait for functional answers before presenting method-dependent basis alternatives. Labels in a functional question name functionals; labels in a basis question name bases. Preserve an explicit user-selected pair and any already confirmed component, asking only for what is missing.

Offer several suitable basis candidates when the scientific conditions permit; expand beyond three when useful for a requested comparison, with short explanations of convergence, cost and diffuse-function needs; allow a custom answer. A selected functional does not silently select its default basis. If only one applicable option is justified, explain why rather than fabricating choices. For example, a neutral small-molecule optimization may compare def2-SVP, def2-TZVP and def2-TZVPP when appropriate; an anion detachment-energy calculation needs a separately justified diffuse-basis comparison, not the same neutral-molecule menu. These are conditional examples, not mandatory lists or accuracy rankings. Check element coverage, selected method requirements and the target observable. REST input capability does not prove the corresponding basis files exist locally. Save the confirmed functional/basis pair on each task only after both answers; unresolved components remain unknown and block formal cards.

Optimization and subsequent energy tasks have independent `decision` objects. They may use different functionals, bases and reasons. When neither is selected, ask separately for the geometry method and the final energy method; preserve already confirmed choices. Do not propagate a selected method to every task automatically.

For ADE/VDE, reaction and binding energies, all total energies in a given difference must share the final functional, basis, dispersion and compatible numerical settings; charges and multiplicities remain appropriate to each species. If geometry optimization uses another method, create final-energy tasks for each required species and geometry. For ADE/VDE: optimize anion and neutral geometries at the chosen geometry method, then evaluate anion at anion geometry, neutral at neutral geometry, and neutral at anion geometry at the chosen final-energy method. ADE_electronic = E(neutral, neutral geometry) − E(anion, anion geometry); VDE_electronic = E(neutral, anion geometry) − E(anion, anion geometry). Never mix energies from different methods in the same difference. Record the geometry approximation; alternate energy methods are separate comparisons. The backend validates cards and dependencies, not the scientific meaning of a free-text combination formula.

### Plan corrections from the target observable

Start from **what the user wants to obtain or compare**, for any molecular system. Do not require a novice to name ZPE, a functional, a charge/spin state or a task sequence in the opening question. Infer plausible interpretations from the physical process and experimental context, explain them briefly, and ask only for information that changes the plan. Record the observable, comparison convention, physical states and unresolved assumptions in task `purpose`/`notes` and plan `assumptions`. Neither “compare with experiment” alone nor a system name fixes the workflow or method.

| Requested quantity | Required planning |
| --- | --- |
| Electronic energy or an explicitly electronic reaction/binding/detachment difference | Consistent final electronic energies; no automatic ZPE/thermal tasks; label the result electronic only |
| Experimental vibrational 0–0 ADE/adiabatic electron affinity, adiabatic ionization threshold, or a 0 K dissociation/reaction quantity including nuclear zero-point motion | Optimized states plus frequency/ZPE sources for every participating molecular species; combine electronic energies and the stoichiometric ZPE difference |
| Vertical detachment/ionization electronic energy gap | Both electronic states at the specified initial-state geometry; do not automatically add equilibrium-geometry ZPE differences |
| Finite-temperature enthalpy, free energy or equilibrium constant | Appropriate frequencies and thermal/entropy treatment, with temperature, pressure/standard state and relevant low-frequency/conformer assumptions; ZPE alone is insufficient |
| A photoelectron band envelope or a full absorption/XPS spectrum | Identify the spectroscopy and transitions first; arrange the appropriate excited-state/vibrational/intensity/broadening treatment or pending external steps; electronic energy differences alone are not a spectrum |

If the experimental observable is unclear, use a concise DSH question panel when available, with plain explanations such as threshold, band position or full spectrum. Do not ask the user to decide whether a physically required correction exists. Do not ask again when the scope is already clear. Preserve explicit electronic-only scope; do not promise a 0–0 comparison for an uncorrected energy. If a correction is required, **save its calculation/source and analysis tasks**, not just a reminder after delivering cards.

For a zero-point-corrected energy difference, use the process stoichiometry:

`delta_E_0 = sum(products: coefficient * (E_electronic + ZPE)) - sum(reactants: coefficient * (E_electronic + ZPE))`

The ZPE correction can have either sign. Atomic species and a free electron have no molecular vibrational ZPE; record that physical zero instead of inventing an atomic frequency job. Include every required molecular state/fragment with its own identity and dependencies; do not always add exactly two frequency tasks.

For **molecular electron detachment** specifically, the reusable pattern is:

`ADE_0 = E(neutral, neutral geometry) - E(anion, anion geometry) + ZPE(neutral) - ZPE(anion)`

`VDE_electronic = E(neutral, anion geometry) - E(anion, anion geometry)`

For two molecular species this adds an anion frequency task depending on its optimization and a neutral frequency task depending on its own optimization. The corrected ADE analysis directly depends on both final-energy tasks and both ZPE sources, with the explicit formula in `analysis_formula`; an optional separate analysis reports `ADE_electronic`. VDE analysis depends on the two energies at the anion geometry. These roles apply across systems: choose actual task IDs, electron states, methods and bases from the problem, retaining original stable IDs when revising a saved plan. Do not copy a test cluster's charge, multiplicity, geometry, functional or basis.

Frequency cards use `job_type=energy` with the supported Hessian section/driver, not an invented `job_type=frequency`. For each missing optimized geometry, use `position_source=prior_result` and the corresponding `position_from_task`/`depends_on`; keep coordinates/unit null until its real result arrives. Choose a consistent frequency method/basis/scaling protocol for the participating species, normally the confirmed geometry protocol when its Hessian is supported. Frequency and final-energy decisions are independent. Query derivative coverage for each actual electronic state: open-shell needs the reviewed unrestricted analdrv route rather than the closed-shell native Hessian; post-SCF and unverified VV10 Hessians remain blocked. If a frequency protocol is unsuitable, propose a separately confirmed supported protocol or an external frequency source; never silently replace the method or assume a high-level energy method has an available Hessian.

For a supported full-molecule frequency protocol, request the thermo ZPE report; `thermo.sclzpe=1.0` explicitly records unscaled harmonic ZPE when no justified scaling factor is chosen. For the analdrv route use `ctrl.analdrv_tasks=["hessian"]` and omit `atm_list` to cover all atoms. Native and analdrv routes still obey their respective contracts. Record any justified scaling factor, changed frequency method and approximation. The thermo section's default finite-temperature outputs do not change a requested 0 K observable. Combine the separately reported ZPE correction with the chosen final electronic energies, not frequency-method `E+ZPE` totals or Gibbs/enthalpy corrections.

After external calculations, request all required energies/ZPE **with their units, species/state, method and frequency/minimum check**. Exclude translation/rotation from harmonic ZPE. For an equilibrium structure, significant imaginary vibrational modes mean the minimum is not established; do not take absolute frequencies or discard problematic modes to manufacture a valid comparison. Transition-state frequency interpretation is a separate saddle-point workflow. Convert units explicitly with a recorded source before combination. Do not invent frequencies or ZPE from prepared cards. Save unresolved result requirements in the analysis task's notes and describe it as awaiting results even though the backend labels it `analysis_only`.

AIFS currently saves tasks/formulas and prepares input cards; it does not run frequencies, parse results or evaluate free-text formulas. A detailed vibronic VDE/spectral comparison needs its own stated experimental convention and vibrational/Franck–Condon treatment; do not apply the equilibrium ADE correction to ordinary VDE automatically.

Definition reference for molecular ADE: [neutral-minus-anion ZPE correction to the 0–0 transition](https://pubs.rsc.org/en/content/articlehtml/2020/cp/d0cp05204c). This defines an observable, not a functional recommendation for any particular system.

Compare methods against the user's actual observable and molecular system. Do not default every request to PBE0, or infer accuracy from a method's age, popularity or rung. When a comparison matters, choose a few justified alternatives: a relevant conventional hybrid, a range-separated method (for example ωB97X, ωB97X-V or ωB97M-V when applicable), and a double-hybrid/post-SCF method such as XYG3/XYG7 only if the system and resource constraints fit. Explain inclusion/exclusion, basis and convergence considerations, and relevant opposing evidence. Retain favorable PBE0 evidence when it applies. Broad molecular benchmarks or averages over a cluster series do not determine the best method for a specific Al-cluster ADE/VDE.

Exact variants matter: ωB97X, ωB97X-D, ωB97X-V and ωB97M-V are different methods. Do not replace one with another or recreate it by arbitrary dispersion settings. LibXC naming support alone does not establish that the calculation engine evaluates all required range-separated exchange, nonlocal correlation or gradients.

Query `get_rest_capabilities` to distinguish current AIFS coverage from official REST capabilities. The legacy path includes wB97X and CAM-B3LYP; the reviewed `parse_xc` path includes wB97X-V, wB97M-V, wB97X-D3, wB97X-D3BJ and wB97M-D3BJ. Put the chosen parser in `decision.xc_parser`. The exact supported list and limits come from the tool. wB97X-D is explicitly rejected by the pinned upstream parser and must not become wB97X-D3. Never substitute PBE0. Source review is not numerical calculation verification; current REST source wires VV10 energy, while its analytic derivative/response combinations remain restricted in AIFS pending verification.

Bare LDA is a family label, not an accepted legacy functional at the pinned source. If that is all the user specifies, discuss an explicit choice such as SVWN or PW-LDA and confirm it; do not silently rename it.

## Advanced REST input mapping

Use `get_rest_capabilities` once for the current coverage; query `section` for only the needed keyword schema. This is local and does not consume a literature-search round. Do not search packaged source code for schemas. REST operations are activated by sections as well as `job_type`:

| User's task | Saved task settings | Required checks |
| --- | --- | --- |
| Harmonic frequencies | `job_type=energy`, `rest_options.hessian={frequencies:true}` | Confirm geometry and method; the current native Hessian contract is closed shell |
| Open-shell/RSH/mGGA frequencies | `job_type=energy`, `rest_options.ctrl={analdrv_tasks:["hessian"]}`, optional `rest_options.analdrv` | Explicitly choose the newer analdrv path; no ROHF, post-SCF Hessian or unverified VV10 derivatives; do not replace the method |
| Thermal corrections/free energy | Hessian plus `rest_options.thermo` | Temperature K, pressure atm, appropriate optimized geometry; finite/positive values and RRHO limitations |
| Electric multipoles | `job_type=energy`, `rest_options.ctrl={analdrv_tasks:["multipole"]}`, `rest_options.analdrv` | Orders 1–4; origin in Bohr regardless of geometry unit; post-SCF is limited to reviewed restricted PT2 methods without frozen core |
| TDDFT excitation energies | `job_type=energy`, `rest_options.tddft` | Restricted triplet/both needs AO mode; unrestricted reference must omit `tddft_spin` |
| Frequency-domain polarizability/response | `job_type=energy`, `rest_options.tddft={response_tddft:true,external_field_freq:0.1}` for a confirmed 0.1 Hartree frequency | Restricted reference; damping in Hartree and response grid in Bohr; this run skips excitation eigenvalues |
| FEAST excitation solver | `job_type=energy`, `rest_options.tddft={tddft_feast_solver:true}` plus confirmed range/solver settings | Restricted MO mode, ordered Hartree interval; not unrestricted/AO |
| PySOC transition export | `job_type=energy`, `rest_options.tddft={pysoc:true,tddft_spin:"both",tddft_mode:"ao"}` | Restricted reference; prepares an export, not a completed SOC spectrum |
| Excited-state force | `job_type=force`, `rest_options.tddft={tddft_grad_state:1}` for confirmed first excited state | Restricted single channel, reviewed HF/LDA/GGA/ordinary hybrid, root within nroots; eigenvalue run required; no RSH/mGGA, response, FEAST, combined-spin gradient or excited-state optimization |
| One-/two-dimensional RRS-PBC | `job_type=energy`, `rest_options.geom` with `rrs_pbc=true`, `pbc_dim`, `unit_cell_index`, `rrs_pbc_vec`, `max_step`, `k_points` | Closed shell; zero-based core-cell indices, vector unit follows geometry; finite-cluster post-SCF reconstruction, not periodic SCF; 3D sampling pending |
| Transition-state optimization | `job_type=opt`, `rest_options.geometric_pyo3={transition:true,hessian:"first"}` | Appropriate initial geometry; later confirm the saddle by frequency/IRC, never claim a TS from card generation |
| IRC | `job_type=opt`, geometric section `irc=true`, `irc_direction` | Requires a suitable transition-state geometry; preserve result dependencies |
| Frozen atoms | Five-column geometry `Element fix x y z` | `0` fixed / `1` movable; geometric-pyo3 and tric/dlc/hdlc coordinates |
| VV10 method optimization | Reviewed parse_xc method plus `rest_options.ctrl={numerical_force:true}` | Slower numerical derivative; no added D3/D4, no claim of verified analytic VV10 derivatives |

Put extra tables in `PlanTask.rest_options`, keyed by exact section name, for example `{"hessian":{"frequencies":true},"thermo":{"temperature":298.15,"pressure":1.0}}`. The backend preserves them in plan revisions and card provenance. It rejects unknown keys and attempts to override the core method, coordinates, charge or multiplicity. A section's presence can trigger an operation even if empty; avoid inserting empty sections by habit. `convergence_*` is the actual geometric convergence keyword prefix read by the pinned source; do not copy README's obsolete `converge_*` spelling.

`[analdrv]` alone only configures the driver: use the **array** `ctrl.analdrv_tasks=["hessian"]` or `["multipole"]` to request a property. Native and analdrv Hessians are alternative routes. Thermochemistry with analdrv requires all atoms; a partial atom Hessian is not a full molecular free-energy calculation. Split stability, frequency-domain response, FEAST and excited-state gradient requests into suitable separate tasks. Do not attach the gradient to a FEAST/response-only run that lacks the required eigenvectors. Query the latest section schema and honor blockers for each combination.

Optimization-result dependencies still apply to later frequency, thermochemistry, or excited-state tasks. Keep coordinates/unit unknown until the genuine result arrives; neither an input file nor an energy-only result proves a successful optimization. Native thermo pressure is **atm**, geometric `thermo=[T,P]` pressure is **bar**. Do not silently convert user quantities without recording the conversion and its source.

GW/BSE, MD/AIMD/QM-MM/pure-MM, 3D RRS-PBC sampling, multipole density export and advanced excited-state optimization/gradient combinations remain integration gaps. Use the capability tool's latest pending list rather than generalizing a gap to an entire method family. Explain pending scientific steps and preserve requirements; do not generate a replacement card for the requested unintegrated operation. A requested theoretical spectrum needs the appropriate excited-state/transition-intensity analysis and broadening; ground-state total energies alone are not a simulated XPS/absorption spectrum.

## Replies for the calculation user

Start with what has been prepared for the requested scientific goal. Show a concise step list or table using calculation names, the chosen or provisional method, and plain-language progress based on the latest tool outcomes. Provide generated-file download links and the next needed information or action. Explain method reasoning, relevant evidence and uncertainty when these affect the choice.

Prefer actual `.in` file attachments when DSH file write/present tools are available: export the exact saved AIFS `content` using its `filename` to the permitted workspace, then present it. This copies an already validated card; it does not replace AIFS generation with a manually written card. Preserve the original body and provenance. If file delivery is unavailable, provide the current download URL. If the user requests the card directly, display its saved content in chat. Localhost URLs can expire across backend restarts; on download failure use `get_aifs_card` for current content/URL and export or show the body, rather than regenerating a card or repeating a broken URL.

Give the recommended next action directly. Ask only for unresolved scientific inputs or decisions that affect the calculation. A confirmed plan does not need a generic “accept this or choose another method” menu; alternatives are useful when tied to precision, cost or unresolved evidence.

For necessary confirmation, prefer DSH `ask_user_question` when available in the current conversation. Batch independent unresolved questions into one call using the actual tool schema: stable `id`, concise Chinese `question`/`header`, and `options` with short `label` and meaningful `description`. Put the recommended option first with the tool's recommended-label convention; allow custom answers. For water, electronic-state confirmation and functional choice can share a panel; basis choice is a separate question after the functional answer, with multiple suitable alternatives and their tradeoffs. Offer numerical charge/spin candidates only when scientifically justified, and let an unsure user request help rather than confirm a guessed state. Read the submitted selected/custom answers, then revise the plan and produce eligible cards. A preselected option, pending/timeout, cancellation or “不确定” does not confirm parameters. Do not repeat already confirmed questions. If the tool is missing or fails, ask briefly in chat, state the actual limitation and do not claim that a panel opened.

For optimization followed by single-point energy, a normal reply is: “按你指定的 PBE/def2-TZVP，先优化结构，再计算优化结构的单点能。优化输入文件已准备好，可在下方下载；单点能输入文件需要等优化后的坐标及其单位。完成优化后把这些结果发来，即可继续。” Attach the actual returned download URL. A generated input file is not a completed calculation.

Plan/task/card IDs, internal field/status/source codes, API or tool names, hashes, version bookkeeping and raw validation results belong in an explicitly requested technical, audit or debugging view. Show full input-card contents when requested. Source attribution in an ordinary reply uses scientific language such as “按你指定的方法”, “研究在这些条件下支持该方案”, or “这是待确认的初步建议”. Saved technical fields remain available through the tools.

Discuss local basis paths and installation when relevant to the next requested action or a concrete reported failure. Claims about missing files or empty directories require an actual inspection; ordinary file preparation does not need an environment checklist.

## REST geometry convention (verified 2026-10-03)

The [official REST README, geom section](https://gitee.com/restgroup/rest/blob/master/README.md) supports `unit = "angstrom"` and `unit = "bohr"`. AIFS writes this keyword explicitly. A `.in` file contains TOML; `.in` is the file extension.

Save the source coordinate unit as `inputs.position_unit` (`angstrom` or `bohr`). Preserve coordinate numbers; AIFS does not convert them. If the user supplies Å/Angstrom, record `angstrom`; if Bohr/a0, record `bohr`. Do not infer units from distances. An unknown unit can be null in a saved plan but blocks a task card. For an optimization result, confirm the result's unit separately from the starting geometry. Do not re-search this recorded convention after card generation unless the user specifies a different REST version or presents contradictory evidence.

`spin` is multiplicity **2S+1**, not S or the number of unpaired electrons. `charge` is net molecular charge. Keep unknown charge/spin unknown. These input conventions do not specify the units of future calculation outputs; this stage does not parse or run REST results.

## Plan contract and optimization example

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
