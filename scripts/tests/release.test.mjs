import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, mkdir, writeFile, readFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { synchronizeRelease, checkRelease } from '../release.mjs'

async function fixture(run) {
  const root = await mkdtemp(join(tmpdir(), 'AIFS release with spaces '))
  try {
    await mkdir(join(root, 'backend/src/aifs'), { recursive: true })
    await mkdir(join(root, 'dsh-plugin-aifs/src'), { recursive: true })
    await writeFile(join(root, 'backend/src/aifs/__init__.py'), '__version__ = "1.2.3"\n')
    await writeFile(join(root, 'dsh-plugin-aifs/package.json'), JSON.stringify({ name: 'aifs', version: '0.1.0', devDependencies: { esbuild: '0.28.2' } }))
    await writeFile(join(root, 'dsh-plugin-aifs/package-lock.json'), JSON.stringify({ name: 'aifs', version: '0.1.0', packages: { '': { name: 'aifs', version: '0.1.0', devDependencies: { esbuild: '0.28.2' } }, 'node_modules/esbuild': { version: '0.28.2' } } }))
    await run(root)
  } finally { await rm(root, { recursive: true, force: true }) }
}

test('synchronizing a release updates plugin, lock and runtime handshake version', () => fixture(async root => {
  await synchronizeRelease(root)
  const manifest = JSON.parse(await readFile(join(root, 'dsh-plugin-aifs/package.json'), 'utf8'))
  const lock = JSON.parse(await readFile(join(root, 'dsh-plugin-aifs/package-lock.json'), 'utf8'))
  assert.equal(manifest.version, '1.2.3')
  assert.equal(lock.version, '1.2.3')
  assert.equal(lock.packages[''].version, '1.2.3')
  assert.match(await readFile(join(root, 'dsh-plugin-aifs/src/version.ts'), 'utf8'), /SERVICE_VERSION = '1.2.3'/)
  await checkRelease(root)
}))

test('release check refuses stale versions without changing files', () => fixture(async root => {
  const path = join(root, 'dsh-plugin-aifs/package.json')
  const before = await readFile(path, 'utf8')
  await assert.rejects(checkRelease(root), /version/i)
  assert.equal(await readFile(path, 'utf8'), before)
}))

test('Windows checkout line endings pass without masking a stale runtime version', () => fixture(async root => {
  await synchronizeRelease(root)
  const path = join(root, 'dsh-plugin-aifs/src/version.ts')
  const crlf = (await readFile(path, 'utf8')).replace(/\n/g, '\r\n')
  await writeFile(path, crlf)
  assert.equal(await checkRelease(root), '1.2.3')
  assert.equal(await readFile(path, 'utf8'), crlf)
  await writeFile(path, crlf.replace("'1.2.3'", "'1.2.2'"))
  await assert.rejects(checkRelease(root), /Runtime version mismatch/)
}))

test('release check refuses a lock that resolves a different build dependency', () => fixture(async root => {
  await synchronizeRelease(root)
  const path = join(root, 'dsh-plugin-aifs/package-lock.json')
  const lock = JSON.parse(await readFile(path, 'utf8'))
  lock.packages['node_modules/esbuild'].version = '0.27.0'
  await writeFile(path, JSON.stringify(lock))
  await assert.rejects(checkRelease(root), /esbuild/)
}))

test('build check refuses installed dependencies that differ from the lock', () => fixture(async root => {
  await synchronizeRelease(root)
  const directory = join(root, 'dsh-plugin-aifs/node_modules/esbuild')
  await mkdir(directory, { recursive: true })
  await writeFile(join(directory, 'package.json'), JSON.stringify({ name: 'esbuild', version: '0.27.0' }))
  await assert.rejects(checkRelease(root, { installed: true }), /Installed build dependency mismatch: esbuild/)
}))
