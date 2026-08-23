/**
 * Canonical output schemas for the two AIFS tools.
 *
 * These are fixed-version snapshots of the backend response fields (per the
 * architecture spec: the TypeScript plugin validates against a pinned OpenAPI
 * Schema). Domain failures are structured results, never thrown errors, so
 * `generate_rest_input` declares both the success and the domain-error branch.
 */

import type { ValueSchemaSpec } from '@deepseek-ai/dsh-tools'

/**
 * One validator finding on a REST input card (backend `ValidationIssue`).
 * The backend serializes its optional fields as JSON `null`, so they accept
 * both the declared type and `null`.
 */
const NULLABLE_STRING_SCHEMA = {
  oneOf: [{ type: 'string' }, { type: 'null' }],
} as const satisfies ValueSchemaSpec

const NULLABLE_INTEGER_SCHEMA = {
  oneOf: [{ type: 'integer' }, { type: 'null' }],
} as const satisfies ValueSchemaSpec

export const VALIDATION_ISSUE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    code: { type: 'string', required: true },
    message: { type: 'string', required: true },
    section: NULLABLE_STRING_SCHEMA,
    field: NULLABLE_STRING_SCHEMA,
    line: NULLABLE_INTEGER_SCHEMA,
  },
} as const satisfies ValueSchemaSpec

/** Successful render: the card plus effective settings and applied defaults. */
export const GENERATE_SUCCESS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    ok: { type: 'boolean', required: true, const: true },
    rest_input: { type: 'string', required: true },
    effective_settings: { type: 'object', additionalProperties: true, required: true },
    defaults_applied: { type: 'array', required: true, items: { type: 'string' } },
    warnings: { type: 'array', required: true, items: { type: 'string' } },
  },
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

/** `validate_rest_input` result; `valid: false` is a normal 200 domain result. */
export const VALIDATE_OUTPUT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    valid: { type: 'boolean', required: true },
    errors: { type: 'array', required: true, items: VALIDATION_ISSUE_SCHEMA },
    warnings: { type: 'array', required: true, items: VALIDATION_ISSUE_SCHEMA },
    parsed_sections: { type: 'array', required: true, items: { type: 'string' } },
  },
} as const satisfies ValueSchemaSpec
