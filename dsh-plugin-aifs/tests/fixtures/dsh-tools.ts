/**
 * Test double for `@deepseek-ai/dsh-tools.defineTool` (see vitest.config.ts).
 *
 * Implements a faithful subset of the real helper: compiles the declared
 * parameter and output schemas to JSON Schema, validates arguments before
 * execution and the canonical output value after it, exactly like the real
 * registry does. That makes the schema tests in this package meaningful: the
 * JSON Schemas asserted here are the ones argument validation actually runs.
 */

import type {
  ContentBlock,
  ParameterSchemaSpec,
  ToolDefinition,
  ToolRunContext,
  ValueSchemaSpec,
} from '@deepseek-ai/dsh-tools'

/** Compiled JSON Schema subset produced by {@link compileValue}. */
export interface JsonSchema {
  type?: 'string' | 'number' | 'integer' | 'boolean' | 'array' | 'object' | 'null'
  properties?: Record<string, JsonSchema>
  required?: string[]
  items?: JsonSchema
  enum?: unknown[]
  const?: unknown
  additionalProperties?: boolean
  oneOf?: JsonSchema[]
}

export function compileValue(spec: ValueSchemaSpec): JsonSchema {
  if ('oneOf' in spec) {
    return { oneOf: spec.oneOf.map(compileValue) }
  }
  const node: JsonSchema = { type: spec.type === 'json' ? undefined : spec.type }
  if ('enum' in spec && spec.enum !== undefined) node.enum = [...spec.enum]
  if ('const' in spec && spec.const !== undefined) node.const = spec.const
  if ('additionalProperties' in spec) node.additionalProperties = spec.additionalProperties
  if (spec.type === 'object' && 'properties' in spec && spec.properties !== undefined) {
    node.properties = Object.fromEntries(
      Object.entries(spec.properties).map(([key, property]) => [key, compileValue(property)]),
    )
    node.required = Object.entries(spec.properties)
      .filter(([, property]) => property.required === true)
      .map(([key]) => key)
  }
  if (spec.type === 'array' && 'items' in spec && spec.items !== undefined) {
    node.items = compileValue(spec.items)
  }
  return node
}

export function validateValue(schema: JsonSchema, value: unknown, path: string): string[] {
  if (schema.oneOf !== undefined) {
    for (const branch of schema.oneOf) {
      if (validateValue(branch, value, path).length === 0) return []
    }
    return [`${path}: value matches no branch of oneOf`]
  }
  if (schema.const !== undefined && value !== schema.const) {
    return [`${path}: expected const ${JSON.stringify(schema.const)}`]
  }
  if (schema.enum !== undefined && !schema.enum.includes(value)) {
    return [`${path}: value not in enum`]
  }
  const violations: string[] = []
  if (schema.type !== undefined) {
    if (schema.type === 'integer') {
      if (typeof value !== 'number' || !Number.isInteger(value)) {
        violations.push(`${path}: expected integer`)
      }
    } else if (schema.type === 'array') {
      if (!Array.isArray(value)) violations.push(`${path}: expected array`)
    } else if (schema.type === 'null') {
      if (value !== null) violations.push(`${path}: expected null`)
    } else if (typeof value !== schema.type) {
      violations.push(`${path}: expected ${schema.type}`)
    }
  }
  if (schema.type === 'array' && Array.isArray(value) && schema.items !== undefined) {
    value.forEach((item, index) => {
      violations.push(...validateValue(schema.items as JsonSchema, item, `${path}[${index}]`))
    })
  }
  if (schema.type === 'object' && typeof value === 'object' && value !== null && !Array.isArray(value)) {
    const record = value as Record<string, unknown>
    for (const key of Object.keys(record)) {
      const property = schema.properties?.[key]
      if (property !== undefined) {
        violations.push(...validateValue(property, record[key], `${path}.${key}`))
      } else if (schema.additionalProperties === false) {
        violations.push(`${path}.${key}: additional property not allowed`)
      }
    }
    for (const key of schema.required ?? []) {
      if (!(key in record)) violations.push(`${path}.${key}: required property missing`)
    }
  }
  return violations
}

export interface DefineToolOptions {
  readonly name: string
  readonly description: string
  readonly parameters: ParameterSchemaSpec
  readonly output: {
    readonly schema: ValueSchemaSpec
    render(args: unknown, value: unknown): ContentBlock[]
  }
  execute(args: unknown, exec: ToolRunContext): Promise<unknown>
}

export function defineTool(options: DefineToolOptions): ToolDefinition {
  // The real parameter root is an implicit open object with per-property
  // requiredness; unknown argument keys are tolerated, like the harness.
  const parameterSchema: JsonSchema = {
    type: 'object',
    additionalProperties: true,
    properties: Object.fromEntries(
      Object.entries(options.parameters).map(([key, property]) => [key, compileValue(property)]),
    ),
    required: Object.entries(options.parameters)
      .filter(([, property]) => property.required === true)
      .map(([key]) => key),
  }
  const outputSchema = compileValue(options.output.schema)
  return {
    name: options.name,
    description: options.description,
    parameters: parameterSchema as unknown as Record<string, unknown>,
    output: {
      schema: outputSchema,
      render: options.output.render,
    },
    async execute(args: unknown, exec: ToolRunContext): Promise<unknown> {
      const argumentViolations = validateValue(parameterSchema, args, '')
      if (argumentViolations.length > 0) {
        throw new Error(`invalid arguments for ${options.name}: ${argumentViolations.join('; ')}`)
      }
      const value = await options.execute(args, exec)
      const outputViolations = validateValue(outputSchema, value, '')
      if (outputViolations.length > 0) {
        throw new Error(`invalid canonical output for ${options.name}: ${outputViolations.join('; ')}`)
      }
      return value
    },
  }
}
