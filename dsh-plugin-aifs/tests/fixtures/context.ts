/**
 * Minimal fake of the Cordis context surface the plugin touches: a tool
 * registry whose `register` returns a working disposer, and an `effect`
 * hook whose returned cleanup runs on dispose — the same lifecycle the real
 * Cordis context provides.
 */

import type { Context } from '@deepseek-ai/cordis'
import type { ToolDefinition } from '@deepseek-ai/dsh-tools'
import { apply, Config } from '../../src/index.ts'

export interface TestContext {
  readonly tools: {
    register(definition: ToolDefinition): () => void
    names(): string[]
    get(name: string): ToolDefinition | undefined
  }
  effect(fn: () => () => void | Promise<void>): void
  dispose(): Promise<void>
}

export function createTestContext(): TestContext {
  const registry = new Map<string, ToolDefinition>()
  let cleanup: (() => void | Promise<void>) | undefined
  return {
    tools: {
      register(definition) {
        registry.set(definition.name, definition)
        return () => {
          registry.delete(definition.name)
        }
      },
      names: () => [...registry.keys()],
      get: (name) => registry.get(name),
    },
    effect(fn) {
      cleanup = fn()
    },
    async dispose() {
      await cleanup?.()
    },
  }
}

/** Mount the plugin on a fresh fake context with default config. */
export function mountPlugin(config: Record<string, unknown> = {}): TestContext {
  const ctx = createTestContext()
  apply(ctx as unknown as Context, Config.parse(config))
  return ctx
}
