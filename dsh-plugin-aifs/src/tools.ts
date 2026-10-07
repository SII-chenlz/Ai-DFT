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
import type { AifsBackendClient, GenerateRestInputArgs, JsonValue } from './client.ts'
import { GENERATE_OUTPUT_SCHEMA, VALIDATE_OUTPUT_SCHEMA } from './schemas.ts'
import { EVIDENCE_SEARCH_OUTPUT_SCHEMA } from './schemas.ts'
import { PLAN_DRAFT_SCHEMA } from './plan-schema.ts'
import { REST_INPUT_SCHEMA, VALIDATE_INPUT_SCHEMA, EVIDENCE_REQUEST_SCHEMA, PLAN_REVISION_SCHEMA } from './generated/backend.ts'
import { withDescriptions, REST_DESCRIPTIONS } from './schema-descriptions.ts'

const REST_PARAMETERS = withDescriptions(REST_INPUT_SCHEMA, REST_DESCRIPTIONS).properties
const EVIDENCE_PARAMETERS = withDescriptions(EVIDENCE_REQUEST_SCHEMA, {
  system_description: 'Description of the target system.',
  calculation_goal: 'Requested calculation or property.',
  candidate_functionals: 'Optional functional names to compare.',
  limit: 'Maximum evidence records; backend range 1–50, default 8.',
}).properties

function renderJson(_args: unknown, value: unknown): Array<{ type: 'text'; text: string }> {
  return [{ type: 'text', text: JSON.stringify(value) }]
}

/**
 * POST /v1/rest-inputs: render a structured request into a REST TOML card.
 * A backend domain error (422 envelope) is returned as `{ ok: false, error }`;
 * only network/backend failures throw.
 */
export function defineGenerateRestInputTool(client: AifsBackendClient): ToolDefinition {
  return defineTool({
    name: 'generate_rest_input',
    description:
      'Render a structured quantum-chemistry request into a REST TOML input card via the ' +
      'AIFS backend. Returns the card, effective settings, applied defaults and warnings. ' +
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
      return client.generate({
        ...args, rest_options: args.rest_options as GenerateRestInputArgs['rest_options'],
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
    description: 'Save a molecular calculation task plan. Supply question, goal and tasks with stable task_id, kind, dependencies, inputs, optional method candidates and decisions. The backend computes blockers and status; do not send status. For task-level evidence use web URL, title, specific claim note and claim_type, or a local record ID; keep opposing sources and uncertainty.',
    parameters: {
      plan: { ...PLAN_DRAFT_SCHEMA, required: true, description: 'Complete PlanDraft. Missing scientific inputs may be null; backend derives status. Use this declared schema directly, without looking for backend source in the user workspace.' },
    },
    output: { schema: { type: 'json' }, render: renderJson },
    async execute(args, exec) {
      return client.workflow('POST', '/v1/plans', args.plan as JsonValue, exec.signal)
    },
  })
}

export function defineReviseAifsPlanTool(client: AifsBackendClient): ToolDefinition {
  return defineTool({
    name: 'revise_aifs_plan',
    description: 'Revise a saved AIFS plan after the user supplies missing information or a method decision. Read its latest version first; old cards remain tied to their historical version.',
    parameters: {
      ...PLAN_REVISION_SCHEMA.properties,
      plan_id: { type: 'string', required: true },
      plan: { ...PLAN_DRAFT_SCHEMA, required: true, description: 'Complete revised PlanDraft, including every retained task. Preserve IDs; copy only the plan draft from get_aifs_plan, not its status/card metadata.' },
    },
    output: { schema: { type: 'json' }, render: renderJson },
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
    description: 'Read a saved plan, task blockers, and cards for its latest or a historical version.',
    parameters: {
      plan_id: { type: 'string', required: true },
      version: { type: 'integer', description: 'Historical version; omit for latest.' },
    },
    output: { schema: { type: 'json' }, render: renderJson },
    async execute(args, exec) {
      const path = `/v1/plans/${encodeURIComponent(args.plan_id)}${args.version === undefined ? '' : `?version=${args.version}`}`
      return client.workflow('GET', path, undefined, exec.signal)
    },
  })
}

export function defineGenerateAifsTaskCardTool(client: AifsBackendClient): ToolDefinition {
  return defineTool({
    name: 'generate_aifs_task_card',
    description: 'Generate, independently validate and save one REST .in card from a ready task in the latest saved AIFS plan. Missing or unsupported tasks return a blocker; never substitute the starting geometry for a missing optimized result.',
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
    description: 'Read a saved card including its exact content, filename, plan version, validation result and current .in download URL. Use the returned content for direct display or file export; a previous localhost URL may be stale after restart.',
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
