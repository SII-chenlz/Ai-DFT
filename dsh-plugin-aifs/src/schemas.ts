/** Generated Python outputs plus the plugin-owned domain error envelope. */
import type { ValueSchemaSpec } from '@deepseek-ai/dsh-tools'

import { PREPARE_RESPONSE_SCHEMA, VALIDATE_RESPONSE_SCHEMA, EVIDENCE_RESPONSE_SCHEMA } from './generated/backend.ts'

/** Client adds ok to the Python render response. */
export const GENERATE_SUCCESS_SCHEMA = {
  ...PREPARE_RESPONSE_SCHEMA,
  properties: { ok: { type: 'boolean', required: true, const: true }, ...PREPARE_RESPONSE_SCHEMA.properties },
} as const satisfies ValueSchemaSpec

/** Structured domain failure: the backend's 422 error envelope. */
export const DOMAIN_ERROR_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    ok: { type: 'boolean', required: true, const: false },
    error: {
      type: 'object',
      additionalProperties: false,
      required: true,
      properties: {
        code: { type: 'string', required: true },
        message: { type: 'string', required: true },
      },
    },
  },
} as const satisfies ValueSchemaSpec

/** `generate_rest_input` outcome: success or a structured domain failure. */
export const GENERATE_OUTPUT_SCHEMA = {
  oneOf: [GENERATE_SUCCESS_SCHEMA, DOMAIN_ERROR_SCHEMA],
} as const satisfies ValueSchemaSpec

export const VALIDATE_OUTPUT_SCHEMA = VALIDATE_RESPONSE_SCHEMA
export const EVIDENCE_SEARCH_OUTPUT_SCHEMA = EVIDENCE_RESPONSE_SCHEMA
