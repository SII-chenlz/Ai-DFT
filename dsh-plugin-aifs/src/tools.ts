/**
 * Tool definitions registered by the AIFS plugin.
 *
 * Tools accept only declared fields — never arbitrary TOML fragments — and
 * forward `exec.signal` to the HTTP request. Infrastructure failures throw;
 * domain failures return structured results. Literature retrieval returns
 * evidence for the Harness LLM; it is not a backend recommendation engine.
 */

import { defineTool } from '@deepseek-ai/dsh-tools'
import type { ToolDefinition } from '@deepseek-ai/dsh-tools'
import type { AifsBackendClient, PrepareRestInputArgs, JsonValue } from './client.ts'
import { GENERATE_OUTPUT_SCHEMA, VALIDATE_OUTPUT_SCHEMA } from './schemas.ts'
import { EVIDENCE_SEARCH_OUTPUT_SCHEMA } from './schemas.ts'
import { PLAN_DRAFT_SCHEMA } from './plan-schema.ts'
import { PREPARE_INPUT_SCHEMA, VALIDATE_INPUT_SCHEMA, EVIDENCE_REQUEST_SCHEMA, PLAN_REVISION_SCHEMA } from './generated/backend.ts'
import { withDescriptions, REST_DESCRIPTIONS } from './schema-descriptions.ts'

const REST_PARAMETERS = withDescriptions(PREPARE_INPUT_SCHEMA, REST_DESCRIPTIONS).properties
const EVIDENCE_PARAMETERS = withDescriptions(EVIDENCE_REQUEST_SCHEMA, {
  system_description: 'Description of the target system.',
  calculation_goal: 'Requested calculation or property.',
  candidate_functionals: 'Optional functional names to compare.',
  limit: 'Maximum evidence records; backend range 1–50, default 8.',
}).properties

function renderJson(_args: unknown, value: unknown): Array<{ type: 'text'; text: string }> {
  return [{ type: 'text', text: JSON.stringify(value) }]
}

function record(value: unknown): Record<string, unknown> | undefined {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown> : undefined
}

function records(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.map(record).filter((item): item is Record<string, unknown> => item !== undefined) : []
}

function shortText(value: unknown, limit: number): string | undefined {
  return typeof value === 'string' ? value.length > limit ? `${value.slice(0, limit)}…` : value : undefined
}

/** DSH sends rendered content to the model; the canonical value stays complete. */
function renderPlan(args: unknown, value: unknown): Array<{ type: 'text'; text: string }> {
  const result = record(value)
  if (!result || result.ok === false) return renderJson(args, value)
  const options = record(args)
  const plan = record(result.plan)
  const tasks = records(plan?.tasks)
  const statuses = records(result.statuses)
  const cards = records(result.cards)
  if (typeof options?.task_id === 'string') {
    const task = tasks.find(item => item.task_id === options.task_id)
    if (!task) return renderJson(args, {
      ok: false,
      error: { code: 'task_not_found', message: `No task ${options.task_id} in this plan version` },
      plan_id: result.plan_id, version: result.version,
    })
    return renderJson(args, {
      ok: true, plan_id: result.plan_id, version: result.version,
      task, status: statuses.find(item => item.task_id === task.task_id),
      cards: cards.filter(item => item.task_id === task.task_id),
    })
  }
  if (options?.view === 'full') return renderJson(args, value)
  return renderJson(args, {
    ok: result.ok, plan_id: result.plan_id, version: result.version,
    goal: plan?.goal, question: shortText(plan?.question, 160),
    tasks: tasks.map(task => {
      const status = statuses.find(item => item.task_id === task.task_id)
      return {
        task_id: task.task_id, title: shortText(task.title, 120), kind: task.kind,
        job_type: task.job_type, depends_on: task.depends_on,
        state: status?.state, blockers: status?.blockers ?? [],
        cards: cards.filter(card => card.task_id === task.task_id)
          .map(card => ({
            card_id: card.card_id, filename: card.filename, version: card.version,
            export_relative_path: card.export_relative_path,
            is_current_plan_version: card.is_current_plan_version,
            is_applicable_to_current_plan: card.is_applicable_to_current_plan,
          })),
      }
    }),
    detail_hint: 'Use get_aifs_plan with task_id for one task; view=full is for explicit full export or debugging.',
  })
}

/**
 * POST /v1/rest-inputs/prepare: generate and independently validate a card.
 * A backend domain error (422 envelope) is returned as `{ ok: false, error }`;
 * only network/backend failures throw.
 */
export function defineGenerateRestInputTool(client: AifsBackendClient): ToolDefinition {
  return defineTool({
    name: 'generate_rest_input',
    description:
      'Prepare one REST .in file directly, without creating a plan. Supply confirmed ' +
      'coordinates, coordinate unit, charge, multiplicity, functional and basis. The ' +
      'AIFS backend generates and independently validates the card in one call, returning ' +
      'rest_input, filename, export_relative_path, validation, effective settings, defaults and warnings. Export the exact body under the permitted workspace at export_relative_path. Use this ' +
      'for independent ready calculations. Workflows with prerequisites or energy ' +
      'combinations use create_aifs_plan and saved-task cards; dependent steps wait ' +
      'for actual results. ' +
      'Domain incompatibilities (e.g. empirical dispersion on a double-hybrid/RPA method) ' +
      'come back as an ok=false structured result; only backend or network failures raise ' +
      'tool errors. The basis is a name inside the server-configured pool — never an ' +
      'absolute path.',
    parameters: REST_PARAMETERS,
    output: {
      schema: GENERATE_OUTPUT_SCHEMA,
      render: renderJson,
    },
    async execute(args, exec) {
      return client.prepare({
        ...args, rest_options: args.rest_options as PrepareRestInputArgs['rest_options'],
      }, exec.signal)
    },
  })
}

export function defineGetRestCapabilitiesTool(client: AifsBackendClient): ToolDefinition {
  return defineTool({
    name: 'get_rest_capabilities',
    description: 'Read the current AIFS REST input coverage, exact method/parser names, upstream source commit and remaining integration gaps. Optional section returns keyword types, enums, bounds and units. Use this before planning advanced REST cards; no source-code or shell search is needed. AIFS input validation does not mean REST calculation execution.',
    parameters: { section: { type: 'string', description: 'Optional section, e.g. ctrl, ctrl.ri_pt2, geom, hessian, thermo, geometric_pyo3 or tddft. Omit for overview.' } },
    output: { schema: { type: 'json' }, render: renderJson },
    async execute(args, exec) {
      const query = typeof args.section === 'string' ? `?section=${encodeURIComponent(args.section)}` : ''
      return client.workflow('GET', `/v1/rest-capabilities${query}`, undefined, exec.signal)
    },
  })
}

/**
 * POST /v1/rest-inputs/validate: independently check a complete REST TOML
 * card against the REST catalogs. `valid: false` is a normal structured
 * result; only network/backend failures throw.
 */
export function defineValidateRestInputTool(client: AifsBackendClient): ToolDefinition {
  return defineTool({
    name: 'validate_rest_input',
    description:
      'Independently validate a complete REST TOML input card against the REST keyword ' +
      'catalogs via the AIFS backend. Returns valid plus structured errors and warnings; ' +
      'valid=false is a normal domain result, not a tool error.',
    parameters: VALIDATE_INPUT_SCHEMA.properties,
    output: {
      schema: VALIDATE_OUTPUT_SCHEMA,
      render: renderJson,
    },
    async execute(args, exec) {
      return client.validate(args.rest_input, exec.signal)
    },
  })
}

/** Retrieve literature records and verbatim evidence for the model to assess. */
export function defineRetrieveFunctionalEvidenceTool(client: AifsBackendClient): ToolDefinition {
  return defineTool({
    name: 'retrieve_functional_evidence',
    description:
      'Search imported DFT literature records and return source-linked evidence for reasoning. ' +
      'This tool does not recommend a functional and does not replace scientific judgment. ' +
      'Compare returned systems, tasks, protocols and conflicting evidence before making a suggestion.',
    parameters: EVIDENCE_PARAMETERS,
    output: {
      schema: EVIDENCE_SEARCH_OUTPUT_SCHEMA,
      render: renderJson,
    },
    async execute(args, exec) {
      return client.searchEvidence(args, exec.signal)
    },
  })
}

/** Create an AIFS-owned plan; its JSON is validated by the Python domain model. */
export function defineCreateAifsPlanTool(client: AifsBackendClient): ToolDefinition {
  return defineTool({
    name: 'create_aifs_plan',
    description: 'Save the internal workflow automatically when calculations require preceding results or combine multiple energies, and when the user explicitly requests persistence for an independent calculation. Independent ready calculations otherwise use generate_rest_input. Supply one concise complete initial graph with stable task IDs, dependencies and required inputs/decisions; do not repeat long evidence or candidate lists. The backend computes blockers and status; do not send status. Creation returns a model-facing summary; use get_aifs_plan with task_id for details. User-facing replies describe calculations, not database operations.',
    parameters: {
      plan: { ...PLAN_DRAFT_SCHEMA, required: true, description: 'Complete PlanDraft. Missing scientific inputs may be null; backend derives status. Use this declared schema directly, without looking for backend source in the user workspace.' },
    },
    output: { schema: { type: 'json' }, render: renderPlan },
    async execute(args, exec) {
      return client.workflow('POST', '/v1/plans', args.plan as JsonValue, exec.signal)
    },
  })
}

export function defineReviseAifsPlanTool(client: AifsBackendClient): ToolDefinition {
  return defineTool({
    name: 'revise_aifs_plan',
    description: 'Revise a saved AIFS plan using a compact patch of changed fields. Read the latest summary and relevant task details first. Preserve confirmed choices unless the user changes them or agrees to a scientifically necessary revision. patch.tasks updates existing tasks by task_id; inputs/decision merge their supplied fields, other arrays/dictionaries replace that field. Omitted fields stay unchanged; null explicitly clears a nullable field. Use patch.add_tasks for new complete tasks and patch.remove_task_ids for removals. Full plan remains a compatibility option; normally send patch only. The backend checks the merged graph and saves a new version; old cards remain unchanged. Returns a model-facing summary.',
    parameters: {
      ...withDescriptions(PLAN_REVISION_SCHEMA, {
        patch: 'Preferred compact revision: send only changes, not the full saved plan. Exactly one of patch or plan is required by the backend.',
        'patch.tasks': 'Updates to existing tasks by task_id. Omitted nested inputs/decision fields are preserved. Lists and rest_options replace their whole field.',
        'patch.add_tasks': 'Complete new tasks with unique IDs. Existing tasks do not need to be repeated.',
        'patch.remove_task_ids': 'IDs to remove; retained tasks must not depend on a removed task.',
        plan: 'Compatibility mode: complete replacement PlanDraft with every retained task. Prefer patch for incremental edits.',
      }).properties,
      plan_id: { type: 'string', required: true },
    },
    output: { schema: { type: 'json' }, render: renderPlan },
    async execute(args, exec) {
      const { plan_id, ...revision } = args
      return client.workflow('PUT', `/v1/plans/${encodeURIComponent(plan_id)}`, revision as JsonValue, exec.signal)
    },
  })
}

export function defineListAifsPlansTool(client: AifsBackendClient): ToolDefinition {
  return defineTool({
    name: 'list_aifs_plans',
    description: 'List saved AIFS plans so a user can reopen work after a new conversation.',
    parameters: {},
    output: { schema: { type: 'json' }, render: renderJson },
    async execute(_args, exec) {
      return client.workflow('GET', '/v1/plans', undefined, exec.signal)
    },
  })
}

export function defineGetAifsPlanTool(client: AifsBackendClient): ToolDefinition {
  return defineTool({
    name: 'get_aifs_plan',
    description: 'Read a saved workflow at its latest or a historical version. The default model-facing summary includes task names, IDs, states, blockers and card references without repeating coordinates or evidence. Supply task_id to read one complete task and its status/cards. Use view=full only for explicit full export or debugging; task_id takes precedence if supplied. The underlying HTTP response and canonical tool value remain complete.',
    parameters: {
      plan_id: { type: 'string', required: true },
      version: { type: 'integer', description: 'Historical version; omit for latest.' },
      task_id: { type: 'string', description: 'Read details of this one task instead of the default summary.' },
      view: { type: 'string', enum: ['summary', 'full'], description: 'Default summary. Full is for explicitly requested export/debugging; task_id selects one task when supplied.' },
    },
    output: { schema: { type: 'json' }, render: renderPlan },
    async execute(args, exec) {
      const path = `/v1/plans/${encodeURIComponent(args.plan_id)}${args.version === undefined ? '' : `?version=${args.version}`}`
      return client.workflow('GET', path, undefined, exec.signal)
    },
  })
}

export function defineGenerateAifsTaskCardTool(client: AifsBackendClient): ToolDefinition {
  return defineTool({
    name: 'generate_aifs_task_card',
    description: 'Generate, independently validate and save one REST .in card from a ready task in the latest saved AIFS plan, within the calculation scope the user requested. Identical existing cards are reused; is_applicable_to_current_plan expresses current applicability independently of the original card version. Missing or unsupported tasks return a blocker; never substitute the starting geometry for a missing optimized result. A saved dependency or supplied coordinate is not proof that a calculation has run.',
    parameters: {
      plan_id: { type: 'string', required: true },
      task_id: { type: 'string', required: true },
    },
    output: { schema: { type: 'json' }, render: renderJson },
    async execute(args, exec) {
      return client.workflow('POST', `/v1/plans/${encodeURIComponent(args.plan_id)}/tasks/${encodeURIComponent(args.task_id)}/cards`, {}, exec.signal)
    },
  })
}

export function defineGetAifsCardTool(client: AifsBackendClient): ToolDefinition {
  return defineTool({
    name: 'get_aifs_card',
    description: 'Read a saved card including its exact content, filename, stable export_relative_path, plan version, validation result and current .in download URL. Export the exact content at export_relative_path under the permitted workspace; a previous localhost URL may be stale after restart.',
    parameters: {
      plan_id: { type: 'string', required: true },
      card_id: { type: 'string', required: true },
    },
    output: { schema: { type: 'json' }, render: renderJson },
    async execute(args, exec) {
      return client.workflow('GET', `/v1/plans/${encodeURIComponent(args.plan_id)}/cards/${encodeURIComponent(args.card_id)}`, undefined, exec.signal)
    },
  })
}
