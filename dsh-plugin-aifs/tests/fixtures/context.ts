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
  readonly systemPrompt: {
    section(section: { name: string; order: number; text: string }): () => void
    sections(): Array<{ name: string; order: number; text: string }>
  }
  inject(services: string[], callback: (child: Context) => void): void
  effect(fn: () => () => void | Promise<void>): void
  dispose(): Promise<void>
}

export function createTestContext(services: Record<string, unknown> = {}): TestContext {
  const registry = new Map<string, ToolDefinition>()
  const promptSections: Array<{ name: string; order: number; text: string }> = []
  const cleanups: Array<() => void | Promise<void>> = []
  const ctx: TestContext = {
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
    systemPrompt: {
      section(section) {
        promptSections.push(section)
        return () => {
          const index = promptSections.indexOf(section)
          if (index >= 0) promptSections.splice(index, 1)
        }
      },
      sections: () => [...promptSections],
    },
    inject(required, callback) {
      if (required.every(name => name in services)) callback(ctx as unknown as Context)
    },
    effect(fn) {
      cleanups.push(fn())
    },
    async dispose() {
      for (const cleanup of cleanups.reverse()) await cleanup()
    },
  }
  Object.assign(ctx, services)
  return ctx
}

/** Mount the plugin on a fresh fake context with default config. */
export function mountPlugin(config: Record<string, unknown> = {}): TestContext {
  const ctx = createTestContext()
  apply(ctx as unknown as Context, Config.parse(config))
  return ctx
}
