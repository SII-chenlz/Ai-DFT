/**
 * AIFS plugin: Cordis function plugin registering the AIFS REST input tools.
 *
 * Exports the Cordis function-plugin contract (`name`, `inject`, `Config`,
 * `apply`, no default export). `apply` registers exactly two tools —
 * `generate_rest_input` and `validate_rest_input` — backed by HTTP calls to
 * the AIFS FastAPI backend, and unregisters both when the context disposes.
 * The recommender, RAG and REST execution are deliberately out of scope.
 */

import type { Context } from '@deepseek-ai/cordis'
import z from '@deepseek-ai/schemastery'
import {
  AifsBackendClient,
  DEFAULT_BASE_URL,
  DEFAULT_MAX_RESPONSE_BYTES,
  DEFAULT_REQUEST_TIMEOUT_MS,
  assertClientConfig,
} from './client.ts'
import type { AifsClientConfig } from './client.ts'
import { defineGenerateRestInputTool, defineValidateRestInputTool } from './tools.ts'

/** Cordis function-plugin name. */
export const name = 'aifs'

/** Services the plugin requires before its `apply` runs. */
export const inject = ['tools'] as const

/** Deployment-facing configuration of the AIFS plugin. */
export interface Config extends AifsClientConfig {}

/**
 * Runtime schema for {@link Config}. Timeout, response-size cap and API
 * address are explicit configuration with defaults; invalid values fail
 * loudly in {@link apply}.
 */
export const Config = z.object({
  baseUrl: z.string().default(DEFAULT_BASE_URL),
  requestTimeoutMs: z.number().default(DEFAULT_REQUEST_TIMEOUT_MS),
  maxResponseBytes: z.number().default(DEFAULT_MAX_RESPONSE_BYTES),
}) as unknown as ((data?: unknown) => Config) & {
  /** Local shim convenience; the real schemastery schema is callable. */
  parse(value: unknown): Config
}

/**
 * Install the AIFS REST tools. Registration goes through the tools registry
 * (an effect of its own); the returned disposers are collected so the tools
 * are unregistered when the context disposes.
 */
export function apply(ctx: Context, config: Config): void {
  assertClientConfig(config)
  ctx.effect(() => {
    const client = new AifsBackendClient(config)
    const disposeGenerate = ctx.tools.register(defineGenerateRestInputTool(client))
    const disposeValidate = ctx.tools.register(defineValidateRestInputTool(client))
    return () => {
      disposeValidate()
      disposeGenerate()
    }
  })
}
