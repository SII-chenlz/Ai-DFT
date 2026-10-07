/** Regression: the linked package must import without development peer links. */
import { mkdtemp, copyFile, rm, readFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import assert from 'node:assert/strict'
const packageDirectory = process.argv[2]
if (!packageDirectory) throw new Error('Provide the extracted plugin directory')
const isolated = await mkdtemp(join(tmpdir(), 'aifs-isolated-import-'))
try {
  const artifact = join(isolated, 'index.mjs')
  await copyFile(join(packageDirectory, 'lib/index.js'), artifact)
  const plugin = await import(pathToFileURL(artifact))
  assert.equal(plugin.name, 'aifs')
  assert.equal(typeof plugin.apply, 'function')
  assert.equal(plugin.Config({ backendMode: 'managed' }).backendMode, 'managed')
  const manifest = JSON.parse(await readFile(join(packageDirectory, 'package.json'), 'utf8'))
  assert.equal(manifest.peerDependencies, undefined)
  assert.equal(manifest.dependencies, undefined)
  console.log('Isolated artifact import passed (no development dependencies)')
} finally {
  await rm(isolated, { recursive: true, force: true })
}
