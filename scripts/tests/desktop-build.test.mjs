/** Verify Windows archive layout with a fixture runtime; no native execution claim. */
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { cp, mkdir, mkdtemp, readFile, rm, symlink, writeFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { releaseVersion } from '../release.mjs'

const source = fileURLToPath(new URL('../../', import.meta.url))

async function fixture(run) {
  const root = await mkdtemp(join(tmpdir(), 'AIFS Windows package with spaces '))
  try {
    for (const directory of ['backend/src/aifs', 'dsh-plugin-aifs', 'scripts', 'packaging', 'dist']) {
      await mkdir(join(root, directory), { recursive: true })
    }
    const paths = [
      'backend/src/aifs', 'contracts', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'dsh-plugin-aifs/package.json',
      'dsh-plugin-aifs/package-lock.json', 'dsh-plugin-aifs/cordis.patch.yml',
      'dsh-plugin-aifs/src', 'skills', 'scripts/build-desktop-plugin.mjs',
      'scripts/release.mjs', 'scripts/check-contracts.mjs', 'scripts/verify-desktop-import.mjs',
      'packaging/requirements-desktop.lock', 'packaging/README.md',
      'packaging/local-acceptance.md', 'packaging/rest-coverage.md',
    ]
    for (const path of paths) await cp(join(source, path), join(root, path), { recursive: true })
    await symlink(join(source, 'dsh-plugin-aifs/node_modules'), join(root, 'dsh-plugin-aifs/node_modules'), 'junction')
    const runtime = join(root, 'build/desktop-runtimes/win32-x64')
    await mkdir(join(runtime, 'aifs-backend'), { recursive: true })
    const content = Buffer.from('MZ fixture only; not an executable Windows backend')
    const executable = 'aifs-backend/aifs-backend.exe'
    await writeFile(join(runtime, executable), content)
    const version = await releaseVersion(source)
    await writeFile(join(runtime, 'runtime.json'), JSON.stringify({
      version, target: 'win32-x64', executable, python: '3.11.0',
      files: [{ path: executable, sha256: createHash('sha256').update(content).digest('hex') }],
    }))
    await run(root, version)
  } finally { await rm(root, { recursive: true, force: true }) }
}

test('Windows packaging uses .exe and preserves other-platform archives', () => fixture(async (root, version) => {
  const mac = 'aifs-dsh-0.0.1-macos-arm64-local.tgz'
  const oldWin = 'aifs-dsh-0.0.1-windows-x64-local.tgz'
  for (const name of [mac, oldWin]) {
    await writeFile(join(root, 'dist', name), 'older fixture')
    await writeFile(join(root, 'dist', `${name}.sha256`), 'older checksum fixture')
  }
  execFileSync(process.execPath, [join(root, 'scripts/build-desktop-plugin.mjs'), '--target', 'win32-x64'], {
    env: { ...process.env, AIFS_UPDATE_LOCAL_PACKAGE: '0' }, stdio: 'pipe',
  })
  const stage = join(root, 'build/desktop-plugin/win32-x64/package')
  const manifest = JSON.parse(await readFile(join(stage, 'package.json'), 'utf8'))
  assert.deepEqual(manifest.aifs.targets, ['win32-x64'])
  const runtime = JSON.parse(await readFile(join(stage, 'runtimes/win32-x64/runtime.json'), 'utf8'))
  assert.equal(runtime.executable, 'aifs-backend/aifs-backend.exe')
  assert.equal(await readFile(join(root, 'dist', mac), 'utf8'), 'older fixture')
  await assert.rejects(readFile(join(root, 'dist', oldWin)), { code: 'ENOENT' })
  await assert.rejects(readFile(join(root, 'dist', `${oldWin}.sha256`)), { code: 'ENOENT' })
  const name = `aifs-dsh-${version}-windows-x64-local.tgz`
  const archive = join(root, 'dist', name)
  const listing = execFileSync('tar', ['-tzf', archive], { encoding: 'utf8' })
  assert(listing.includes('package/runtimes/win32-x64/aifs-backend/aifs-backend.exe'))
  assert(!listing.includes('runtimes/darwin-arm64'))
  assert(listing.includes('package/assets/skills/aifs-molecular-planning/SKILL.md'))
  assert(listing.includes('package/LICENSE'))
  assert(listing.includes('package/THIRD_PARTY_NOTICES.md'))
  assert(listing.includes('package/licenses/dsh-tools.txt'))
  const digest = createHash('sha256').update(await readFile(archive)).digest('hex')
  assert.equal(await readFile(`${archive}.sha256`, 'utf8'), `${digest}  ${name}\n`)
}))

test('Windows package refuses a runtime for another platform before writing an archive', () => fixture(async root => {
  const path = join(root, 'build/desktop-runtimes/win32-x64/runtime.json')
  const runtime = JSON.parse(await readFile(path, 'utf8'))
  runtime.target = 'darwin-arm64'
  await writeFile(path, JSON.stringify(runtime))
  assert.throws(() => execFileSync(process.execPath, [join(root, 'scripts/build-desktop-plugin.mjs'), '--target', 'win32-x64'], { stdio: 'pipe' }), /Backend version\/target mismatch/)
}))
