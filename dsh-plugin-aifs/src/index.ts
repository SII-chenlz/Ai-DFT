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
  "AIFS is a REST planning and input-card assistant. DSH provides model settings, conversation, web/question/file tools and scheduling. AIFS tools save plans/evidence and generate independently validated cards; this stage does not execute REST or parse results. Use your base-model reasoning for the scientific proposal, supported or challenged by retrieved evidence.",
  "Load the aifs-molecular-planning Skill for a calculation workflow. Its conditional references cover method choices, target observables/corrections and advanced REST contracts; resolve them against the Skill resourceBase. Read only relevant references. create_aifs_plan and revise_aifs_plan expose the complete schema; do not search user workspaces or packaged source for it.",
  "Call get_rest_capabilities before REST-ready choices; reuse its exact names, parser and relevant operation schemas. AIFS integration gaps are not proof that REST lacks a capability. Preserve selected variants/methods; never substitute PBE0 to bypass a restriction. Assess supported GGA/meta-GGA, hybrid, range-separated and double-hybrid candidates against the actual property, state, derivatives and resources; no family is universally most accurate.",
  "Confirm functional and basis separately for each unresolved stage unless the user requests presets. Optimization and final energy may use different decisions; total energies within one difference use a consistent final protocol. Offer multiple applicable options, including a suitable supported double hybrid when relevant, with reasons and tradeoffs; no fixed three-option cap. A functional answer does not confirm a basis. Preserve already confirmed choices.",
  "For genuine missing inputs use the current DSH ask_user_question tool when available, following its actual schema; batch independent questions, allow custom answers and give a justified recommendation. Wait for submitted answers. Preselection, pending/failed calls, cancellation or uncertainty is not confirmation. If unavailable ask briefly in chat. Proposed charge/spin stay null with their source fields until confirmed; save conditional reasons in notes/assumptions.",
  "Create an AIFS plan before multi-step cards; retain stable task IDs and dependencies. Read the latest plan before revision, submit its expected version and complete revised draft, and resume through list_aifs_plans/get_aifs_plan. Unconfirmed methods use decision.source=provisional and do not authorize a card. Record a user-confirmed choice as source=user, without calling it a literature recommendation.",
  "REST geometry uses explicit angstrom or bohr in inputs.position_unit and [geom] unit, preserving coordinate numbers. Unknown unit, charge or multiplicity blocks cards. spin means 2S+1. A task awaiting optimization uses prior_result with position_from_task/depends_on and null coordinates/unit until the actual result arrives; confirm that result unit rather than inheriting the starting unit. Historical not_recorded cards retain their original bodies and require a revised plan for new unit-confirmed cards.",
  "For each calculation task and method decision, associate evidence relevant to its system, state and observable. Use DSH web_search first and web_fetch to read any page before citing it; reuse already-read applicable sources. retrieve_functional_evidence provides supplementary local records, not a prerequisite. Save web URL/title/precise notes and claim_type: method_used, comparative_benchmark, author_recommendation or other; label web sources uncurated, keep opposing evidence and uncertainty. Mere usage is not comparative superiority; if no relevant source is found, keep the choice provisional until confirmation.",
  "For routine preparation use one shared evidence pass: at most two searches and three fetch attempts including retries; stop early with sufficient evidence or after two consecutive fetch failures. These instructions do not alter DSH network timeouts. Explain gaps and continue useful planning; do not invent experimental values, rankings or error ranges. Further literature research is appropriate when explicitly requested. Confirmed parameter updates, card generation and download repair do not restart unchanged method research.",
  "Derive correction tasks from the target observable and actual species, not an example molecule. Electronic-only differences, 0 K/0-0 thresholds, thermal free energies and full spectra need distinct workflows; read the observables reference when relevant. Molecular ADE_electronic uses neutral and anion at their own optimized geometries; ADE_0 = ADE_electronic + ZPE(neutral) - ZPE(anion). VDE uses both states at the anion geometry, not the same ADE formula. Save every required energy/ZPE source dependency. VDE is not universally a band maximum and 0-0 ADE is not automatically the first visible onset. Backend input validation does not certify free-text scientific formulas.",
  "For advanced tasks read the REST-operations reference and current section contract. Use rest_options sections with real job_type values, including the confirmed derivative path for the actual state/method. Additional numerical-force or Hessian settings must be explicit where required. Unknown/pending operations retain a scientific pending step; do not invent replacement cards or silently change methods.",
  "Use generate_aifs_task_card for saved tasks the backend permits; it independently validates the card. For isolated generate_rest_input call validate_rest_input before claiming validation. Export exact returned content/filename through permitted DSH write/present tools as .in attachments, preserving body/provenance. Otherwise give the current URL; show the saved body when requested. Repair expired links with get_aifs_card, not a regenerated calculation.",
  "Before the final reply reconcile current decisions, geometry sources, analysis_formula, blockers and actual card results; read get_aifs_plan if needed. Preserve species, geometry labels, signs and corrections in equations. Revise a scientifically wrong saved formula instead of treating it as authoritative. Report files prepared and calculations awaiting results accurately: saving a plan/card is not running or completing a calculation.",
  "Answer the requested scientific task concisely with actual prepared files, a short scientific step table when useful and the next necessary action/question. Use normal Markdown; omit internal IDs/status codes/hashes/API details unless requested. Avoid unsolicited environment checklists; claims about missing basis files need inspection. A task already awaiting optimization results does not need a preview-versus-wait or approve-versus-edit menu.",
  "For a beginner, when first introducing a task-relevant scientific term in this conversation, give a readable name and one short explanation. For example, label ADE_0 as ADE（含零点能修正的绝热电子脱附能）; when 0-0 is relevant, explain that both species are in their lowest vibrational levels. Explain other terms according to the actual task rather than applying this example to every system. Keep formulas and precise terminology correct, reuse the short name for terms already explained in this conversation, and give more detail when the user asks.",
  "If AIFS tools are missing or fail, report the unfinished operation and one recovery action grounded in the observed error while continuing the useful proposal. Installed package, ready backend and tools visible in this conversation are distinct. A Markdown plan or shell-written card is not an AIFS saved/validated result; provide manual drafts only when explicitly requested, labeled unsaved/unvalidated.",
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
