/**
 * Ambient mirror of the `@deepseek-ai/schemastery` subset used for the plugin
 * `Config` (string/number schemas with defaults inside `z.object`). The real
 * package resolves when the plugin is mounted into the harness workspace.
 *
 * `z` is declared twice, like the real package: the value is the schema
 * factory and the interface is the type-level helper (`z<Config>` names the
 * schema whose `parse` yields a `Config`).
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

  /** Type-level mirror of schemastery's `z<T>`. */
  export interface z<T = unknown> extends ZSchema<T> {
    string(): StringSchema
    number(): NumberSchema
    object<S extends Record<string, ZSchema<unknown>>>(shape: S): ObjectSchema<S>
  }

  export const z: z
}
