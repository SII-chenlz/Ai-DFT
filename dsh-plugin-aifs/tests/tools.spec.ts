/**
 * End-to-end tool tests: mount the plugin, invoke a registered tool through
 * the (doubled) registry, and observe the full path — schema validation,
 * HTTP call with the fused signal, and result mapping.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ToolRunContext } from '@deepseek-ai/dsh-tools'
import { mountPlugin } from './fixtures/context.ts'

const EXEC: ToolRunContext = { signal: new AbortController().signal }

const GENERATE_ARGS = {
  system_name: 'water',
  position: 'O 0 0 0',
  job_type: 'energy' as const,
  xc: 'B3LYP',
  position_unit: 'angstrom' as const,
  charge: 0,
  spin: 1,
  basis: 'def2-TZVP',
}

const VALIDATION = { valid: true, errors: [], warnings: [], parsed_sections: ['ctrl', 'geom'] }

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('generate_rest_input tool', () => {
  it('forwards parser and structured extension sections without rewriting them', async () => {
    const fetchMock = vi.fn(async (_url: URL, _init: RequestInit) => jsonResponse({
      rest_input: '[ctrl]\nxc = "wB97X"\n', effective_settings: {}, defaults_applied: [], warnings: [],
      filename: 'water-energy.in', export_relative_path: 'aifs-inputs/water-energy/water-energy.in', validation: VALIDATION,
    }))
    vi.stubGlobal('fetch', fetchMock)
    const args = { ...GENERATE_ARGS, xc: 'wB97X', xc_parser: 'parse_xc', rest_options: { tddft: { nroots: 6, tddft_method: 'tda' } } }
    await mountPlugin().tools.get('generate_rest_input')?.execute(args, EXEC)
    expect(JSON.parse(fetchMock.mock.calls[0]![1].body as string)).toEqual(args)
  })
  it('renders a card end to end with a structured ok=true result', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({
      rest_input: '[ctrl]\nxc = "B3LYP"\n',
      effective_settings: { xc: 'B3LYP' },
      defaults_applied: ['basis=def2-TZVPP'],
      warnings: [],
      filename: 'water-energy.in', export_relative_path: 'aifs-inputs/water-energy/water-energy.in', validation: VALIDATION,
    })))
    const tool = mountPlugin().tools.get('generate_rest_input')
    const outcome = await tool?.execute(GENERATE_ARGS, EXEC)
    expect(outcome).toEqual({
      ok: true,
      rest_input: '[ctrl]\nxc = "B3LYP"\n',
      effective_settings: { xc: 'B3LYP' },
      defaults_applied: ['basis=def2-TZVPP'],
      warnings: [],
      filename: 'water-energy.in', export_relative_path: 'aifs-inputs/water-energy/water-energy.in', validation: VALIDATION,
    })
  })

  it('rejects invalid arguments before any HTTP call', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const tool = mountPlugin().tools.get('generate_rest_input')
    await expect(tool?.execute({ ...GENERATE_ARGS, job_type: 'freq' }, EXEC))
      .rejects.toThrow(/job_type/)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it.each(['position_unit', 'charge', 'spin', 'basis'])('requires explicit %s without creating a plan', async field => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const tool = mountPlugin().tools.get('generate_rest_input')!
    const args: Record<string, unknown> = { ...GENERATE_ARGS }
    delete args[field]
    await expect(tool.execute(args, EXEC)).rejects.toThrow(field)
    await expect(tool.execute({ ...GENERATE_ARGS, [field]: null }, EXEC)).rejects.toThrow(field)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('returns ok=false for a backend domain error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({
      error: { code: 'basis_outside_pool', message: 'basis must stay inside the configured basis_set_pool' },
    }, 422)))
    const tool = mountPlugin().tools.get('generate_rest_input')
    const outcome = await tool?.execute({ ...GENERATE_ARGS, basis: '/etc/evil' }, EXEC)
    expect(outcome).toEqual({
      ok: false,
      error: { code: 'basis_outside_pool', message: 'basis must stay inside the configured basis_set_pool' },
    })
  })

  it('passes exec.signal to the HTTP request and honors caller abort', async () => {
    let seenSignal: AbortSignal | undefined
    vi.stubGlobal('fetch', vi.fn((_url: unknown, init: RequestInit) => {
      seenSignal = init.signal ?? undefined
      return new Promise((_resolve, reject) => {
        init.signal?.addEventListener('abort', () => reject(init.signal?.reason))
      })
    }))
    const controller = new AbortController()
    const tool = mountPlugin().tools.get('generate_rest_input')
    const pending = tool?.execute(GENERATE_ARGS, { signal: controller.signal })
    controller.abort(new Error('caller aborted'))
    await expect(pending).rejects.toThrow('caller aborted')
    expect(seenSignal?.aborted).toBe(true)
  })
})

describe('get_rest_capabilities tool', () => {
  it('reads a section schema from the backend and preserves provenance', async () => {
    const payload = { source_commit: 'reviewed-sha', keywords: { pressure: { type: 'scan', unit: 'atm' } } }
    const fetchMock = vi.fn(async (_url: URL, _init: RequestInit) => jsonResponse(payload))
    vi.stubGlobal('fetch', fetchMock)
    const result = await mountPlugin().tools.get('get_rest_capabilities')?.execute({ section: 'thermo' }, EXEC)
    expect(result).toEqual({ ok: true, ...payload })
    expect(fetchMock.mock.calls[0]![0].toString()).toBe('http://127.0.0.1:8000/v1/rest-capabilities?section=thermo')
    expect(fetchMock.mock.calls[0]![1].method).toBe('GET')
  })
})

describe('validate_rest_input tool', () => {
  it('returns a 200 valid=false domain result structurally', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({
      valid: false,
      errors: [{ code: 'out_of_range', message: 'spin must be >= 1', section: 'ctrl', field: 'spin', line: null }],
      warnings: [],
      parsed_sections: ['ctrl', 'geom'],
    })))
    const tool = mountPlugin().tools.get('validate_rest_input')
    const result = await tool?.execute({ rest_input: '[ctrl]\nspin = 0\n' }, EXEC)
    expect(result).toEqual({
      valid: false,
      errors: [{ code: 'out_of_range', message: 'spin must be >= 1', section: 'ctrl', field: 'spin', line: null }],
      warnings: [],
      parsed_sections: ['ctrl', 'geom'],
    })
  })
})

describe('retrieve_functional_evidence tool', () => {
  it('forwards a natural-language evidence query', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({
      retrieval_mode: 'lexical_fallback',
      query: 'water molecule',
      hits: [],
    })))
    const ctx = mountPlugin()
    const tool = ctx.tools.get('retrieve_functional_evidence')
    const result = await tool?.execute({ system_description: 'water molecule', limit: 3 }, EXEC)
    expect(result).toEqual({ retrieval_mode: 'lexical_fallback', query: 'water molecule', hits: [] })
  })
})

describe('durable AIFS workflow tools', () => {
  function workflowPayload() {
    const tasks = Array.from({ length: 40 }, (_, index) => ({
      task_id: `task_${index}`, title: `Calculation ${index}`, kind: 'rest', job_type: index === 0 ? 'opt' : 'energy',
      depends_on: index === 0 ? [] : ['task_0'],
      inputs: { position: `H 0 0 0\nH 0 0 ${index + 0.74}`, position_unit: 'angstrom', charge: 0, spin: 1 },
      decision: { xc: 'PBE', basis: 'def2-TZVP', source: 'user', rationale: 'Evidence detail '.repeat(500) },
      notes: 'Long notes '.repeat(500),
    }))
    return {
      plan_id: 'p-1', version: 3,
      plan: { goal: 'optimization_single_point', question: 'Optimize and compute energy', tasks },
      statuses: tasks.map(task => ({ task_id: task.task_id, state: task.task_id === 'task_0' ? 'ready_for_card' : 'needs_input', blockers: task.task_id === 'task_0' ? [] : ['optimized coordinates are missing'] })),
      cards: [{ card_id: 'c-0', task_id: 'task_0', filename: 'optimization.in', sha256: 'sha' }],
    }
  }

  function rendered(tool: NonNullable<ReturnType<ReturnType<typeof mountPlugin>['tools']['get']>>, args: unknown, value: unknown) {
    return JSON.parse((tool.output.render(args, value)[0] as { text: string }).text)
  }

  it.each(['create_aifs_plan', 'revise_aifs_plan', 'get_aifs_plan'])('renders %s as a compact summary while retaining its complete canonical result', async name => {
    const payload = workflowPayload()
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(payload)))
    const tool = mountPlugin().tools.get(name)!
    const args = name === 'create_aifs_plan'
      ? { plan: { question: 'force on water', goal: 'force', tasks: [] } }
      : name === 'revise_aifs_plan'
        ? { plan_id: 'p-1', expected_version: 2, change_reason: 'User changed question', patch: { question: 'New question' } }
        : { plan_id: 'p-1' }
    const result = await tool.execute(args, EXEC)
    expect(result).toEqual({ ok: true, ...payload })
    const summary = rendered(tool, args, result)
    expect(summary).toMatchObject({ ok: true, plan_id: 'p-1', version: 3, goal: 'optimization_single_point' })
    expect(summary.tasks).toHaveLength(40)
    expect(summary.tasks[0]).toMatchObject({ task_id: 'task_0', title: 'Calculation 0', state: 'ready_for_card', blockers: [], cards: [{ card_id: 'c-0', filename: 'optimization.in' }] })
    expect(summary.tasks[1]).toMatchObject({ depends_on: ['task_0'], state: 'needs_input', blockers: ['optimized coordinates are missing'] })
    const text = JSON.stringify(summary)
    expect(text).not.toContain('position')
    expect(text).not.toContain('rationale')
    expect(text).not.toContain('Long notes')
    expect(text.length).toBeLessThan(JSON.stringify(result).length / 10)
    expect(payload.plan.tasks[0]?.inputs.position).toBe('H 0 0 0\nH 0 0 0.74')
  })

  it('reads details of one task without changing the HTTP route or canonical response', async () => {
    const payload = workflowPayload()
    const fetchMock = vi.fn(async (_url: URL, _init: RequestInit) => jsonResponse(payload))
    vi.stubGlobal('fetch', fetchMock)
    const tool = mountPlugin().tools.get('get_aifs_plan')!
    const args = { plan_id: 'p-1', version: 3, task_id: 'task_0' }
    const result = await tool.execute(args, EXEC)
    expect(result).toEqual({ ok: true, ...payload })
    expect(fetchMock.mock.calls[0]![0].toString()).toBe('http://127.0.0.1:8000/v1/plans/p-1?version=3')
    const detail = rendered(tool, args, result)
    expect(detail.task).toEqual(payload.plan.tasks[0])
    expect(detail.status.task_id).toBe('task_0')
    expect(detail.cards).toEqual(payload.cards)
    expect(detail.tasks).toBeUndefined()
    expect(JSON.stringify(detail)).not.toContain('Calculation 1')
  })

  it('keeps historical card applicability visible in the compact summary', () => {
    const payload = { ok: true, ...workflowPayload() }
    Object.assign(payload.cards[0]!, {
      version: 1, is_current_plan_version: false, is_applicable_to_current_plan: true,
    })
    const tool = mountPlugin().tools.get('get_aifs_plan')!
    expect(rendered(tool, {}, payload).tasks[0].cards[0]).toMatchObject({
      card_id: 'c-0', version: 1,
      is_current_plan_version: false, is_applicable_to_current_plan: true,
    })
  })

  it('allows explicit full export and reports an unknown task without leaking the full plan', async () => {
    const payload = { ok: true, ...workflowPayload() }
    const tool = mountPlugin().tools.get('get_aifs_plan')!
    expect(rendered(tool, { view: 'full' }, payload)).toEqual(payload)
    expect(rendered(tool, { task_id: 'missing' }, payload)).toEqual({
      ok: false, error: { code: 'task_not_found', message: 'No task missing in this plan version' },
      plan_id: 'p-1', version: 3,
    })
    expect(rendered(tool, { task_id: 'task_0', view: 'full' }, payload).task).toEqual(payload.plan.tasks[0])
  })

  it('preserves domain errors in all plan views and contract errors remain failures', async () => {
    const error = { ok: false, error: { code: 'version_conflict', message: 'reload before editing' } }
    const ctx = mountPlugin()
    for (const name of ['create_aifs_plan', 'revise_aifs_plan', 'get_aifs_plan']) {
      const tool = ctx.tools.get(name)!
      expect(rendered(tool, {}, error)).toEqual(error)
      expect(rendered(tool, { task_id: 'missing', view: 'full' }, error)).toEqual(error)
    }
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ error: { code: 'request_validation_error', detail: [{ loc: ['body', 'invented'] }] } }, 422)))
    await expect(ctx.tools.get('get_aifs_plan')!.execute({ plan_id: 'p-1' }, EXEC)).rejects.toThrow('request_validation_error')
  })

  it('creates a plan and reads it back over the intended HTTP routes', async () => {
    const fetchMock = vi.fn(async (url: URL, init: RequestInit) => {
      if (init.method === 'POST') return jsonResponse({ plan_id: 'p-1', version: 1, statuses: [] }, 201)
      return jsonResponse({ plan_id: 'p-1', version: 1, statuses: [] })
    })
    vi.stubGlobal('fetch', fetchMock)
    const ctx = mountPlugin()
    const plan = { question: 'force on water', goal: 'force', tasks: [] }
    const created = await ctx.tools.get('create_aifs_plan')?.execute({ plan }, EXEC)
    expect(created).toEqual({ ok: true, plan_id: 'p-1', version: 1, statuses: [] })
    const read = await ctx.tools.get('get_aifs_plan')?.execute({ plan_id: 'p-1' }, EXEC)
    expect(read).toEqual({ ok: true, plan_id: 'p-1', version: 1, statuses: [] })
    expect((fetchMock.mock.calls[0] as unknown as [URL, RequestInit])[0].toString()).toBe('http://127.0.0.1:8000/v1/plans')
    expect((fetchMock.mock.calls[1] as unknown as [URL, RequestInit])[0].toString()).toBe('http://127.0.0.1:8000/v1/plans/p-1')
  })

  it('returns task blockers as structured domain results', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({
      error: { code: 'task_not_ready', message: 'optimized coordinates missing' },
    }, 422)))
    const result = await mountPlugin().tools.get('generate_aifs_task_card')?.execute({ plan_id: 'p-1', task_id: 'sp' }, EXEC)
    expect(result).toEqual({ ok: false, error: { code: 'task_not_ready', message: 'optimized coordinates missing' } })
  })
})
