/**
 * HTTP client for the AIFS FastAPI backend.
 *
 * Every request is a JSON POST with the caller's `AbortSignal` fused with a
 * configurable timeout; responses are byte-capped before parsing. Network
 * failures, timeouts, 5xx, and malformed responses throw
 * {@link AifsBackendError} (an infrastructure failure). A 422 carrying the
 * backend's domain error envelope is returned to the caller as a structured
 * domain failure instead — the caller decides whether that is a normal tool
 * result.
 */

export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue }

export interface AifsClientConfig {
  /** Base URL of the AIFS backend, e.g. `http://127.0.0.1:8000`. */
  readonly baseUrl: string
  /** Per-request timeout budget in milliseconds. */
  readonly requestTimeoutMs: number
  /** Maximum accepted response body size in bytes. */
  readonly maxResponseBytes: number
}

export const DEFAULT_BASE_URL = 'http://127.0.0.1:8000'
export const DEFAULT_REQUEST_TIMEOUT_MS = 30_000
export const DEFAULT_MAX_RESPONSE_BYTES = 1_048_576

/** Infrastructure failure talking to the AIFS backend (never a domain one). */
export class AifsBackendError extends Error {
  /** HTTP status of the failing response, when one was received. */
  readonly status?: number

  constructor(message: string, status?: number) {
    super(message)
    this.name = 'AifsBackendError'
    this.status = status
  }
}

/** The request exceeded `requestTimeoutMs` without a response. */
export class AifsBackendTimeoutError extends AifsBackendError {
  constructor(timeoutMs: number) {
    super(`AIFS backend request timed out after ${timeoutMs} ms`)
    this.name = 'AifsBackendTimeoutError'
  }
}

/** The response body exceeded `maxResponseBytes`. */
export class AifsBackendResponseTooLargeError extends AifsBackendError {
  constructor(maxBytes: number) {
    super(`AIFS backend response exceeded the ${maxBytes}-byte limit`)
    this.name = 'AifsBackendResponseTooLargeError'
  }
}

/** Structured request to POST /v1/rest-inputs (mirrors the backend model). */
export interface GenerateRestInputArgs {
  system_name: string
  position: string
  job_type: 'energy' | 'opt' | 'force' | 'numerical dipole'
  xc: string
  basis?: string
  charge?: number
  spin?: number
  spin_polarization?: boolean
  empirical_dispersion?: 'd3' | 'd3bj' | 'd4'
  print_level?: number
  num_threads?: number
  outputs?: string[]
}

/** Backend domain error envelope (`{"error": {"code", "message"}}`). */
export interface AifsDomainError {
  code: string
  message: string
}

export interface GenerateRestInputSuccess {
  ok: true
  rest_input: string
  effective_settings: Record<string, JsonValue>
  defaults_applied: string[]
  warnings: string[]
}

export type GenerateOutcome = GenerateRestInputSuccess | { ok: false; error: AifsDomainError }

export interface ValidationIssue {
  code: string
  message: string
  /** The backend serializes its optional fields as JSON `null`. */
  section?: string | null
  field?: string | null
  line?: number | null
}

export interface ValidateRestInputResult {
  valid: boolean
  errors: ValidationIssue[]
  warnings: ValidationIssue[]
  parsed_sections: string[]
}

/** A settled POST: either a 2xx body or a 422 domain error envelope. */
type PostResult =
  | { readonly kind: 'ok'; readonly status: number; readonly body: JsonValue }
  | { readonly kind: 'domain-error'; readonly code: string; readonly message: string }

/** Fuse a caller signal with a timeout so either one aborts the request. */
function fuseSignals(caller: AbortSignal, timeoutMs: number): {
  readonly signal: AbortSignal
  dispose(): void
} {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(new AifsBackendTimeoutError(timeoutMs)), timeoutMs)
  const onCallerAbort = (): void => controller.abort(caller.reason)
  caller.addEventListener('abort', onCallerAbort, { once: true })
  if (caller.aborted) onCallerAbort()
  return {
    signal: controller.signal,
    dispose: () => {
      clearTimeout(timer)
      caller.removeEventListener('abort', onCallerAbort)
    },
  }
}

/** Read a response body as text, failing when it exceeds `maxBytes`. */
async function readBodyWithLimit(response: Response, maxBytes: number): Promise<string> {
  if (response.body === null) return ''
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let total = 0
  let text = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    total += value.byteLength
    if (total > maxBytes) {
      reader.cancel().catch(() => {})
      throw new AifsBackendResponseTooLargeError(maxBytes)
    }
    text += decoder.decode(value, { stream: true })
  }
  return text + decoder.decode()
}

function readErrorEnvelope(body: JsonValue): AifsDomainError | undefined {
  if (typeof body !== 'object' || body === null || Array.isArray(body)) return undefined
  const error = body.error
  if (typeof error !== 'object' || error === null || Array.isArray(error)) return undefined
  const { code, message } = error
  if (typeof code === 'string' && typeof message === 'string') return { code, message }
  return undefined
}

function bodyMessage(body: JsonValue): string {
  const envelope = readErrorEnvelope(body)
  if (envelope !== undefined) return envelope.message
  if (typeof body === 'object' && body !== null && !Array.isArray(body)) {
    const message = body.message
    if (typeof message === 'string') return message
  }
  return 'no message in response body'
}

/** Reject a misconfigured client loudly, before any request is made. */
export function assertClientConfig(config: AifsClientConfig): void {
  if (!/^https?:\/\//.test(config.baseUrl)) {
    throw new Error(`aifs plugin: baseUrl must be an http(s) URL, got ${JSON.stringify(config.baseUrl)}`)
  }
  if (!Number.isFinite(config.requestTimeoutMs) || config.requestTimeoutMs <= 0) {
    throw new Error(`aifs plugin: requestTimeoutMs must be a positive number, got ${config.requestTimeoutMs}`)
  }
  if (!Number.isFinite(config.maxResponseBytes) || config.maxResponseBytes <= 0) {
    throw new Error(`aifs plugin: maxResponseBytes must be a positive number, got ${config.maxResponseBytes}`)
  }
}

export class AifsBackendClient {
  private readonly config: AifsClientConfig

  constructor(config: AifsClientConfig) {
    assertClientConfig(config)
    this.config = config
  }

  /**
   * Render a structured request via POST /v1/rest-inputs.
   *
   * A 422 domain envelope from the backend (e.g. dispersion requested for a
   * double-hybrid method) is a structured `ok: false` result; only
   * infrastructure failures throw.
   */
  async generate(request: GenerateRestInputArgs, signal: AbortSignal): Promise<GenerateOutcome> {
    const result = await this.post('/v1/rest-inputs', request, signal)
    if (result.kind === 'domain-error') {
      return { ok: false, error: { code: result.code, message: result.message } }
    }
    const body = result.body as Record<string, JsonValue>
    return {
      ok: true,
      rest_input: body.rest_input as string,
      effective_settings: body.effective_settings as Record<string, JsonValue>,
      defaults_applied: body.defaults_applied as string[],
      warnings: body.warnings as string[],
    }
  }

  /**
   * Validate a complete card via POST /v1/rest-inputs/validate.
   *
   * `valid: false` is a normal 200 domain result. Any non-200 response —
   * including a 422 domain envelope, which this endpoint never emits — is an
   * infrastructure failure and throws.
   */
  async validate(restInput: string, signal: AbortSignal): Promise<ValidateRestInputResult> {
    const result = await this.post('/v1/rest-inputs/validate', { rest_input: restInput }, signal)
    if (result.kind !== 'ok' || result.status !== 200) {
      throw new AifsBackendError(
        `AIFS backend returned an unexpected response for /v1/rest-inputs/validate`,
        result.kind === 'ok' ? result.status : undefined,
      )
    }
    return result.body as unknown as ValidateRestInputResult
  }

  private async post(path: string, requestBody: unknown, callerSignal: AbortSignal): Promise<PostResult> {
    const fused = fuseSignals(callerSignal, this.config.requestTimeoutMs)
    try {
      let response: Response
      try {
        response = await fetch(new URL(path, this.config.baseUrl), {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify(requestBody),
          signal: fused.signal,
        })
      } catch (error) {
        if (error instanceof AifsBackendError) throw error
        if (fused.signal.aborted) {
          const reason = fused.signal.reason
          throw reason instanceof Error ? reason : new AifsBackendError('request aborted')
        }
        throw new AifsBackendError(
          `AIFS backend request failed: ${error instanceof Error ? error.message : String(error)}`,
        )
      }
      const text = await readBodyWithLimit(response, this.config.maxResponseBytes)
      let body: JsonValue
      try {
        body = JSON.parse(text) as JsonValue
      } catch {
        throw new AifsBackendError(`AIFS backend returned invalid JSON (HTTP ${response.status})`, response.status)
      }
      if (response.ok) return { kind: 'ok', status: response.status, body }
      const envelope = readErrorEnvelope(body)
      if (response.status === 422 && envelope !== undefined && envelope.code !== 'request_validation_error') {
        return { kind: 'domain-error', code: envelope.code, message: envelope.message }
      }
      throw new AifsBackendError(
        `AIFS backend returned HTTP ${response.status}: ${bodyMessage(body)}`,
        response.status,
      )
    } finally {
      fused.dispose()
    }
  }
}
