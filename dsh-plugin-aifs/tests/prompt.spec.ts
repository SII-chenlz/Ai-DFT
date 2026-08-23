import { describe, expect, it } from 'vitest'

import { AIFS_PROMPT_TEXT } from '../src/index.ts'
import { mountPlugin } from './fixtures/context.ts'

describe('AIFS system-prompt guidance', () => {
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
