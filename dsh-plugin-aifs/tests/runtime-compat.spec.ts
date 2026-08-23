import { describe, expect, it } from 'vitest'

import z from '../src/vendor/z.ts'

describe('official Harness schemastery compatibility', () => {
  it('exposes the default schema constructor convention', () => {
    expect(typeof z.object).toBe('function')
  })
})
