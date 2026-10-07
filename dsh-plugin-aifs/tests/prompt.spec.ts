import { describe, expect, it } from 'vitest'

import { AIFS_PROMPT_TEXT } from '../src/index.ts'
import { mountPlugin } from './fixtures/context.ts'

describe('AIFS system-prompt guidance', () => {
  it('keeps guidance and tool schemas available while the managed service is unavailable', async () => {
    const ctx = mountPlugin({ backendMode: 'managed' })
    expect(ctx.tools.names()).toHaveLength(10)
    expect(ctx.systemPrompt.sections()).toContainEqual({
      name: 'aifs:guidance',
      order: 80,
      text: AIFS_PROMPT_TEXT,
    })
    await ctx.dispose()
    expect(ctx.tools.names()).toEqual([])
    expect(ctx.systemPrompt.sections()).toEqual([])
  })

  it('puts task-level DSH web retrieval before local supplementary records', () => {
    expect(AIFS_PROMPT_TEXT).toContain('For each calculation task and method decision')
    expect(AIFS_PROMPT_TEXT.indexOf('web_search')).toBeLessThan(
      AIFS_PROMPT_TEXT.indexOf('retrieve_functional_evidence'),
    )
    expect(AIFS_PROMPT_TEXT).toContain('web_fetch to read any page before citing it')
    expect(AIFS_PROMPT_TEXT).toContain('method_used, comparative_benchmark')
    expect(AIFS_PROMPT_TEXT).toContain('keep opposing evidence and uncertainty')
    expect(AIFS_PROMPT_TEXT).toContain('if no relevant source is found, keep the choice provisional')
  })

  it('registers stable guidance and removes it on context disposal', async () => {
    const ctx = mountPlugin()
    expect(ctx.systemPrompt.sections()).toContainEqual({
      name: 'aifs:guidance',
      order: 80,
      text: AIFS_PROMPT_TEXT,
    })

    await ctx.dispose()
    expect(ctx.systemPrompt.sections()).toEqual([])
  })
})
