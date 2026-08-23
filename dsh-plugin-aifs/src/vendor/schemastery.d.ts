/**
 * Ambient mirror of the `@deepseek-ai/schemastery` subset used for the plugin
 * `Config` (string/number schemas with defaults inside `z.object`). The real
 * package resolves when the plugin is mounted into the harness workspace.
 *
 * The real package exports its schema factory as the default export. This
 * ambient declaration intentionally follows that public contract so
 * `tsc` checks the plugin against the same import shape used by Harness.
 */
declare module '@deepseek-ai/schemastery' {
  export interface ZSchema<T> {
    parse(value: unknown): T
  }

  export interface StringSchema extends ZSchema<string> {
    default(value: string): StringSchema
  }

  export interface NumberSchema extends ZSchema<number> {
    default(value: number): NumberSchema
  }

  export interface ObjectSchema<S extends Record<string, ZSchema<unknown>>>
    extends ZSchema<{ [K in keyof S]: S[K] extends ZSchema<infer T> ? T : never }> {}

  /** Type-level mirror retained for consumers that use the generic schema type. */
  export interface z<T = unknown> extends ZSchema<T> {
  }

  interface ZFactory {
    string(): StringSchema
    number(): NumberSchema
    object<S extends Record<string, ZSchema<unknown>>>(shape: S): ObjectSchema<S>
  }

  const z: ZFactory
  export default z
}
