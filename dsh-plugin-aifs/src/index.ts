/**
 * AIFS plugin: Cordis function plugin exposing domain workflow tools to DSH.
 *
 * Exports the Cordis function-plugin contract (`name`, `inject`, `Config`,
 * `apply`, no default export). `apply` registers plan, evidence and REST card
 * tools backed by the AIFS FastAPI backend, and unregisters them on disposal.
 * Scientific ranking and REST execution remain outside this plugin.
 */

import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { BackendRuntime, dataDirectory, SERVICE_VERSION } from './desktop/runtime.ts'
import type { RuntimeStatus } from './desktop/runtime.ts'
import { registerPlanningSkill } from './desktop/skill.ts'
import { registerStatusRoutes } from './desktop/routes.ts'
import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import {
  AifsBackendClient,
  AifsBackendError,
  DEFAULT_BASE_URL,
  DEFAULT_MAX_RESPONSE_BYTES,
  DEFAULT_REQUEST_TIMEOUT_MS,
  assertClientConfig,
} from './client.ts'
import type { AifsClientConfig } from './client.ts'
import {
  defineCreateAifsPlanTool,
  defineGenerateAifsTaskCardTool,
  defineGenerateRestInputTool,
  defineGetAifsCardTool,
  defineGetAifsPlanTool,
  defineGetRestCapabilitiesTool,
  defineListAifsPlansTool,
  defineRetrieveFunctionalEvidenceTool,
  defineReviseAifsPlanTool,
  defineValidateRestInputTool,
} from './tools.ts'

/** Cordis function-plugin name. */
export const name = 'aifs'

/** Services the plugin requires before its `apply` runs. */
export const inject = ['tools', 'systemPrompt'] as const

/** Stable model-facing instructions for the AIFS workflow. */
export const AIFS_PROMPT_TEXT = [
  'REST geometry units are already verified: [geom] unit supports angstrom and bohr (REST README [geom], checked 2026-10-03). AIFS cards write unit explicitly and preserve the coordinate numbers. Save the confirmed unit as inputs.position_unit; if unknown, ask and save a blocked plan. When optimized coordinates arrive, confirm their own unit; do not inherit it blindly from the starting structure. Do not perform conversions or re-search these basic conventions after card generation unless a different REST version or contradictory source requires it.',
  'create_aifs_plan and revise_aifs_plan declare the complete PlanDraft input schema. Use those tool definitions; the user workspace need not contain AIFS source code. Read the aifs-molecular-planning Skill for the workflow example.',
  'Historical cards with position_unit_status=not_recorded keep their original content. Explain that their coordinate unit was not recorded; revise the plan with the confirmed unit to obtain a new explicit-unit card, rather than treating the old card as unit-confirmed.',
  'AIFS plans molecular REST calculations and preserves each task, decision and input card.',
  'Use your own molecular reasoning to interpret the question, propose a task graph and explain candidate parameters and methods. Web retrieval and the local knowledge base strengthen and challenge these proposals. When retrieval is unavailable or insufficient, continue useful planning and offer provisional suggestions with their assumptions, rationale and uncertainty.',
  'For a multi-step research question, create_aifs_plan before making cards. Explain the saved workflow in terms of the requested scientific goal, named calculation steps, the chosen or provisional method and the next information needed.',
  'For an ordinary user, report the task outcome first, then a short step list or table using scientific step names and plain-language progress, actual .in download links for generated cards, and the next action or question. Translate blockers into actionable requests. For optimization then single point, say the optimization input file is prepared and the single point awaits optimized coordinates and their unit. Card generation does not mean the calculation ran; use the latest tool outcomes when describing progress.',
  'Expose plan/task/card IDs, internal goal/status/source codes, API/tool names, version bookkeeping, hashes, raw validation payloads and full card bodies only when the user requests technical details, file contents, auditing or debugging. For method provenance say the user chose it, a cited study supports it, or it is a provisional model suggestion, and retain relevant scientific reasoning and uncertainty. The underlying tools still preserve technical fields for lookup. A routine reply is a calculation workflow, not a dump of its tool payload.',
  'Mention basis paths or installation requirements when they affect the user\'s next requested action or a tool reports a concrete problem. State that a directory is empty or files are missing only after an actual inspection. Routine input-file preparation does not require an unsolicited environment checklist.',
  'Deliver generated cards as actual .in file attachments when the current DSH conversation provides file write/present tools: copy the exact content and filename returned by AIFS to the permitted user workspace and present the saved files. This is an export of an already validated card, not manual card generation; preserve its plan/card provenance and never edit or reconstruct its body. Fall back to the current download link when file delivery is unavailable. When the user asks to see the input card directly, show its exact saved content in chat. If a localhost download fails or the backend has restarted, use get_aifs_card to read the saved card and obtain the current URL/content; offer the body or file export instead of repeating the broken link. Do not regenerate or change the method just to repair delivery. A bare old localhost URL is not a durable attachment.',
  'For ordinary calculation requests, save the plan with AIFS tools and obtain validated cards from them. A Markdown document or a hand-written .in file is not an AIFS saved plan or validated card. Export a separate planning document only when requested. If AIFS tools are absent or a call fails, continue discussing the scientific proposal, state that saving or card preparation is pending, and give one relevant recovery action based on the observed failure. Do not substitute shell-written cards for unavailable AIFS operations; if the user explicitly requests a draft, label it unvalidated and unsaved.',
  'Present the recommended next action directly. Ask about unresolved scientific inputs or a choice that materially changes the calculation; do not force a generic approve-versus-edit menu after a confirmed plan. An installed package, backend readiness and tools available in the current conversation are distinct: do not tell the user the plugin is disabled without evidence.',
  'Keep a routine final reply concise: prepared .in attachments first, a short calculation-step table if useful, one necessary scientific clarification and the next action. A saved plan is not a completed calculation; do not label pending work as completed or claim a validated input is immediately runnable without checking the run environment. Do not append a preview-versus-wait choice for tasks that must await optimization results. State a literature gap in one sentence unless the user requests a review. Display equations directly with their species and geometry labels, never refer to an ambiguous preceding formula as "the above formula"; copy scientific definitions accurately from the saved plan. Do not escape normal Markdown headings, tables or links into literal syntax.',
  'For molecular detachment, ADE_electronic = E(neutral, neutral optimized geometry) - E(anion, anion optimized geometry); ADE_0 = ADE_electronic + ZPE(neutral) - ZPE(anion). VDE_electronic = E(neutral, anion optimized geometry) - E(anion, anion optimized geometry). ADE_0 is not VDE plus the equilibrium ZPE difference. VDE is a fixed-geometry electronic gap, not universally the measured band maximum; a 0-0 ADE is not automatically the first visible spectral onset. Interpret experimental assignments, vibrational structure, hot bands and Franck-Condon effects before equating these quantities with spectral features.',
  'When confirmation or a choice is needed, prefer the DSH ask_user_question tool available in the current conversation rather than a numbered question in the final reply. Batch independent unresolved questions (for example electronic state and functional choice) into one call, with stable question ids, concise Chinese headings and options, and a short reason or precision/cost tradeoff for each option. Put the recommended option first with the tool\'s recommended-label convention. Use the actual tool schema and allow custom answers; do not invent chemically unsupported numerical choices. Read submitted answers before revising confirmed inputs or producing cards: a preselected option, a pending/timed-out call, cancellation, or an answer saying the user is unsure is not confirmation. Keep unanswered inputs unknown and do not ask again about information already confirmed. If this question tool is unavailable or fails, ask the necessary concise question in chat and explain the actual limitation without claiming a panel was opened.',
  'Use list_aifs_plans and get_aifs_plan to resume, and revise_aifs_plan when new information arrives.',
  'For missing charge or spin, explain plausible candidates conditional on the molecular identity, ionization and electronic state, then ask for confirmation or the information needed to distinguish them. Save unconfirmed suggestions and their reasons in task.notes or plan.assumptions; keep inputs.charge, inputs.spin and their source fields null until confirmed. Use source=user for a user-confirmed suggestion and source=external only for an actual supplied external record. Coordinate values and units require their own source confirmation.',
  'Save model-proposed methods in candidates with their reasoning. Without supporting references or user approval, keep decision.source=provisional, record uncertainty and leave supporting/opposing empty; your own reasoning is not a web or local evidence record. If the user confirms the proposal, record source=user and retain the original rationale.',
  'Build a geometry-functional menu for the geometry task itself, not just a shortened energy-method list: assess supported GGA/meta-GGA candidates such as PBE, TPSS, r2SCAN or SCAN, conventional hybrids such as TPSSh/PBE0/SCAN0, appropriate range-separated hybrids, and applicable double hybrids. TPSS is a meta-GGA without exact exchange; TPSSh is its hybrid and is a distinct choice. When the user requests TPSS or a broader optimization menu, make applicable candidates selectable with their actual names and explain any exclusion. Do not claim metal-cluster geometry accuracy from a functional family alone or automatically include every catalog entry. Query exact task coverage, account for electronic state/derivative path and resources, and keep unsupported/unjustified options out of the REST-ready panel.',
  'DSH choice panels do not have a fixed three-option cap. When the user asks for a broader or higher-accuracy comparison, present a manageable expanded functional shortlist (for example four to six applicable choices), with a distinct purpose and cost/uncertainty description for each; do not truncate useful candidates to three or pad the list with unsuitable methods. In suitable electronic-energy work, expose supported XYG3, XYG7 and/or XYGJOS as individually selectable double-hybrid alternatives, not only as prose outside the panel. Do not call a double hybrid universally more accurate. For a geometry panel, consider double hybrids only with the reviewed numerical-force route, explicitly set rest_options.ctrl.numerical_force=true when that route is selected, and explain its higher optimization cost and electronic-state limits; analytic Hessian/TDDFT restrictions remain. Keep optimization and final-energy choices independent. If a candidate cannot serve the requested operation, explain its exclusion or offer it at the suitable single-point stage rather than pretending support.',
  'Before researching or presenting a method-choice panel, call get_rest_capabilities to obtain the exact integrated methods/parsers and required operation contracts. Prioritize methods that AIFS can express for the requested REST task. Assess supported double hybrids such as XYG3/XYG7 for accurate electronic-energy work; when applicable, include a reasoned double-hybrid option alongside suitable hybrid/range-separated alternatives. Explain exclusion when correlation assumptions, spin state, basis convergence, derivative coverage or cost make it unsuitable. Do not default every request to PBE0 or infer accuracy solely from a functional family. wB97X-D and CCSD(T) must not appear as ordinary REST-ready choices in this coverage; outside-REST reference methods are clearly separate comparisons when relevant, not promises of REST input cards. If capability access fails, state that compatibility remains unchecked and keep the proposal provisional.',
  'Choose the functional and orbital basis in separate questions, never as bundled functional/basis options unless the user explicitly requests preset combinations. First confirm the unresolved functional for each stage (for example geometry_xc and energy_xc); then ask separate basis questions (geometry_basis and energy_basis) informed by those selected functionals. Group independent questions within the actual DSH tool limits, but wait for functional answers before choosing method-dependent basis options. Functional option labels contain functional names; basis option labels contain basis names. Offer several scientifically suitable basis alternatives when available; the shortlist is not capped at three and may expand when the user requests a broader comparison, describing size/convergence, cost and diffuse-function needs for the actual species/property; allow a custom basis. Do not reduce basis choice to one default just because a functional was selected. If only one applicable choice is justified, explain that constraint instead of inventing alternatives. Respect already confirmed parameters, including explicit combinations, and ask only for the missing component. The capability catalog validates input contracts, not the presence of local basis files or all element/method combinations; do not claim basis availability without evidence. Save the confirmed pair in each task decision; selecting a functional does not confirm an unchosen basis.',
  'Each calculation task has its own decision: optimization and final single-point energies may use different functionals and basis sets. If the user has not chosen both, ask separately about the geometry method and final energy method, with meaningful precision/cost tradeoffs. Save each choice on its own task; never apply a plan-wide method override. For ADE/VDE, binding or reaction energies, all total energies combined in one difference use the same final functional, basis, dispersion and compatible numerical settings, with each species having its appropriate electronic state. When optimization uses a different method, add final-energy tasks for every required species/geometry instead of subtracting optimization energies from single-point energies at another method. Record the geometry-method approximation and wait for genuine optimized coordinates/unit. Distinct alternative energy protocols form separate comparisons. These consistency checks guide planning; the backend does not certify the chemistry of a free-text energy formula.',
  'Derive correction tasks from the requested observable and actual species/states, for any molecular system; do not require a novice to specify ZPE or copy methods, charge/spin or task counts from test examples. Record the comparison convention and assumptions. Electronic-only differences omit automatic thermal/ZPE work; experimental 0–0 ADE/adiabatic electron affinity or other 0 K thresholds include the required molecular frequency/ZPE sources and stoichiometric correction; finite-temperature enthalpy/free energy needs temperature/standard-state and thermal/entropy treatment; vertical electronic gaps and full spectra have distinct requirements. Clarify an ambiguous observable in plain language, not whether a required physical correction exists. For molecular detachment, save ADE_0 = E(neutral_sp)-E(anion_sp)+ZPE(neutral_freq)-ZPE(anion_freq) with direct dependencies on all required energy/ZPE sources; label the uncorrected difference ADE_electronic. The correction may have either sign; atoms/free electrons have no molecular vibrational ZPE and need no fabricated frequency job. VDE_electronic = E(neutral_at_anion_sp)-E(anion_sp) remains a frozen-geometry gap; do not automatically add the equilibrium ADE correction. Frequency tasks await their own optimized coordinates/unit and use an appropriate consistent confirmed frequency protocol, independently of the final-energy method. Query derivative coverage for each electronic state; unsupported Hessians remain blocked, never silently replace a method. Request a full Hessian/ZPE report and record scaling; combine ZPE only with final electronic energies, not another method\'s E+ZPE totals or finite-temperature Gibbs/enthalpy corrections. Record pending energies/ZPE, species/state/method/units and minimum/imaginary-mode checks in notes. AIFS saves tasks/formulas but does not run frequencies, parse results or evaluate free-text formulas; analysis_only is not analysis completed. Follow the planning Skill for detailed conditional routes.',
  'Choose functionals for the actual target property and system. Give the rationale, basis/convergence considerations and uncertainty; preserve favorable evidence for PBE0 when relevant. A general benchmark does not establish superiority for Al-cluster ADE/VDE, and a paper comparing a cluster series does not prove the best method for one cluster/property. Unavailable or conflicting literature still permits base-model provisional suggestions with explicit assumptions and no fabricated ranking or error estimates. Keep exact variants distinct; omegaB97X, its dispersion variants and VV10-containing variants are not interchangeable, and cannot be recreated by adding an arbitrary D3/D4 keyword.',
  'Use get_rest_capabilities to read the current input coverage, method parser, exact variants and source commit, and query the needed section for keyword types and units. The goal is to cover official REST capabilities, but the tool explicitly lists remaining AIFS integration gaps; never infer that REST lacks a capability from an AIFS rejection. The legacy path includes wB97X/CAM-B3LYP and the reviewed parse_xc path includes wB97X-V, wB97M-V and specific D3 variants. Set decision.xc_parser explicitly when needed. Never substitute PBE0 for another selected method. Unknown expressions/variants remain candidates until integrated. Current input checks are against pinned upstream source; they do not prove a calculation ran or establish numerical accuracy.',
  'Advanced operations use REST sections rather than fabricated job_type names: native frequency/Hessian uses energy plus rest_options.hessian; analdrv frequency/multipoles use energy plus rest_options.ctrl.analdrv_tasks as an array of hessian/multipole, with optional rest_options.analdrv. Thermochemistry uses rest_options.thermo with a full Hessian. TDDFT/response/FEAST/PySOC use energy plus rest_options.tddft; excited-state gradient uses force and tddft_grad_state under its restricted single-channel conditions. Split response, FEAST, stability and gradient tasks according to the section contract; response skips excitation eigenvalues and FEAST requires restricted MO mode. TS/IRC uses opt plus rest_options.geometric_pyo3. One/two-dimensional RRS-PBC uses energy and rest_options.geom; it is finite-cluster post-SCF reconstruction, not periodic SCF. Query the current section schemas and use backend blockers; do not replace a requested method to bypass derivative restrictions. Native thermo pressure is atm, geometric thermo pressure is bar, multipole_origin and response spatial grids are bohr. MD/GW/BSE, 3D RRS-PBC and other current pending operations retain scientific plans as kind=unsupported; do not generalize pending status to an entire reviewed family or generate replacement cards.',
  'A single-point task after optimization waits for optimized coordinates; do not reuse starting coordinates.',
  'Use generate_aifs_task_card for a saved ready task; standalone generate_rest_input is only for an isolated card.',
  'The saved task-card operation independently validates its result. For standalone generate_rest_input, call validate_rest_input before saying the card is ready.',
  'For each calculation task and method decision, associate evidence relevant to its system, electronic state, method and target property. For new evidence, start with DSH web_search and use web_fetch to read any page before citing it; search results alone are not evidence of a method ranking. Reuse already-read applicable sources from the saved plan/conversation across related optimization and energy tasks instead of searching independently for every step. Filling confirmed parameters, generating cards, exporting files or repairing downloads does not restart method research unless the scientific scope changed or conflicting evidence needs resolution.',
  'For routine workflow preparation, explain the proposed scientific route before retrieval, then use a bounded evidence pass: at most two web_search calls with focused queries and three web_fetch attempts in total for the shared plan, including retries. Stop web retrieval after two consecutive fetch failures/timeouts; do not cycle through mirrors or aggregators, inspect network configuration or run shell fetches as substitutes. Once adequate relevant evidence is read, stop early. If that pass is insufficient, state what could not be verified, save the provisional plan and ask the user to confirm a proposed method using ask_user_question when available. Do not claim unread sources were verified, invent experimental values or numerical error ranges, or block useful planning while seeking an exact experimental reference. Expand research only when the user explicitly requests a literature review, exhaustive comparison or additional verification; retain evidence uncertainty and backend card gates. These are model retrieval instructions, not a promise to control DSH network timeouts.',
  'Use retrieve_functional_evidence to supplement the web findings with curated local records when useful or when web search/fetch is unavailable; the local store is not a prerequisite for planning.',
  'Save cited web references as source=web with URL, title, a specific note about the claim and claim_type: method_used, comparative_benchmark, author_recommendation or other. Label web references uncurated and keep opposing evidence and uncertainty.',
  'A method appearing in a paper does not establish that it outperforms alternatives. Separate direct comparisons, author advice and mere use; if no relevant source is found, keep the choice provisional or ask the user to choose.',
  'A user-selected method can produce a card without literature support, but call it user-selected, never an AIFS literature recommendation.',
  'Treat retrieved records as evidence, not hard rules; compare source systems and protocols, and explain conflicts.',
  'Cite DOI/title and page evidence when making a literature-based claim. Do not invent literature evidence or benchmark values.',
  'This version generates and validates cards and retrieves literature evidence; it does not run REST jobs.',
].join(' ')

/** Deployment-facing configuration of the AIFS plugin. */
export interface Config extends AifsClientConfig {
  backendMode: string
  runtimeRoot: string
  dataDir: string
  startupTimeoutMs: number
  shutdownTimeoutMs: number
}

/**
 * Runtime schema for {@link Config}. Timeout, response-size cap and API
 * address are explicit configuration with defaults; invalid values fail
 * loudly in {@link apply}.
 */
export const Config = z.object({
  backendMode: z.string().default('external'),
  runtimeRoot: z.string().default(''),
  dataDir: z.string().default(''),
  startupTimeoutMs: z.number().default(30000),
  shutdownTimeoutMs: z.number().default(10000),
  baseUrl: z.string().default(DEFAULT_BASE_URL),
  requestTimeoutMs: z.number().default(DEFAULT_REQUEST_TIMEOUT_MS),
  maxResponseBytes: z.number().default(DEFAULT_MAX_RESPONSE_BYTES),
}) as unknown as ((data?: unknown) => Config) & {
  /** Local shim convenience; the real schemastery schema is callable. */
  parse(value: unknown): Config
}

/**
 * Install the AIFS tools. Registration goes through the tools registry
 * (an effect of its own); the returned disposers are collected so the tools
 * are unregistered when the context disposes.
 */
function registerTools(ctx: Context, config: AifsClientConfig, resolveBaseUrl?: (signal: AbortSignal) => Promise<string>): () => void {
  const disposers: Array<() => void> = []
  const dispose = () => { for (const release of disposers.splice(0).reverse()) release() }
  try {
    const client = new AifsBackendClient(config, resolveBaseUrl)
    for (const define of [
      defineGenerateRestInputTool, defineValidateRestInputTool, defineRetrieveFunctionalEvidenceTool,
      defineCreateAifsPlanTool, defineReviseAifsPlanTool, defineListAifsPlansTool,
      defineGetAifsPlanTool, defineGenerateAifsTaskCardTool, defineGetAifsCardTool,
      defineGetRestCapabilitiesTool,
    ]) disposers.push(ctx.tools.register(define(client)))
    return dispose
  } catch (error) { dispose(); throw error }
}

/** Tool schemas remain available through startup, failure and owned-server retry. */
export function apply(ctx: Context, config: Config): void {
  assertClientConfig(config)
  if (!['managed', 'external'].includes(config.backendMode)) throw new Error('aifs: invalid backendMode')
  for (const key of ['startupTimeoutMs', 'shutdownTimeoutMs'] as const) {
    if (!Number.isSafeInteger(config[key]) || config[key] <= 0 || config[key] > 2147483647) throw new Error(`aifs: invalid ${key}`)
  }
  ctx.effect(() => ctx.systemPrompt.section({ name: 'aifs:guidance', order: 80, text: AIFS_PROMPT_TEXT }))
  let runtime: BackendRuntime | undefined
  const dataDir = dataDirectory(config.dataDir)
  const unavailable: RuntimeStatus = { state: 'failed', version: SERVICE_VERSION, dataDir, logPath: `${dataDir}/logs/launcher.log`, error: 'Waiting for DSH subprocess service' }
  const status = () => runtime?.snapshot() ?? (config.backendMode === 'external'
    ? { ...unavailable, state: 'external' as const, baseUrl: config.baseUrl, error: undefined }
    : unavailable)
  ctx.inject(['connection'], (child) => {
    child.effect(() => registerStatusRoutes(child.connection, status, async () => { await runtime?.start() }))
  })
  ctx.inject(['skills'], (child) => {
    const bundled = fileURLToPath(new URL('../assets/skills/aifs-molecular-planning/SKILL.md', import.meta.url))
    const source = fileURLToPath(new URL('../../skills/aifs-molecular-planning/SKILL.md', import.meta.url))
    child.effect(() => registerPlanningSkill(child.skills, existsSync(bundled) ? bundled : source))
  })
  if (config.backendMode === 'external') {
    ctx.effect(() => registerTools(ctx, config))
    return
  }
  ctx.effect(() => registerTools(ctx, config, async signal => {
    if (!runtime) throw new AifsBackendError(`AIFS 等待 DSH 子进程服务；请查看 AIFS 状态页。${unavailable.logPath}`)
    return runtime.baseUrl(signal)
  }))
  ctx.inject(['subprocess'], (child) => {
    const owned = runtime = new BackendRuntime({ ...config, runtimeRoot: config.runtimeRoot || fileURLToPath(new URL('../runtimes/', import.meta.url)) }, child.subprocess)
    child.effect(() => {
      void owned.start()
      return async () => { await owned.dispose(); if (runtime === owned) runtime = undefined }
    })
  })
}
