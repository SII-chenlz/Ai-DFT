/**
 * Schema tests: the JSON Schemas the two tools declare are strict and mirror
 * the backend catalogs (fixed-version snapshot). The test double in
 * tests/fixtures compiles these schemas the same way the real registry does,
 * so these assertions describe what argument/output validation enforces.
 */

import { describe, expect, it } from 'vitest'
import { AifsBackendClient } from '../src/client.ts'
import { defineGenerateRestInputTool, defineValidateRestInputTool } from '../src/tools.ts'
import type { JsonSchema } from './fixtures/dsh-tools.ts'

const client = new AifsBackendClient({
  baseUrl: 'http://127.0.0.1:8000',
  requestTimeoutMs: 1_000,
  maxResponseBytes: 1_000_000,
})

const generate = defineGenerateRestInputTool(client)
const validate = defineValidateRestInputTool(client)

function asJsonSchema(value: unknown): JsonSchema {
  return value as JsonSchema
}

describe('generate_rest_input schema', () => {
  it('requires exactly the backend-required fields', () => {
    const parameters = asJsonSchema(generate.parameters)
    expect(parameters.required).toEqual(['system_name', 'position', 'job_type', 'xc'])
  })

  it('mirrors the REST job types and dispersion values', () => {
    const parameters = asJsonSchema(generate.parameters)
    expect(parameters.properties?.job_type?.enum).toEqual([
      'energy',
      'opt',
      'force',
      'numerical dipole',
    ])
    expect(parameters.properties?.empirical_dispersion?.enum).toEqual(['d3', 'd3bj', 'd4'])
  })

  it('types scalar parameters and pins the outputs enum', () => {
    const parameters = asJsonSchema(generate.parameters)
    expect(parameters.properties?.spin?.type).toBe('integer')
    expect(parameters.properties?.charge?.type).toBe('number')
    expect(parameters.properties?.spin_polarization?.type).toBe('boolean')
    expect(parameters.properties?.basis?.type).toBe('string')
    expect(parameters.properties?.outputs?.items?.enum).toEqual([
      'dipole',
      'fchk',
      'cube_orb',
      'molden',
      'geometry',
      'force',
      'force_for_ghost_point_charges',
    ])
  })

  it('declares closed success and closed domain-error output branches', () => {
    const output = asJsonSchema(generate.output.schema)
    expect(output.oneOf?.length).toBe(2)
    const success = output.oneOf?.[0]
    const failure = output.oneOf?.[1]
    expect(success?.type).toBe('object')
    expect(success?.additionalProperties).toBe(false)
    expect(success?.required).toEqual([
      'ok',
      'rest_input',
      'effective_settings',
      'defaults_applied',
      'warnings',
    ])
    expect(success?.properties?.ok?.const).toBe(true)
    expect(success?.properties?.rest_input?.type).toBe('string')
    expect(failure?.additionalProperties).toBe(false)
    expect(failure?.properties?.ok?.const).toBe(false)
    expect(failure?.properties?.error?.additionalProperties).toBe(false)
    expect(failure?.properties?.error?.required).toEqual(['code', 'message'])
  })
})

describe('validate_rest_input schema', () => {
  it('accepts only a rest_input string', () => {
    const parameters = asJsonSchema(validate.parameters)
    expect(parameters.required).toEqual(['rest_input'])
    expect(parameters.properties?.rest_input?.type).toBe('string')
  })

  it('declares the closed validation result with nullable issue fields', () => {
    const output = asJsonSchema(validate.output.schema)
    expect(output.additionalProperties).toBe(false)
    expect(output.required).toEqual(['valid', 'errors', 'warnings', 'parsed_sections'])
    expect(output.properties?.valid?.type).toBe('boolean')
    const issue = output.properties?.errors?.items
    expect(issue?.type).toBe('object')
    expect(issue?.additionalProperties).toBe(false)
    expect(issue?.required).toEqual(['code', 'message'])
    expect(issue?.properties?.code?.type).toBe('string')
    // The backend serializes optional fields as null, so they accept null too.
    expect(issue?.properties?.section?.oneOf?.length).toBe(2)
    expect(issue?.properties?.line?.oneOf?.length).toBe(2)
  })
})
