/**
 * HTTP tests for the backend client: request shape, status mapping (domain
 * failure vs infrastructure failure), timeouts, caller aborts and the
 * response-size cap. All network access is mocked.
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  AifsBackendClient,
  AifsBackendError,
  AifsBackendResponseTooLargeError,
  AifsBackendTimeoutError,
  type GenerateRestInputArgs,
  type EvidenceSearchArgs,
} from '../src/client.ts'

const CONFIG = {
  baseUrl: 'http://127.0.0.1:8000',
  requestTimeoutMs: 5_000,
  maxResponseBytes: 1_000_000,
}

const ARGS: GenerateRestInputArgs = {
  system_name: 'water',
  position: 'O 0 0 0',
  job_type: 'energy',
  xc: 'B3LYP',
}

const CARD = '[ctrl]\nxc = "PBE"\n'
const EVIDENCE_ARGS: EvidenceSearchArgs = {
  system_description: 'open-shell nickel cluster',
  calculation_goal: 'spin-state ordering',
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

/** A fetch that stays pending until the request signal aborts. */
function abortPendingFetch(): typeof fetch {
  return vi.fn((_url: unknown, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
    init?.signal?.addEventListener('abort', () => reject(init?.signal?.reason))
  }))
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('AifsBackendClient.generate', () => {
  it('POSTs structured JSON to /v1/rest-inputs and wraps the 200 result', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({
      rest_input: '[ctrl]',
      effective_settings: { xc: 'B3LYP' },
      defaults_applied: ['basis=def2-TZVPP'],
      warnings: [],
    }))
    vi.stubGlobal('fetch', fetchMock)
    const client = new AifsBackendClient(CONFIG)
    const outcome = await client.generate(ARGS, new AbortController().signal)
    expect(outcome).toEqual({
      ok: true,
      rest_input: '[ctrl]',
      effective_settings: { xc: 'B3LYP' },
      defaults_applied: ['basis=def2-TZVPP'],
      warnings: [],
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as unknown as [URL, RequestInit]
    expect(url.toString()).toBe('http://127.0.0.1:8000/v1/rest-inputs')
    expect(init.method).toBe('POST')
    expect((init.headers as Record<string, string>)['content-type']).toBe('application/json')
    expect(JSON.parse(init.body as string)).toEqual(ARGS)
  })

  it('returns a structured ok=false result for a 422 domain envelope', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({
      error: { code: 'empirical_dispersion_not_needed', message: 'omit empirical_dispersion' },
    }, 422)))
    const outcome = await new AifsBackendClient(CONFIG).generate(ARGS, new AbortController().signal)
    expect(outcome).toEqual({
      ok: false,
      error: { code: 'empirical_dispersion_not_needed', message: 'omit empirical_dispersion' },
    })
  })

  it('throws for a 422 request_validation_error (plugin/backend schema mismatch)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({
      error: { code: 'request_validation_error', detail: [] },
    }, 422)))
    await expect(new AifsBackendClient(CONFIG).generate(ARGS, new AbortController().signal))
      .rejects.toThrow(AifsBackendError)
  })

  it('throws on a 500 with the backend message', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({
      error: { code: 'internal', message: 'boom' },
    }, 500)))
    await expect(new AifsBackendClient(CONFIG).generate(ARGS, new AbortController().signal))
      .rejects.toThrow(/HTTP 500: boom/)
  })

  it('throws when a 200 response body is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('not json', { status: 200 })))
    await expect(new AifsBackendClient(CONFIG).generate(ARGS, new AbortController().signal))
      .rejects.toThrow(/invalid JSON/)
  })

  it('throws on a network failure', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new Error('ECONNREFUSED')
    }))
    await expect(new AifsBackendClient(CONFIG).generate(ARGS, new AbortController().signal))
      .rejects.toThrow(/request failed/)
  })
})

describe('AifsBackendClient.validate', () => {
  it('POSTs the card to /v1/rest-inputs/validate and returns the 200 result', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({
      valid: false,
      errors: [{ code: 'out_of_range', message: 'spin must be >= 1', section: 'ctrl', field: 'spin', line: null }],
      warnings: [],
      parsed_sections: ['ctrl', 'geom'],
    }))
    vi.stubGlobal('fetch', fetchMock)
    const client = new AifsBackendClient(CONFIG)
    const result = await client.validate(CARD, new AbortController().signal)
    expect(result.valid).toBe(false)
    expect(result.errors[0]?.code).toBe('out_of_range')
    const [url] = fetchMock.mock.calls[0] as unknown as [URL]
    expect(url.toString()).toBe('http://127.0.0.1:8000/v1/rest-inputs/validate')
  })

  it('throws on a 422 domain envelope (this endpoint only returns 200 domain results)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({
      error: { code: 'something', message: 'unexpected' },
    }, 422)))
    await expect(new AifsBackendClient(CONFIG).validate(CARD, new AbortController().signal))
      .rejects.toThrow(/unexpected response/)
  })
})

describe('AifsBackendClient.searchEvidence', () => {
  it('POSTs the natural-language query and returns source-linked hits', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({
      retrieval_mode: 'lexical_fallback',
      query: 'open-shell nickel cluster spin-state ordering',
      hits: [{
        record_id: 'MREC-1', doi: '10.1/example', title: 'Cluster', system: 'Ni cluster',
        calculation: 'spin state', benchmark: null, functional: 'PBE0', protocol: 'def2-TZVP',
        experience_type: 'evaluation', summary: 'comparison', score: 0.5,
        evidence: [{ quote: 'PBE0 comparison', page: 3, section: 'Results', evidence_type: 'text' }],
      }],
    }))
    vi.stubGlobal('fetch', fetchMock)
    const result = await new AifsBackendClient(CONFIG).searchEvidence(EVIDENCE_ARGS, new AbortController().signal)
    expect(result.retrieval_mode).toBe('lexical_fallback')
    expect(result.hits[0]?.doi).toBe('10.1/example')
    const [url, init] = fetchMock.mock.calls[0] as unknown as [URL, RequestInit]
    expect(url.toString()).toBe('http://127.0.0.1:8000/v1/evidence/search')
    expect(JSON.parse(init.body as string)).toEqual(EVIDENCE_ARGS)
  })

  it('throws on backend schema failure', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ error: { code: 'request_validation_error', detail: [] } }, 422)))
    await expect(new AifsBackendClient(CONFIG).searchEvidence(EVIDENCE_ARGS, new AbortController().signal))
      .rejects.toThrow(AifsBackendError)
  })
})

describe('timeouts, aborts and size caps', () => {
  it('uses the current owned address after a port change and never falls back after failure', async () => {
    const resolver = vi.fn().mockResolvedValueOnce('http://127.0.0.1:49101')
      .mockResolvedValueOnce('http://127.0.0.1:49102').mockRejectedValueOnce(new Error('owned startup failed'))
    const fetchMock = vi.fn(async (_url: URL) => jsonResponse({ methods: {} }))
    vi.stubGlobal('fetch', fetchMock)
    const client = new AifsBackendClient(CONFIG, resolver)
    for (let i = 0; i < 2; i++) await client.workflow('GET', '/v1/rest-capabilities', undefined, new AbortController().signal)
    expect(fetchMock.mock.calls.map(call => String(call[0]))).toEqual([
      'http://127.0.0.1:49101/v1/rest-capabilities', 'http://127.0.0.1:49102/v1/rest-capabilities',
    ])
    await expect(client.workflow('GET', '/v1/rest-capabilities', undefined, new AbortController().signal))
      .rejects.toThrow('owned startup failed')
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('includes owned-server readiness waiting in the request timeout', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const client = new AifsBackendClient({ ...CONFIG, requestTimeoutMs: 20 }, signal => new Promise((_resolve, reject) => {
      signal.addEventListener('abort', () => reject(signal.reason), { once: true })
    }))
    await expect(client.workflow('GET', '/v1/rest-capabilities', undefined, new AbortController().signal))
      .rejects.toThrow(AifsBackendTimeoutError)
    expect(fetchMock).not.toHaveBeenCalled()
  })
  it('aborts after requestTimeoutMs and throws the timeout error', async () => {
    vi.stubGlobal('fetch', abortPendingFetch())
    const client = new AifsBackendClient({ ...CONFIG, requestTimeoutMs: 30 })
    await expect(client.generate(ARGS, new AbortController().signal))
      .rejects.toThrow(AifsBackendTimeoutError)
  })

  it('propagates a caller abort with the caller reason', async () => {
    vi.stubGlobal('fetch', abortPendingFetch())
    const controller = new AbortController()
    const client = new AifsBackendClient(CONFIG)
    const pending = client.generate(ARGS, controller.signal)
    controller.abort(new Error('caller aborted'))
    await expect(pending).rejects.toThrow('caller aborted')
  })

  it('throws when the response exceeds maxResponseBytes', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ rest_input: 'x'.repeat(200) }))))
    const client = new AifsBackendClient({ ...CONFIG, maxResponseBytes: 100 })
    await expect(client.generate(ARGS, new AbortController().signal))
      .rejects.toThrow(AifsBackendResponseTooLargeError)
  })
})
