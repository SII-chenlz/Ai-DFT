/**
 * Minimal schemastery-compatible runtime used for the plugin `Config`.
 *
 * Stand-in for `@deepseek-ai/schemastery`, which is not installable outside
 * the deepseek-harness workspace; tests alias the package name to this file
 * (see `vitest.config.ts`). It implements only the subset the plugin uses:
 * `z.object` over `z.string()` / `z.number()` with `.default()`. When the
 * plugin is mounted into the harness the real package resolves instead and
 * this file can be deleted.
 */

export interface ZSchema<T> {
  parse(value: unknown): T
}

class StringSchema implements ZSchema<string> {
  private readonly defaultValue: string | undefined

  constructor(defaultValue?: string) {
    this.defaultValue = defaultValue
  }

  default(value: string): StringSchema {
    return new StringSchema(value)
  }

  parse(value: unknown): string {
    const resolved = value === undefined ? this.defaultValue : value
    if (typeof resolved !== 'string') {
      throw new Error(`expected a string, got ${JSON.stringify(resolved)}`)
    }
    return resolved
  }
}

class NumberSchema implements ZSchema<number> {
  private readonly defaultValue: number | undefined

  constructor(defaultValue?: number) {
    this.defaultValue = defaultValue
  }

  default(value: number): NumberSchema {
    return new NumberSchema(value)
  }

  parse(value: unknown): number {
    const resolved = value === undefined ? this.defaultValue : value
    if (typeof resolved !== 'number' || !Number.isFinite(resolved)) {
      throw new Error(`expected a finite number, got ${JSON.stringify(resolved)}`)
    }
    return resolved
  }
}

class ObjectSchema<S extends Record<string, ZSchema<unknown>>>
implements ZSchema<{ [K in keyof S]: S[K] extends ZSchema<infer T> ? T : never }> {
  private readonly shape: S

  constructor(shape: S) {
    this.shape = shape
  }

  parse(value: unknown): { [K in keyof S]: S[K] extends ZSchema<infer T> ? T : never } {
    if (typeof value !== 'object' || value === null || Array.isArray(value)) {
      throw new Error(`expected an object, got ${JSON.stringify(value)}`)
    }
    const record = value as Record<string, unknown>
    const result = {} as { [K in keyof S]: S[K] extends ZSchema<infer T> ? T : never }
    for (const [key, schema] of Object.entries(this.shape)) {
      result[key as keyof S] = schema.parse(record[key]) as never
    }
    return result
  }
}

/**
 * Type-level mirror of schemastery's `z<T>`: the schema whose `parse` yields a
 * `T`. Declared alongside the const `z` (value namespace + type namespace),
 * like the real package, so `z<Config>` works in type position.
 */
export interface z<T = unknown> extends ZSchema<T> {
  string(): StringSchema
  number(): NumberSchema
  object<S extends Record<string, ZSchema<unknown>>>(shape: S): ObjectSchema<S>
}

export const z = {
  string(): StringSchema {
    return new StringSchema()
  },
  number(): NumberSchema {
    return new NumberSchema()
  },
  object<S extends Record<string, ZSchema<unknown>>>(shape: S): ObjectSchema<S> {
    return new ObjectSchema(shape)
  },
} as unknown as z

// The official @deepseek-ai/schemastery package exposes this constructor as
// its default export. Keep the named export for the local test shim, but make
// the default export the compatibility contract used by the plugin.
export default z
