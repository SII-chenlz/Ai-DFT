import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitest/config'

/**
 * This package is developed outside the deepseek-harness pnpm workspace, so
 * the harness packages are not installable here. The two runtime imports the
 * plugin makes are resolved to local stand-ins in tests only:
 *
 * - `@deepseek-ai/dsh-tools` -> a faithful subset of `defineTool` that
 *   compiles the declared schemas to JSON Schema and validates arguments and
 *   canonical output values;
 * - `@deepseek-ai/schemastery` -> the minimal runtime in `src/vendor/z.ts`.
 *
 * When the plugin is mounted into the harness workspace, the real packages
 * resolve normally and no source change is required.
 */
export default defineConfig({
  resolve: {
    alias: {
      '@deepseek-ai/dsh-tools': fileURLToPath(
        new URL('./tests/fixtures/dsh-tools.ts', import.meta.url),
      ),
      '@deepseek-ai/schemastery': fileURLToPath(
        new URL('./src/vendor/z.ts', import.meta.url),
      ),
    },
  },
  test: {
    include: ['tests/**/*.spec.ts'],
  },
})
