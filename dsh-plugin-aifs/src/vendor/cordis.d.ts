/**
 * Ambient mirror of the `@deepseek-ai/cordis` subset this plugin uses.
 *
 * The plugin is developed outside the deepseek-harness workspace, where the
 * real package is not installable. This declaration is type-only and matches
 * the public API surface used here; when the plugin is mounted into the
 * harness workspace the real package resolves and this mirror can be deleted.
 */
declare module '@deepseek-ai/cordis' {
  import type { SubprocessService } from '../desktop/runtime.ts'
  import type { SkillService } from '../desktop/skill.ts'
  import type { ConnectionService } from '../desktop/routes.ts'
  import type { ToolRuntime } from '@deepseek-ai/dsh-tools'

  export interface SystemPromptSection {
    name: string
    order: number
    text: string
  }

  export interface SystemPrompt {
    section(section: SystemPromptSection): () => void
  }

  export interface Context {
    /** Tool registry service injected via the plugin's `inject: ['tools']`. */
    tools: ToolRuntime
    /** Prompt registry used to add model-facing domain guidance. */
    systemPrompt: SystemPrompt
    /** Register a lifecycle effect; the callback's return value runs on dispose. */
    subprocess: SubprocessService
    skills: SkillService
    connection: ConnectionService
    inject(services: string[], callback: (child: Context) => void): unknown
    effect(fn: () => () => void | Promise<void>): void
  }
}
