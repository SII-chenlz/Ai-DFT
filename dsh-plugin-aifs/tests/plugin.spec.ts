/** Plugin contract: exports, registration, disposal, config validation. */

import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it, vi } from 'vitest'
import type { Context } from '@deepseek-ai/cordis'
import { apply, Config, inject, name } from '../src/index.ts'
import { createTestContext, mountPlugin } from './fixtures/context.ts'

describe('aifs plugin', () => {
  it('exports the Cordis function-plugin contract with no default export', () => {
    expect(name).toBe('aifs')
    expect(inject).toEqual(['tools', 'systemPrompt'])
    expect(typeof apply).toBe('function')
    expect(typeof Config.parse).toBe('function')
  })

  it('registers REST, evidence and durable workflow tools', () => {
    const ctx = mountPlugin()
    expect(ctx.tools.names()).toEqual([
      'generate_rest_input',
      'validate_rest_input',
      'retrieve_functional_evidence',
      'create_aifs_plan',
      'revise_aifs_plan',
      'list_aifs_plans',
      'get_aifs_plan',
      'generate_aifs_task_card',
      'get_aifs_card',
      'get_rest_capabilities',
    ])
  })

  it('unregisters all tools when the context disposes', async () => {
    const ctx = mountPlugin()
    expect(ctx.tools.names().length).toBe(10)
    await ctx.dispose()
    expect(ctx.tools.names()).toEqual([])
  })

  it('exposes schemas before subprocess injection, with no external-server fallback', async () => {
    const ctx = mountPlugin({ backendMode: 'managed' })
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    try {
      expect(ctx.tools.names()).toHaveLength(10)
      await expect(ctx.tools.get('get_rest_capabilities')!.execute({}, { signal: new AbortController().signal }))
        .rejects.toThrow('DSH 子进程服务')
      expect(fetchMock).not.toHaveBeenCalled()
    } finally { fetchMock.mockRestore(); await ctx.dispose() }
  })

  it('retains tools after runtime startup failure and reports its cause', async () => {
    const dataDir = mkdtempSync(join(tmpdir(), 'AIFS failed plugin '))
    const spawn = vi.fn()
    const ctx = createTestContext({ subprocess: { spawn } })
    const fetchMock = vi.spyOn(globalThis, 'fetch')
    try {
      apply(ctx as unknown as Context, Config.parse({ backendMode: 'managed', dataDir, runtimeRoot: join(dataDir, 'missing') }))
      expect(ctx.tools.names()).toHaveLength(10)
      await expect(ctx.tools.get('get_rest_capabilities')!.execute({}, { signal: new AbortController().signal }))
        .rejects.toThrow(/AIFS 后端尚不可用.*ENOENT/)
      expect(spawn).not.toHaveBeenCalled()
      expect(fetchMock).not.toHaveBeenCalled()
      expect(ctx.tools.names()).toHaveLength(10)
    } finally { fetchMock.mockRestore(); await ctx.dispose(); rmSync(dataDir, { recursive: true, force: true }) }
    expect(ctx.tools.names()).toEqual([])
  })

  it('applies config defaults matching the architecture spec', () => {
    const config = Config.parse({})
    expect(config).toEqual({
      backendMode: 'external', runtimeRoot: '', dataDir: '', startupTimeoutMs: 30000, shutdownTimeoutMs: 10000,
      baseUrl: 'http://127.0.0.1:8000',
      requestTimeoutMs: 30_000,
      maxResponseBytes: 1_048_576,
    })
  })

  it('fails loud on invalid config before registering anything', () => {
    const ctx = createTestContext()
    const context = ctx as unknown as Context
    expect(() => apply(context, Config.parse({ requestTimeoutMs: 0 }))).toThrow(/requestTimeoutMs/)
    expect(() => apply(context, Config.parse({ baseUrl: 'not-a-url' }))).toThrow(/baseUrl/)
    expect(ctx.tools.names()).toEqual([])
  })
})
