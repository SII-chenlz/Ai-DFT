/** Model-facing PlanDraft contract; conditional scientific gates stay in Python. */
import type { ValueSchemaSpec } from '@deepseek-ai/dsh-tools'

const nullableString = { oneOf: [{ type: 'string' }, { type: 'null' }] } as const
const strings = { type: 'array', items: { type: 'string' } } as const
const evidence = {
  type: 'object', additionalProperties: false,
  properties: {
    source: { type: 'string', enum: ['local', 'web'], required: true },
    claim_type: { oneOf: [{ type: 'string', enum: ['method_used', 'comparative_benchmark', 'author_recommendation', 'other'] }, { type: 'null' }] },
    record_id: nullableString, url: nullableString, title: nullableString,
    note: { type: 'string', required: true, description: 'Specific supporting/opposing claim; web requires url and title, local requires record_id.' },
  },
} as const satisfies ValueSchemaSpec
const references = { type: 'array', items: evidence } as const
const decision = {
  type: 'object', additionalProperties: false,
  properties: {
    xc: { type: 'string', required: true }, basis: nullableString,
    xc_parser: { type: 'string', enum: ['legacy', 'parse_xc'], description: 'Defaults to legacy. Set parse_xc for methods listed on that path by get_rest_capabilities.' },
    empirical_dispersion: { oneOf: [{ type: 'string', enum: ['d3', 'd3bj', 'd4'] }, { type: 'null' }] },
    source: { type: 'string', enum: ['user', 'evidence', 'provisional'], required: true },
    rationale: { type: 'string', required: true }, uncertainty: nullableString,
    supporting: references, opposing: references,
  },
} as const satisfies ValueSchemaSpec
const task = {
  type: 'object', additionalProperties: false,
  properties: {
    task_id: { type: 'string', required: true, description: 'Stable unique ID, starting with a letter; letters, digits, underscore and hyphen only.' },
    title: { type: 'string', required: true }, purpose: { type: 'string', required: true },
    kind: { type: 'string', enum: ['rest', 'analysis', 'unsupported'], required: true },
    depends_on: strings, system_name: nullableString,
    job_type: { ...nullableString, description: 'REST tasks require energy, opt, force or numerical dipole. Unsupported operations use kind=unsupported.' },
    rest_options: { type: 'object', additionalProperties: true, description: 'Extra REST tables keyed by section, e.g. {hessian:{frequencies:true},thermo:{temperature:298.15,pressure:1.0}}. Use get_rest_capabilities for supported sections, types, units and limits. Frequency/TDDFT use job_type=energy with their section, transition/IRC use opt with geometric_pyo3. Cannot override core inputs/decisions.' },
    analysis_formula: { ...nullableString, description: 'Required for kind=analysis, e.g. E(complex)-E(A)-E(B).' },
    inputs: {
      type: 'object', additionalProperties: false,
      properties: {
        position: { ...nullableString, description: 'Element x y z lines; leave null while waiting for optimized result.' },
        position_unit: { oneOf: [{ type: 'string', enum: ['angstrom', 'bohr'] }, { type: 'null' }], description: 'Confirmed source coordinate unit. Required to generate a task card; never infer from coordinate magnitudes.' },
        position_source: { oneOf: [{ type: 'string', enum: ['user', 'external_optimized', 'prior_result'] }, { type: 'null' }] },
        position_from_task: { ...nullableString, description: 'For prior_result, the optimization task ID, also present in depends_on.' },
        charge: { oneOf: [{ type: 'number' }, { type: 'null' }] },
        charge_source: { oneOf: [{ type: 'string', enum: ['user', 'external'] }, { type: 'null' }] },
        spin: { oneOf: [{ type: 'integer' }, { type: 'null' }], description: 'Multiplicity 2S+1, minimum 1.' },
        spin_source: { oneOf: [{ type: 'string', enum: ['user', 'external'] }, { type: 'null' }] },
      },
    },
    candidates: {
      type: 'array', items: {
        type: 'object', additionalProperties: false,
        properties: {
          xc: { type: 'string', required: true }, basis: nullableString,
          rationale: { type: 'string', required: true }, supporting: references, opposing: references,
        },
      },
    },
    decision: { oneOf: [decision, { type: 'null' }] }, notes: nullableString,
  },
} as const satisfies ValueSchemaSpec

export const PLAN_DRAFT_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    question: { type: 'string', required: true },
    goal: { type: 'string', required: true, enum: ['reaction_energy', 'binding_energy', 'optimization_single_point', 'force', 'dipole', 'other'] },
    tasks: { type: 'array', required: true, items: task }, assumptions: strings,
  },
} as const satisfies ValueSchemaSpec
