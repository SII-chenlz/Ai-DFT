import { PassThrough } from 'node:stream'
import { mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, symlinkSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { BackendRuntime, packagedExecutable, SERVICE_VERSION } from '../src/desktop/runtime.ts'
import type { ProcessHandle, SubprocessService } from '../src/desktop/runtime.ts'
import { registerStatusRoutes } from '../src/desktop/routes.ts'
import { registerPlanningSkill } from '../src/desktop/skill.ts'

const cleanups: Array<() => void | Promise<void>> = []
afterEach(async () => { for (const cleanup of cleanups.splice(0).reverse()) await cleanup() })
it('accepts a canonical runtime-directory alias but rejects a file escaping that directory', () => {
  const root = mkdtempSync(join(tmpdir(), 'AIFS runtime alias '))
  cleanups.push(() => rmSync(root, { recursive: true, force: true }))
  const actual = join(root, 'actual', `${process.platform}-${process.arch}`)
  mkdirSync(actual, { recursive: true })
  const bytes = 'test executable'
  writeFileSync(join(actual, 'backend'), bytes)
  const digest = createHash('sha256').update(bytes).digest('hex')
  const manifest = { version: SERVICE_VERSION, target: `${process.platform}-${process.arch}`, executable: 'backend', files: [{ path: 'backend', sha256: digest }] }
  writeFileSync(join(actual, 'runtime.json'), JSON.stringify(manifest))
  symlinkSync(join(root, 'actual'), join(root, 'alias'), 'dir')
  expect(packagedExecutable(join(root, 'alias'))).toBe(realpathSync(join(actual, 'backend')))
  writeFileSync(join(root, 'outside'), bytes)
  symlinkSync(join(root, 'outside'), join(actual, 'escape'))
  manifest.files.push({ path: 'escape', sha256: digest })
  writeFileSync(join(actual, 'runtime.json'), JSON.stringify(manifest))
  expect(() => packagedExecutable(join(root, 'alias'))).toThrow('escapes package directory')
})
function fixture() {
  const dataDir = mkdtempSync(join(tmpdir(), 'AIFS path with spaces '))
  cleanups.push(() => rmSync(dataDir, { recursive: true, force: true }))
  const handles: Array<ProcessHandle & { finish(): void; announce(version?: string): void }> = []
  const service: SubprocessService = { spawn: vi.fn((spec) => {
    expect(spec.argv).toEqual(['/package path/backend', '--data-dir', dataDir, '--parent-stdin'])
    const output = new PassThrough()
    let finish!: () => void
    const done = new Promise<{ exitCode: number | null; signal: string | null }>((resolve) => { finish = () => resolve({ exitCode: 1, signal: null }) })
    const handle = { stdin: new PassThrough(), stdout: output, stderr: new PassThrough(), done,
      terminate: vi.fn(finish), waitForExit: async () => { await done; return true }, finish,
      announce(version = SERVICE_VERSION) { output.write(JSON.stringify({ event: 'ready', service: 'aifs-api', version, baseUrl: 'http://127.0.0.1:12345' }) + '\n') },
    }
    handles.push(handle)
    return handle
  }) }
  const health = vi.fn(async () => Response.json({ status: 'ok', service: 'aifs-api', version: SERVICE_VERSION }))
  const runtime = new BackendRuntime({ dataDir, runtimeRoot: '/unused', startupTimeoutMs: 100, shutdownTimeoutMs: 100 }, service, () => '/package path/backend', health)
  cleanups.push(() => runtime.dispose())
  return { runtime, handles, service, health }
}
describe('desktop backend ownership', () => {
  it('deduplicates activation, health-checks readiness and reports a crash before retry', async () => {
    const { runtime, handles, service, health } = fixture()
    const first = runtime.start()
    expect(runtime.start()).toBe(first)
    expect(runtime.snapshot().state).toBe('starting')
    handles[0]!.announce()
    await first
    expect(health).toHaveBeenCalledOnce()
    expect(runtime.snapshot().state).toBe('ready')
    await runtime.start()
    expect(service.spawn).toHaveBeenCalledOnce()
    handles[0]!.finish()
    await vi.waitFor(() => expect(runtime.snapshot().state).toBe('failed'))
    const retry = runtime.start()
    await vi.waitFor(() => expect(handles.length).toBe(2))
    handles[1]!.announce()
    await retry
    expect(runtime.snapshot().state).toBe('ready')
    await runtime.dispose()
    expect(handles[1]!.terminate).toHaveBeenCalled()
    expect(runtime.snapshot().baseUrl).toBeUndefined()
  })
  it('rejects mismatched service versions without connecting to health', async () => {
    const { runtime, handles, health } = fixture()
    const started = runtime.start()
    handles[0]!.announce('wrong')
    await started
    expect(runtime.snapshot().state).toBe('failed')
    expect(runtime.snapshot().error).toContain('mismatch')
    expect(health).not.toHaveBeenCalled()
    expect(handles[0]!.terminate).toHaveBeenCalled()
    expect(readFileSync(runtime.snapshot().logPath, 'utf8')).toContain('startup failed')
    expect(readFileSync(runtime.snapshot().logPath, 'utf8')).toContain('version/address mismatch')
  })
  it('waits for readiness, cancels a caller independently and exposes failure without auto-retry', async () => {
    const { runtime, handles, service } = fixture()
    const starting = runtime.start()
    const caller = new AbortController()
    const cancelled = runtime.baseUrl(caller.signal)
    const pending = runtime.baseUrl(new AbortController().signal)
    caller.abort(new Error('user cancelled'))
    await expect(cancelled).rejects.toThrow('user cancelled')
    handles[0]!.announce()
    await starting
    await expect(pending).resolves.toBe('http://127.0.0.1:12345')
    handles[0]!.finish()
    await vi.waitFor(() => expect(runtime.snapshot().state).toBe('failed'))
    await expect(runtime.baseUrl(new AbortController().signal)).rejects.toThrow('状态页重试')
    expect(service.spawn).toHaveBeenCalledOnce()
  })
  it('times out silent startup and never revives after disposal', async () => {
    const { runtime, handles } = fixture()
    await runtime.start()
    expect(runtime.snapshot().error).toContain('timed out')
    const retry = runtime.start()
    await vi.waitFor(() => expect(handles.length).toBe(2))
    await runtime.dispose()
    await retry
    await runtime.start()
    expect(handles.length).toBe(2)
    expect(runtime.snapshot().state).toBe('stopped')
  })
  it('refuses ready state if the health service version differs', async () => {
    const { runtime, handles, health } = fixture()
    health.mockResolvedValueOnce(Response.json({ status: 'ok', service: 'aifs-api', version: 'wrong' }))
    const started = runtime.start()
    handles[0]!.announce()
    await started
    expect(runtime.snapshot().state).toBe('failed')
    expect(runtime.snapshot().error).toContain('health/version')
  })
})
it('registers authenticated status/retry routes and disposes both', async () => {
  const { runtime } = fixture()
  const routes: Array<{ path: string; fetch(request: Request): Promise<Response> }> = []
  const dispose = vi.fn(async () => {})
  const retry = vi.fn(async () => {})
  const unregister = registerStatusRoutes({ fetch: { register: (route) => { routes.push(route); return dispose } } }, () => runtime.snapshot(), retry)
  expect((await (await routes[0]!.fetch(new Request('http://localhost/api/aifs/status'))).json()).state).toBe('stopped')
  await routes[1]!.fetch(new Request('http://localhost/api/aifs/retry', { method: 'POST' }))
  expect(retry).toHaveBeenCalledOnce()
  await unregister()
  expect(dispose).toHaveBeenCalledTimes(2)
})
it('registers a discoverable bundled planning skill, including its body and resource directory', async () => {
  const dispose = vi.fn()
  const unregister = registerPlanningSkill({ registerProvider: (create) => {
    const provider = create()
    cleanups.push(async () => {
      const candidates = await provider.list()
      expect(candidates[0]!.name).toBe('aifs-molecular-planning')
      const skill = await provider.get(candidates[0]!)
      expect(skill.content).toContain('create_aifs_plan')
      expect(skill.source).toBe('bundled')
      expect(skill.invocation.modelInvocable).toBe(true)
    })
    return dispose
  } }, fileURLToPath(new URL('../../skills/aifs-molecular-planning/SKILL.md', import.meta.url)))
  unregister()
  expect(dispose).toHaveBeenCalledOnce()
})
