/**
 * Ambient mirror of the `@deepseek-ai/cordis` subset this plugin uses.
 *
 * The plugin is developed outside the deepseek-harness workspace, where the
 * real package is not installable. This declaration is type-only and matches
 * the public API surface used here; when the plugin is mounted into the
 * harness workspace the real package resolves and this mirror can be deleted.
 */
declare module '@deepseek-ai/cordis' {
  import type { ToolRuntime } from '@deepseek-ai/dsh-tools'

  export interface Context {
    /** Tool registry service injected via the plugin's `inject: ['tools']`. */
    tools: ToolRuntime
    /** Register a lifecycle effect; the callback's return value runs on dispose. */
    effect(fn: () => () => void | Promise<void>): void
  }
}
