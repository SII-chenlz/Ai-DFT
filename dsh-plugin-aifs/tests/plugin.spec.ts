/** Plugin contract: exports, registration, disposal, config validation. */

import { describe, expect, it } from 'vitest'
import type { Context } from '@deepseek-ai/cordis'
import { apply, Config, inject, name } from '../src/index.ts'
import { createTestContext, mountPlugin } from './fixtures/context.ts'

describe('aifs plugin', () => {
  it('exports the Cordis function-plugin contract with no default export', () => {
    expect(name).toBe('aifs')
    expect(inject).toEqual(['tools'])
    expect(typeof apply).toBe('function')
    expect(typeof Config.parse).toBe('function')
  })

  it('registers exactly the two REST tools', () => {
    const ctx = mountPlugin()
    expect(ctx.tools.names()).toEqual(['generate_rest_input', 'validate_rest_input'])
  })

  it('unregisters both tools when the context disposes', async () => {
    const ctx = mountPlugin()
    expect(ctx.tools.names().length).toBe(2)
    await ctx.dispose()
    expect(ctx.tools.names()).toEqual([])
  })

  it('applies config defaults matching the architecture spec', () => {
    const config = Config.parse({})
    expect(config).toEqual({
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
