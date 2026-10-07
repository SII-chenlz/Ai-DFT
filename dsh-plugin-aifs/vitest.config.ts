import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitest/config'

/**
 * Isolated unit tests use two test doubles. Production bundles the real
 * package helpers; verify-desktop-host.mjs checks real DSH services.
 *
 * - `@deepseek-ai/dsh-tools` -> a faithful subset of `defineTool` that
 *   compiles the declared schemas to JSON Schema and validates arguments and
 *   canonical output values;
 * - `@deepseek-ai/schemastery` -> tests/fixtures/schemastery.ts.
 */
export default defineConfig({
  resolve: {
    alias: {
      '@deepseek-ai/dsh-tools': fileURLToPath(
        new URL('./tests/fixtures/dsh-tools.ts', import.meta.url),
      ),
      '@deepseek-ai/schemastery': fileURLToPath(
        new URL('./tests/fixtures/schemastery.ts', import.meta.url),
      ),
    },
  },
  test: {
    include: ['tests/**/*.spec.ts'],
  },
})
