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
}

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
    })))
    const tool = mountPlugin().tools.get('generate_rest_input')
    const outcome = await tool?.execute(GENERATE_ARGS, EXEC)
    expect(outcome).toEqual({
      ok: true,
      rest_input: '[ctrl]\nxc = "B3LYP"\n',
      effective_settings: { xc: 'B3LYP' },
      defaults_applied: ['basis=def2-TZVPP'],
      warnings: [],
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
