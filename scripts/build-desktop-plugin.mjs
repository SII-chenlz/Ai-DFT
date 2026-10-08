/** Assemble a native runtime into a platform-specific DSH debug archive. */
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { cp, mkdir, readFile, readdir, rm, writeFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { basename, dirname, join } from 'node:path'
import { checkRelease } from './release.mjs'
import { checkContracts } from './check-contracts.mjs'
const root = fileURLToPath(new URL('../', import.meta.url))
const args = process.argv.slice(2)
if (args.length && (args.length !== 2 || args[0] !== '--target')) throw new Error('Usage: node scripts/build-desktop-plugin.mjs [--target darwin-arm64|win32-x64]')
const target = args[1] || `${process.platform}-${process.arch}`
const archivePlatforms = { 'darwin-arm64': 'macos-arm64', 'win32-x64': 'windows-x64' }
const archivePlatform = archivePlatforms[target]
if (!archivePlatform) throw new Error(`Unsupported build target: ${target}`)
await checkRelease(root, { installed: true })
await checkContracts(root)
const source = join(root, 'dsh-plugin-aifs')
const require = createRequire(join(source, 'package.json'))
const esbuild = require('esbuild')
const manifest = JSON.parse(await readFile(join(source, 'package.json'), 'utf8'))
const runtime = join(root, 'build/desktop-runtimes', target)
const runtimeManifest = JSON.parse(await readFile(join(runtime, 'runtime.json'), 'utf8'))
if (runtimeManifest.target !== target || runtimeManifest.version !== manifest.version) throw new Error('Backend version/target mismatch')
const expectedExecutable = target === 'win32-x64' ? 'aifs-backend/aifs-backend.exe' : 'aifs-backend/aifs-backend'
if (runtimeManifest.executable !== expectedExecutable) throw new Error('Backend executable does not match target')
const stage = target === 'darwin-arm64' ? join(root, 'build/desktop-plugin/package') : join(root, 'build/desktop-plugin', target, 'package')
await rm(stage, { recursive: true, force: true })
await mkdir(join(stage, 'lib'), { recursive: true })
// Bundle schema/compiler helpers; plugin services are borrowed from ctx at runtime.
// The public dsh-tools root also exports services. Resolve its pure helper file
// at build time so no extra service registry or peer installation is shipped.
const toolPackage = dirname(require.resolve('@deepseek-ai/dsh-tools/package.json'))
const llmPackage = dirname(require.resolve('@deepseek-ai/dsh-llm/package.json'))
const sessionPackage = dirname(require.resolve('@deepseek-ai/dsh-session/package.json'))
await esbuild.build({
  entryPoints: [join(source, 'src/index.ts')], outfile: join(stage, 'lib/index.js'),
  bundle: true, platform: 'node', format: 'esm', target: 'node22',
  plugins: [{ name: 'bundle-tool-schema-helper', setup(build) {
    build.onResolve({ filter: /^@deepseek-ai\/dsh-tools$/ }, () => ({ path: join(toolPackage, 'lib/types/schema.js') }))
    build.onResolve({ filter: /^@deepseek-ai\/dsh-session$/ }, () => ({ path: join(sessionPackage, 'lib/types/json.js') }))
    build.onResolve({ filter: /^@deepseek-ai\/dsh-llm$/ }, () => ({ path: 'schema-errors', namespace: 'aifs-build-sdk' }))
    build.onLoad({ filter: /^schema-errors$/, namespace: 'aifs-build-sdk' }, () => ({
      contents: `export { HarnessError } from ${JSON.stringify(join(llmPackage, 'lib/types/error.js'))}; export { assertNever } from ${JSON.stringify(join(llmPackage, 'lib/types/never.js'))};`,
      loader: 'js', resolveDir: source,
    }))
  } }],
})
const client = await esbuild.build({ entryPoints: [join(source, 'src/desktop/ui.ts')], write: false, bundle: true, platform: 'browser', format: 'cjs', target: 'es2022', external: ['react'] })
await writeFile(join(stage, 'lib/client.js'), `window.__ModuleLoader__.load({id:${JSON.stringify(manifest.name)},factory:(require)=>{var module={exports:{}};var exports=module.exports;\n${client.outputFiles[0].text}\nreturn module.exports;}});\n`)
await cp(runtime, join(stage, 'runtimes', target), { recursive: true })
await cp(join(root, 'skills'), join(stage, 'assets/skills'), { recursive: true })
await cp(join(source, 'cordis.patch.yml'), join(stage, 'cordis.patch.yml'))
await cp(join(root, 'packaging/requirements-desktop.lock'), join(stage, 'build-requirements.lock'))
await cp(join(root, 'packaging/README.md'), join(stage, 'README.md'))
await cp(join(root, 'packaging/local-acceptance.md'), join(stage, 'local-acceptance.md'))
await cp(join(root, 'packaging/rest-coverage.md'), join(stage, 'rest-coverage.md'))
await cp(join(root, 'LICENSE'), join(stage, 'LICENSE'))
await cp(join(root, 'THIRD_PARTY_NOTICES.md'), join(stage, 'THIRD_PARTY_NOTICES.md'))
await mkdir(join(stage, 'licenses'), { recursive: true })
for (const name of ['dsh-tools', 'dsh-llm', 'dsh-session', 'schemastery', 'cordis']) {
  const directory = dirname(require.resolve(`@deepseek-ai/${name}/package.json`))
  await cp(join(directory, 'LICENSE'), join(stage, 'licenses', `${name}.txt`))
}
const sdkHelpers = Object.fromEntries(await Promise.all(['dsh-tools', 'dsh-llm', 'dsh-session', 'schemastery'].map(async (name) => [name, JSON.parse(await readFile(require.resolve(`@deepseek-ai/${name}/package.json`), 'utf8')).version])))
const dependencyLocks = Object.fromEntries(await Promise.all(['dsh-plugin-aifs/package-lock.json', 'packaging/requirements-desktop.lock'].map(async path => [path, createHash('sha256').update(await readFile(join(root, path))).digest('hex')])))
await writeFile(join(stage, 'build-info.json'), JSON.stringify({ version: manifest.version, node: process.version, esbuild: esbuild.version, sdkHelpers, dependencyLocks, compatibility: manifest.aifs.compatibility, runtime: { target: runtimeManifest.target, python: runtimeManifest.python }, channel: 'local-debug' }, null, 2) + '\n')
const { scripts: _scripts, devDependencies: _dev, peerDependencies: _peers, ...published } = manifest
published.main = './lib/index.js'
published.exports = { '.': './lib/index.js', './client': './lib/client.js', './package.json': './package.json' }
published.aifs = { ...manifest.aifs, channel: 'local-debug', targets: [target] }
await writeFile(join(stage, 'package.json'), JSON.stringify(published, null, 2) + '\n')
// A source-only symlink install must resolve without any parent node_modules.
execFileSync(process.execPath, [join(root, 'scripts/verify-desktop-import.mjs'), stage], { stdio: 'inherit' })
await mkdir(join(root, 'dist'), { recursive: true })
const archive = join(root, `dist/aifs-dsh-${manifest.version}-${archivePlatform}-local.tgz`)
execFileSync('tar', ['-czf', archive, '-C', join(stage, '..'), 'package'], {
  env: { ...process.env, COPYFILE_DISABLE: '1' },
})
const digest = createHash('sha256').update(await readFile(archive)).digest('hex')
await writeFile(`${archive}.sha256`, `${digest}  ${basename(archive)}\n`)
if (target === 'darwin-arm64' && process.env.AIFS_UPDATE_LOCAL_PACKAGE !== '0') {
  await cp(stage, join(root, 'dist/package'), { recursive: true, verbatimSymlinks: true })
} else {
  console.log(`Staged package: ${stage}; dist/package unchanged`)
}
// Prune older archives only after this build and its checksum are complete.
// Match this platform/channel exactly; leave other artifacts and newer versions.
// Keep the comparison baseline when preparing a test upgrade.
const currentParts = manifest.version.split('-')[0].split('.').map(Number)
let removed = 0
for (const entry of process.env.AIFS_PRUNE_OLD_PACKAGES === '0' ? [] : await readdir(join(root, 'dist'), { withFileTypes: true })) {
  if (!entry.isFile()) continue
  const match = /^aifs-dsh-(\d+\.\d+\.\d+(?:-[\da-zA-Z.-]+)?)-(macos-arm64|windows-x64)-local\.tgz(?:\.sha256)?$/.exec(entry.name)
  if (!match || match[2] !== archivePlatform || match[1] === manifest.version) continue
  const parts = match[1].split('-')[0].split('.').map(Number)
  const different = parts.findIndex((part, i) => part !== currentParts[i])
  const older = different >= 0 ? parts[different] < currentParts[different]
    : !manifest.version.includes('-') && match[1].includes('-')
  if (older) { await rm(join(root, 'dist', entry.name)); removed++ }
}
if (removed) console.log(`Removed ${removed} obsolete local archive/checksum files`)
console.log(`Local debug plugin: ${archive}\nSHA-256: ${digest}`)
