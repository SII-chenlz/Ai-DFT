/**
 * Ambient mirror of the `@deepseek-ai/dsh-tools` subset this plugin uses
 * (`defineTool` and its schema DSL). Type-only stand-in for development
 * outside the deepseek-harness workspace; the real package resolves when the
 * plugin is mounted into the harness, and this mirror can be deleted then.
 */
declare module '@deepseek-ai/dsh-tools' {
  /** Annotation keywords shared by every author-facing schema node. */
  export interface ValueSchemaAnnotations {
    description?: string
    title?: string
    default?: unknown
    examples?: unknown
  }

  export interface StringValueSchemaSpec extends ValueSchemaAnnotations {
    type: 'string'
    enum?: readonly string[]
    const?: string
  }

  export interface NumberValueSchemaSpec extends ValueSchemaAnnotations {
    type: 'number'
    enum?: readonly number[]
    const?: number
  }

  export interface IntegerValueSchemaSpec extends ValueSchemaAnnotations {
    type: 'integer'
    enum?: readonly number[]
    const?: number
  }

  export interface BooleanValueSchemaSpec extends ValueSchemaAnnotations {
    type: 'boolean'
    enum?: readonly boolean[]
    const?: boolean
  }

  export interface NullValueSchemaSpec extends ValueSchemaAnnotations {
    type: 'null'
  }

  export interface ArrayValueSchemaSpec extends ValueSchemaAnnotations {
    type: 'array'
    items?: ValueSchemaSpec
  }

  export interface ObjectValueSchemaSpec extends ValueSchemaAnnotations {
    type: 'object'
    properties?: ParameterSchemaSpec
    additionalProperties: boolean
  }

  export interface JsonValueSchemaSpec extends ValueSchemaAnnotations {
    type: 'json'
  }

  export interface OneOfValueSchemaSpec extends ValueSchemaAnnotations {
    oneOf: readonly [ValueSchemaSpec, ValueSchemaSpec, ...ValueSchemaSpec[]]
  }

  export type ValueSchemaSpec =
    | StringValueSchemaSpec
    | NumberValueSchemaSpec
    | IntegerValueSchemaSpec
    | BooleanValueSchemaSpec
    | NullValueSchemaSpec
    | ArrayValueSchemaSpec
    | ObjectValueSchemaSpec
    | JsonValueSchemaSpec
    | OneOfValueSchemaSpec

  /** One implicit parameter-root property, optionally required. */
  export type ParameterPropertySpec = ValueSchemaSpec & { required?: true }

  /** Tool parameter schema: an implicit open object root of properties. */
  export type ParameterSchemaSpec = {
    [key: string]: ParameterPropertySpec
  }

  /** Simplified inference over the subset above (bounded, like the real one). */
  type InferNode<S, D extends unknown[]> =
    D['length'] extends 8 ? unknown :
      S extends { const: infer C } ? C :
        S extends { enum: readonly (infer E)[] } ? E :
          S extends { type: 'string' } ? string :
            S extends { type: 'number' | 'integer' } ? number :
              S extends { type: 'boolean' } ? boolean :
                S extends { type: 'null' } ? null :
                  S extends { type: 'array'; items: infer I } ? InferNode<I, [unknown, ...D]>[] :
                    S extends { type: 'object'; properties: infer P; additionalProperties: boolean }
                      ? (P extends ParameterSchemaSpec
                          ? InferArgs<P, [unknown, ...D]>
                          : Record<string, unknown>) &
                          (S['additionalProperties'] extends true ? Record<string, unknown> : {})
                      : unknown

  /** Infer the TypeScript argument object for a parameter schema. */
  export type InferArgs<S, D extends unknown[] = []> = {
    [K in keyof S as S[K] extends { required: true } ? K : never]: InferNode<S[K], D>
  } & {
    [K in keyof S as S[K] extends { required: true } ? never : K]?: InferNode<S[K], D>
  }

  /** Infer the TypeScript value accepted by a value schema. */
  export type InferValue<S> = InferNode<S, []>

  export interface ContentBlock {
    type: string
    text: string
  }

  /** Runtime context handed to a tool body; cancellation rides `signal`. */
  export interface ToolRunContext {
    readonly signal: AbortSignal
  }

  export interface ToolDefinition {
    readonly name: string
    readonly description: string
    readonly parameters: Record<string, unknown>
    readonly output: {
      readonly schema: unknown
      render(args: unknown, value: unknown): ContentBlock[]
    }
    execute(args: unknown, exec: ToolRunContext): Promise<unknown>
  }

  export interface ToolRuntime {
    /** Register a tool; the returned disposer unregisters it. */
    register(definition: ToolDefinition): () => void
  }

  export interface DefineToolOptions<
    S extends ParameterSchemaSpec,
    O extends ValueSchemaSpec,
  > {
    readonly name: string
    readonly description: string
    readonly parameters: S
    readonly output: {
      readonly schema: O
      render(args: InferArgs<S>, value: InferValue<O>): ContentBlock[]
    }
    execute(args: InferArgs<S>, exec: ToolRunContext): Promise<InferValue<O>>
  }

  export function defineTool<
    const S extends ParameterSchemaSpec,
    const O extends ValueSchemaSpec,
  >(options: DefineToolOptions<S, O>): ToolDefinition
}
