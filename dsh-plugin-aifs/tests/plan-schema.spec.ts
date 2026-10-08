import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { compileValue, validateValue } from './fixtures/dsh-tools.ts'
import { PLAN_DRAFT_SCHEMA } from '../src/plan-schema.ts'
import { PREPARE_INPUT_SCHEMA, PLAN_REVISION_SCHEMA } from '../src/generated/backend.ts'

const raw = readFileSync(new URL('../../skills/aifs-molecular-planning/SKILL.md', import.meta.url), 'utf8')
const example = () => JSON.parse(/```json\r?\n([\s\S]*?)\r?\n```/.exec(raw.slice(raw.indexOf('## Plan contract example')))![1]!)
const schema = compileValue(PLAN_DRAFT_SCHEMA)

describe('model-facing plan contract', () => {
  it('accepts the direct and compact revision examples shipped in the Skill', () => {
    const direct = JSON.parse(/```json\r?\n([\s\S]*?)\r?\n```/.exec(raw.slice(raw.indexOf('### Direct card example')))![1]!)
    expect(validateValue(compileValue(PREPARE_INPUT_SCHEMA), direct, '')).toEqual([])
    const { plan_id: _id, ...revision } = JSON.parse(/```json\r?\n([\s\S]*?)\r?\n```/.exec(raw.slice(raw.indexOf('### Compact revision example')))![1]!)
    expect(validateValue(compileValue(PLAN_REVISION_SCHEMA), revision, '')).toEqual([])
  })
  it('accepts the shipped Skill example and a backend-expanded draft with nulls', () => {
    const plan = example()
    expect(validateValue(schema, plan, 'plan')).toEqual([])
    Object.assign(plan.tasks[0], { notes: null, analysis_formula: null })
    Object.assign(plan.tasks[0].decision, { empirical_dispersion: null, uncertainty: null, supporting: [], opposing: [] })
    expect(validateValue(schema, plan, 'plan')).toEqual([])
  })
  it('rejects the observed incorrect goal/source and missing rationale', () => {
    const plan = example()
    plan.goal = 'optimization_then_energy'
    plan.tasks[1].inputs.position_source = 'optimized'
    delete plan.tasks[0].decision.rationale
    plan.tasks[0].candidates = [{ xc: 'PBE' }]
    const errors = validateValue(schema, plan, 'plan')
    for (const key of ['goal', 'position_source', 'decision', 'candidates[0].rationale']) {
      expect(errors.some(error => error.includes(key))).toBe(true)
    }
  })
  it('allows a saved unknown unit but rejects invented unit names and status', () => {
    const plan = example()
    plan.tasks[0].inputs.position_unit = 'nm'
    plan.tasks[0].status = 'ready_for_card'
    const errors = validateValue(schema, plan, 'plan')
    expect(errors.some(error => error.includes('position_unit'))).toBe(true)
    expect(errors.some(error => error.includes('status'))).toBe(true)
  })
})
