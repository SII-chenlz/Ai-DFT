/**
 * Tool definitions registered by the AIFS plugin.
 *
 * Exactly two tools are registered: `generate_rest_input` and
 * `validate_rest_input`. The recommender is deliberately absent (a later
 * task). Tools only accept declared fields — never arbitrary TOML fragments —
 * and forward `exec.signal` to the HTTP request. Infrastructure failures
 * throw; domain failures return structured results.
 */

import { defineTool } from '@deepseek-ai/dsh-tools'
import type { ToolDefinition } from '@deepseek-ai/dsh-tools'
import type { AifsBackendClient } from './client.ts'
import { GENERATE_OUTPUT_SCHEMA, VALIDATE_OUTPUT_SCHEMA } from './schemas.ts'

/**
 * Versioned mirror of `aifs.rest.catalogs` (backend README read 2026-08-23).
 * Kept in sync manually until OpenAPI-generated types replace it.
 */
const JOB_TYPES = ['energy', 'opt', 'force', 'numerical dipole'] as const
const DISPERSION_VALUES = ['d3', 'd3bj', 'd4'] as const
const ALLOWED_OUTPUTS = [
  'dipole',
  'fchk',
  'cube_orb',
  'molden',
  'geometry',
  'force',
  'force_for_ghost_point_charges',
] as const

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
    parameters: {
      system_name: {
        type: 'string',
        required: true,
        description: 'Short name of the molecular system, e.g. "water".',
      },
      position: {
        type: 'string',
        required: true,
        description: 'Multi-line geometry, one "Element x y z" line per atom.',
      },
      job_type: {
        type: 'string',
        required: true,
        enum: [...JOB_TYPES],
        description: 'REST job type.',
      },
      xc: {
        type: 'string',
        required: true,
        description: 'Exchange-correlation method name (case-insensitive), e.g. "B3LYP".',
      },
      basis: {
        type: 'string',
        description:
          'Basis set name inside the server-configured pool, e.g. "def2-SVP". ' +
          'Relative only; absolute paths and ".." segments are rejected by the backend.',
      },
      charge: { type: 'number', description: 'Net molecular charge. Default 0.' },
      spin: {
        type: 'integer',
        description: 'Electron spin multiplicity (2S+1), at least 1. Default 1.',
      },
      spin_polarization: {
        type: 'boolean',
        description: 'Explicit spin polarization; derived from spin when omitted.',
      },
      empirical_dispersion: {
        type: 'string',
        enum: [...DISPERSION_VALUES],
        description: 'Empirical dispersion correction, if the method needs one.',
      },
      print_level: { type: 'integer', description: 'REST print verbosity, >= 0. Default 1.' },
      num_threads: { type: 'integer', description: 'Thread count, >= 1. Default 10.' },
      outputs: {
        type: 'array',
        items: { type: 'string', enum: [...ALLOWED_OUTPUTS] },
        description: 'Extra output items to request from REST.',
      },
    },
    output: {
      schema: GENERATE_OUTPUT_SCHEMA,
      render: renderJson,
    },
    async execute(args, exec) {
      return client.generate(args, exec.signal)
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
    parameters: {
      rest_input: {
        type: 'string',
        required: true,
        description: 'Complete REST TOML input card as a string.',
      },
    },
    output: {
      schema: VALIDATE_OUTPUT_SCHEMA,
      render: renderJson,
    },
    async execute(args, exec) {
      return client.validate(args.rest_input, exec.signal)
    },
  })
}
