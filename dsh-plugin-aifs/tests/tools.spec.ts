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
