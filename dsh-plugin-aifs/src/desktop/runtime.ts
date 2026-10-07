/** Owned backend lifecycle. Never reconnect to an unowned service. */
import { createHash } from 'node:crypto'
import { appendFileSync, mkdirSync, readFileSync, realpathSync, renameSync, statSync, existsSync } from 'node:fs'
import { homedir } from 'node:os'
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path'
import type { Readable, Writable } from 'node:stream'

import { SERVICE_VERSION } from '../version.ts'
export { SERVICE_VERSION } from '../version.ts'
export interface ProcessHandle {
  stdin: Writable | undefined
  stdout: Readable | undefined
  stderr: Readable | undefined
  done: Promise<{ exitCode: number | null; signal: string | null }>
  terminate(): void
  waitForExit(signal?: AbortSignal): Promise<boolean>
}
export interface SubprocessService {
  spawn(spec: { argv: readonly string[]; cwd: string; stdio: { stdin: 'pipe'; stdout: 'pipe'; stderr: 'pipe' }; graceMs: number; signal: AbortSignal }): ProcessHandle
}
export interface RuntimeConfig {
  runtimeRoot: string
  dataDir: string
  startupTimeoutMs: number
  shutdownTimeoutMs: number
}
export interface RuntimeStatus {
  state: 'stopped' | 'starting' | 'ready' | 'failed' | 'external'
  version: string
  dataDir: string
  logPath: string
  baseUrl?: string
  error?: string
}

export function dataDirectory(configured: string): string {
  const home = process.env.DSH_HOME?.trim() || join(homedir(), '.dsh')
  const expand = (path: string) => path === '~' ? homedir() : path.startsWith('~/') ? join(homedir(), path.slice(2)) : path
  return resolve(expand(configured || join(expand(home), 'aifs')))
}

/** Validate every runtime file against the package manifest before execution. */
export function packagedExecutable(root: string): string {
  const target = `${process.platform}-${process.arch}`
  // macOS /var and /tmp are aliases of /private/...; compare canonical
  // paths on both sides while still rejecting file links outside this runtime.
  const directory = realpathSync(resolve(root, target))
  const manifest: unknown = JSON.parse(readFileSync(join(directory, 'runtime.json'), 'utf8'))
  if (!manifest || typeof manifest !== 'object' || !('version' in manifest) || manifest.version !== SERVICE_VERSION || !('target' in manifest) || manifest.target !== target || !('executable' in manifest) || typeof manifest.executable !== 'string' || !('files' in manifest) || !Array.isArray(manifest.files) || !manifest.files.length) {
    throw new Error(`Backend runtime version/target mismatch (${target}, expected ${SERVICE_VERSION})`)
  }
  const safePath = (name: string) => {
    if (isAbsolute(name)) throw new Error('Runtime manifest contains an absolute path')
    const path = resolve(directory, name)
    const rel = relative(directory, realpathSync(path))
    if (rel === '..' || rel.startsWith(`..${sep}`) || isAbsolute(rel)) throw new Error('Runtime file escapes package directory')
    return path
  }
  let executableListed = false
  for (const entry of manifest.files) {
    if (!entry || typeof entry !== 'object' || typeof entry.path !== 'string' || typeof entry.sha256 !== 'string') throw new Error('Invalid runtime file manifest')
    const digest = createHash('sha256').update(readFileSync(safePath(entry.path))).digest('hex')
    if (digest !== entry.sha256) throw new Error(`Runtime checksum mismatch: ${entry.path}`)
    if (entry.path === manifest.executable) executableListed = true
  }
  if (!executableListed) throw new Error('Runtime executable has no checksum')
  return safePath(manifest.executable)
}

export class BackendRuntime {
  private status: RuntimeStatus
  private handle?: ProcessHandle
  private attempt?: Promise<void>
  private disposed = false
  private abort?: AbortController
  private listeners = new Set<(status: RuntimeStatus) => void>()
  constructor(private config: RuntimeConfig, private service: SubprocessService, private executable = () => packagedExecutable(config.runtimeRoot), private health = fetch) {
    const dataDir = dataDirectory(config.dataDir)
    this.status = { state: 'stopped', version: SERVICE_VERSION, dataDir, logPath: join(dataDir, 'logs', 'launcher.log') }
  }
  snapshot(): RuntimeStatus { return { ...this.status } }
  /** Wait for the current startup only; failed calls never launch another process. */
  async baseUrl(signal: AbortSignal): Promise<string> {
    if (signal.aborted) throw signal.reason
    if (this.status.state === 'starting') {
      await new Promise<void>((resolve, reject) => {
        let unsubscribe = () => {}
        const cleanup = () => { unsubscribe(); signal.removeEventListener('abort', onAbort) }
        const onAbort = () => { cleanup(); reject(signal.reason) }
        signal.addEventListener('abort', onAbort, { once: true })
        unsubscribe = this.subscribe(state => {
          if (state.state !== 'starting') { cleanup(); resolve() }
        })
      })
    }
    if (signal.aborted) throw signal.reason
    if (this.status.state === 'ready' && this.status.baseUrl) return this.status.baseUrl
    throw new Error(`AIFS 后端尚不可用：${this.status.error || this.status.state}。请在 AIFS 状态页重试；若刚升级，请完全退出并重开 DSH。日志：${this.status.logPath}`)
  }
  subscribe(listener: (status: RuntimeStatus) => void): () => void {
    this.listeners.add(listener)
    listener(this.snapshot())
    return () => { this.listeners.delete(listener) }
  }
  private publish(status: RuntimeStatus): void {
    this.status = status
    for (const listener of this.listeners) listener(this.snapshot())
  }
  private log(message: string | Buffer): void {
    if (existsSync(this.status.logPath) && statSync(this.status.logPath).size > 2_000_000) {
      renameSync(this.status.logPath, `${this.status.logPath}.1`)
    }
    appendFileSync(this.status.logPath, message)
  }
  start(): Promise<void> {
    if (this.disposed || this.status.state === 'ready') return Promise.resolve()
    if (this.attempt) return this.attempt
    this.attempt = this.launch().finally(() => { this.attempt = undefined })
    return this.attempt
  }
  private async launch(): Promise<void> {
    this.publish({ ...this.status, state: 'starting', error: undefined, baseUrl: undefined })
    try {
      mkdirSync(dirname(this.status.logPath), { recursive: true })
      if (this.handle) await this.stopHandle()
      if (this.disposed) return
      const executable = this.executable()
      this.log(`${new Date().toISOString()} Starting AIFS ${SERVICE_VERSION}\n`)
      const abort = this.abort = new AbortController()
      const handle = this.handle = this.service.spawn({
        argv: [executable, '--data-dir', this.status.dataDir, '--parent-stdin'], cwd: this.status.dataDir,
        stdio: { stdin: 'pipe', stdout: 'pipe', stderr: 'pipe' }, graceMs: 2000, signal: abort.signal,
      })
      handle.stderr?.on('data', (chunk: Buffer) => {
        try { this.log(chunk) } catch (error) {
          abort.abort(error)
        }
      })
      const ready = await this.readReady(handle, abort)
      if (this.disposed || abort.signal.aborted) throw new Error('Backend startup cancelled')
      const response = await this.health(`${ready.baseUrl}/health`, { signal: AbortSignal.any([abort.signal, AbortSignal.timeout(this.config.startupTimeoutMs)]) })
      const body: unknown = await response.json()
      if (!response.ok || !body || typeof body !== 'object' || !('status' in body) || body.status !== 'ok' || !('service' in body) || body.service !== 'aifs-api' || !('version' in body) || body.version !== SERVICE_VERSION) throw new Error('Backend health/version check failed')
      if (this.disposed || abort.signal.aborted) throw new Error('Backend startup cancelled')
      this.publish({ ...this.status, state: 'ready', baseUrl: ready.baseUrl })
      void handle.done.then((outcome) => {
        if (!this.disposed && this.handle === handle && !abort.signal.aborted) this.publish({ ...this.status, state: 'failed', baseUrl: undefined, error: `Backend exited (${outcome.exitCode ?? outcome.signal})` })
      }, (error: unknown) => {
        if (!this.disposed && this.handle === handle && !abort.signal.aborted) this.publish({ ...this.status, state: 'failed', baseUrl: undefined, error: String(error) })
      })
    } catch (error) {
      try { await this.stopHandle() } catch (cleanupError) { error = new Error(`${String(error)}; cleanup: ${String(cleanupError)}`) }
      if (!this.disposed) {
        try { this.log(`${new Date().toISOString()} AIFS ${SERVICE_VERSION} startup failed: ${String(error)}\n`) } catch { /* Status still reports failures when the log path cannot be written. */ }
        this.publish({ ...this.status, state: 'failed', baseUrl: undefined, error: String(error) })
      }
    }
  }
  private readReady(handle: ProcessHandle, abort: AbortController): Promise<{ baseUrl: string }> {
    return new Promise((accept, reject) => {
      let buffer = ''
      const finish = (error?: Error, baseUrl?: string) => {
        clearTimeout(timer)
        handle.stdout?.off('data', onData)
        abort.signal.removeEventListener('abort', onAbort)
        if (error) reject(error)
        else accept({ baseUrl: baseUrl! })
      }
      const onAbort = () => finish(new Error('Backend startup cancelled'))
      const onData = (chunk: Buffer) => {
        buffer += chunk.toString('utf8')
        if (buffer.length > 8192) return finish(new Error('Invalid backend startup output'))
        const end = buffer.indexOf('\n')
        if (end < 0) return
        try {
          const record: unknown = JSON.parse(buffer.slice(0, end))
          if (!record || typeof record !== 'object' || !('event' in record) || record.event !== 'ready' || !('service' in record) || record.service !== 'aifs-api' || !('version' in record) || record.version !== SERVICE_VERSION || !('baseUrl' in record) || typeof record.baseUrl !== 'string' || !/^http:\/\/127\.0\.0\.1:[1-9]\d{0,4}$/.test(record.baseUrl) || Number(new URL(record.baseUrl).port) > 65535) throw new Error('Backend ready record version/address mismatch')
          finish(undefined, record.baseUrl)
        } catch (error) { finish(new Error(String(error))) }
      }
      const timer = setTimeout(() => finish(new Error('Backend startup timed out')), this.config.startupTimeoutMs)
      handle.stdout?.on('data', onData)
      abort.signal.addEventListener('abort', onAbort, { once: true })
      void handle.done.then(() => finish(new Error('Backend exited before ready')), (error: unknown) => finish(new Error(String(error))))
    })
  }
  private async stopHandle(): Promise<void> {
    const handle = this.handle
    if (!handle) return
    this.abort?.abort()
    handle.stdin?.end()
    handle.terminate()
    const exited = await handle.waitForExit(AbortSignal.timeout(this.config.shutdownTimeoutMs))
    if (!exited) throw new Error('Backend process cleanup timed out; refusing a second process')
    this.handle = undefined
  }
  async dispose(): Promise<void> {
    this.disposed = true
    this.abort?.abort()
    await this.attempt
    await this.stopHandle()
    this.publish({ ...this.status, state: 'stopped', baseUrl: undefined })
    this.listeners.clear()
  }
}
