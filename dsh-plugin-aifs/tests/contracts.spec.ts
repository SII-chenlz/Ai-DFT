import { describe, expect, it } from 'vitest'
import { PLAN_DRAFT_SCHEMA, REST_INPUT_SCHEMA, PLAN_REVISION_SCHEMA } from '../src/generated/backend.ts'
import { compileValue, validateValue } from './fixtures/dsh-tools.ts'
import { withDescriptions } from '../src/schema-descriptions.ts'

describe('generated backend contracts', () => {
  it('rejects missing fields and invented enums and accepts Python nullable values', () => {
    const schema = compileValue(REST_INPUT_SCHEMA)
    const request = { system_name: 'H2', position: 'H 0 0 0', job_type: 'energy', xc: 'PBE', basis: null, spin_polarization: null }
    expect(validateValue(schema, request, '')).toEqual([])
    expect(validateValue(schema, { ...request, job_type: 'freq' }, '')).not.toEqual([])
    const { xc: _xc, ...missing } = request
    expect(validateValue(schema, missing, '')).not.toEqual([])
  })
  it('derives revision required fields and retains the Skill-facing plan structure', () => {
    expect(compileValue(PLAN_REVISION_SCHEMA).required).toEqual(['expected_version', 'change_reason', 'plan'])
    expect(compileValue(PLAN_DRAFT_SCHEMA).properties?.tasks?.items?.properties?.decision?.oneOf).toHaveLength(2)
  })
  it('adds descriptions without changing validation or mutating generated fields', () => {
    const decorated = withDescriptions(REST_INPUT_SCHEMA, { basis: 'Choose the basis separately.' })
    expect(compileValue(decorated)).toEqual(compileValue(REST_INPUT_SCHEMA))
    expect('description' in REST_INPUT_SCHEMA.properties.basis).toBe(false)
    expect(() => withDescriptions(REST_INPUT_SCHEMA, { nonexistent: 'stale annotation' })).toThrow(/nonexistent/)
  })
})

// Simulate adding a Python revision field and regenerating the schema.
// The adapter must declare and forward it without another hand-maintained key list.
it('carries newly generated revision fields through the tool boundary', async () => {
  const { defineReviseAifsPlanTool } = await import('../src/tools.ts')
  const { vi } = await import('vitest')
  const properties = PLAN_REVISION_SCHEMA.properties as unknown as Record<string, { type: 'string' }>
  properties.future_note = { type: 'string' }
  const workflow = vi.fn(async () => ({ saved: true }))
  try {
    const tool = defineReviseAifsPlanTool({ workflow } as unknown as import('../src/client.ts').AifsBackendClient)
    expect((tool.parameters as unknown as import('./fixtures/dsh-tools.ts').JsonSchema).properties?.future_note).toEqual({ type: 'string' })
    const plan = { question: 'record', goal: 'other', tasks: [{ task_id: 'a', title: 'analysis', purpose: 'record', kind: 'analysis' }] }
    const revision = { expected_version: 1, change_reason: 'update', plan, future_note: 'new field' }
    const signal = new AbortController().signal
    await tool.execute({ plan_id: 'id with spaces', ...revision }, { signal })
    expect(workflow).toHaveBeenCalledWith('PUT', '/v1/plans/id%20with%20spaces', revision, signal)
  } finally { delete properties.future_note }
})
