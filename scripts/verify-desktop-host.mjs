/** Real Cordis, Skill and subprocess services; no UI or model credentials. */
import { createRequire } from 'node:module'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { cp, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { setTimeout as delay } from 'node:timers/promises'
import assert from 'node:assert/strict'

const root = fileURLToPath(new URL('../', import.meta.url))
const dsh = process.env.DEEPSEEK_HARNESS_DIR || join(root, '../deepseek-harness')
const stage = join(root, 'build/desktop-plugin/package')
const installedPackages = process.env.AIFS_DSH_PACKAGES
const hostManifest = JSON.parse(await readFile(installedPackages ? join(installedPackages, '../../package.json') : join(dsh, 'apps/desktop/package.json'), 'utf8'))
const packageManifest = JSON.parse(await readFile(join(stage, 'package.json'), 'utf8'))
const compatibility = packageManifest.aifs.compatibility
const verifiedVersions = installedPackages ? compatibility.desktopServicesTested : compatibility.sourceServicesTested
assert(verifiedVersions.includes(hostManifest.version), `DSH ${hostManifest.version} is outside the recorded service compatibility baseline; review and test this version before updating the baseline`)
const packagePath = (name, group, folder) => installedPackages ? join(installedPackages, name) : join(dsh, `packages/${group}/${folder}`)
const hostRequire = createRequire(join(packagePath('@deepseek-ai/dsh-subprocess-local', 'subprocess', 'subprocess-local'), 'package.json'))
const { Context, Service } = hostRequire('@deepseek-ai/cordis')
const plugin = await import(pathToFileURL(join(stage, 'lib/index.js')))
const { default: Prompt } = await import(pathToFileURL(join(packagePath('@deepseek-ai/dsh-system-prompt', 'core', 'system-prompt'), 'lib/index.js')))
const { default: Tools } = await import(pathToFileURL(join(packagePath('@deepseek-ai/dsh-tools', 'core', 'tools'), 'lib/index.js')))
const { default: Skills } = await import(pathToFileURL(join(packagePath('@deepseek-ai/dsh-skill', 'skill', 'skill'), 'lib/index.js')))
const { default: Subprocess } = await import(pathToFileURL(join(packagePath('@deepseek-ai/dsh-subprocess-local', 'subprocess', 'subprocess-local'), 'lib/index.js')))
const routes = new Map()
class TestConnection extends Service {
  constructor(ctx) {
    super(ctx, 'connection')
    this.fetch = { register: route => { routes.set(route.path, route); return async () => routes.delete(route.path) } }
  }
}
const dataDir = await mkdtemp(join(tmpdir(), 'AIFS real DSH host '))
const ctx = new Context()
let firstUrl
const status = async () => (await (await routes.get('/api/aifs/status').fetch(new Request('http://localhost/api/aifs/status'))).json())
async function untilReady() {
  const deadline = Date.now() + 30000
  while (Date.now() < deadline) {
    if (routes.has('/api/aifs/status')) {
      const current = await status()
      if (current.state === 'ready') return current
      if (current.state === 'failed' && !current.error.includes('Waiting')) throw new Error(current.error)
    }
    await delay(100)
  }
  throw new Error('Real Host plugin startup timed out')
}
try {
  await ctx.plugin(Prompt)
  await ctx.plugin(Tools)
  await ctx.plugin(Skills)
  await ctx.plugin(Subprocess)
  await ctx.plugin(TestConnection)
  const config = plugin.Config({ backendMode: 'managed', dataDir })
  const fiber = await ctx.plugin(plugin, config)
  // A model request made immediately on enable must see the full catalog,
  // even while the owned process has not finished starting.
  assert.equal(ctx.tools.schemas().length, 10)
  const earlyPrompt = await ctx.systemPrompt.assemble()
  assert.equal(earlyPrompt.tools.length, 10)
  const execution = { signal: new AbortController().signal }
  const earlyCapabilities = ctx.tools.get('get_rest_capabilities').execute({}, execution)
  const ready = await untilReady()
  assert.equal((await earlyCapabilities).ok, true)
  firstUrl = ready.baseUrl
  assert.equal(ctx.tools.schemas().length, 10)
  const assembled = await ctx.systemPrompt.assemble()
  assert.deepEqual(assembled.tools.map(tool => tool.name).sort(), ctx.tools.schemas().map(tool => tool.name).sort())
  assert(assembled.sections.some(section => section.name === 'aifs:guidance'))
  const capabilities = await ctx.tools.get('get_rest_capabilities').execute({ section: 'thermo' }, execution)
  assert.equal(capabilities.ok, true, JSON.stringify(capabilities))
  assert.equal(capabilities.keywords.pressure.unit, 'atm')
  assert(capabilities.methods.legacy.includes('SVWN'))
  assert(!capabilities.methods.legacy.includes('LDA'))
  const plan = await ctx.tools.get('create_aifs_plan').execute({ plan: {
    question: 'Verify bundled tool helper with H2', goal: 'other', tasks: [{
      task_id: 'h2', title: 'H2 energy', purpose: 'Get energy', kind: 'rest', job_type: 'energy', system_name: 'H2',
      inputs: { position: 'H 0 0 0\nH 0 0 0.74', position_source: 'user', position_unit: 'angstrom', charge: 0, charge_source: 'user', spin: 1, spin_source: 'user' },
      decision: { xc: 'PBE', source: 'user', rationale: 'Explicit user method' },
    }],
  } }, execution)
  assert.equal(plan.ok, true, JSON.stringify(plan))
  const card = await ctx.tools.get('generate_aifs_task_card').execute({ plan_id: plan.plan_id, task_id: 'h2' }, execution)
  assert.equal(card.ok, true, JSON.stringify(card))
  assert.equal(card.validation.valid, true)
  assert.equal(card.position_unit_status, 'explicit')
  assert.equal(card.position_unit, 'angstrom')
  assert.equal(await (await fetch(card.download_url)).text(), card.content)
  const advancedPlan = await ctx.tools.get('create_aifs_plan').execute({ plan: {
    question: 'Verify native frequency and thermal sections', goal: 'other', tasks: [{
      ...plan.plan.tasks[0], task_id: 'frequency',
      rest_options: { hessian: { frequencies: true }, thermo: { temperature: 298.15, pressure: 1.0 } },
    }],
  } }, execution)
  assert.equal(advancedPlan.ok, true, JSON.stringify(advancedPlan))
  const advancedCard = await ctx.tools.get('generate_aifs_task_card').execute({ plan_id: advancedPlan.plan_id, task_id: 'frequency' }, execution)
  assert.equal(advancedCard.ok, true, JSON.stringify(advancedCard))
  assert.equal(advancedCard.validation.valid, true)
  assert(advancedCard.content.includes('[hessian]'))
  assert(advancedCard.content.includes('[thermo]'))
  assert.equal(await (await fetch(advancedCard.download_url)).text(), advancedCard.content)
  const propertyCases = [
    { task_id: 'lda_frequency', job_type: 'energy',
      decision: { xc: 'SVWN', source: 'user', rationale: 'Explicit user method' },
      rest_options: { hessian: { frequencies: true } }, marker: 'xc = "SVWN"' },
    { task_id: 'open_shell_frequency', job_type: 'energy',
      inputs: { ...plan.plan.tasks[0].inputs, charge: 1, spin: 2 },
      decision: { xc: 'wB97X', source: 'user', rationale: 'Explicit user method' },
      rest_options: { ctrl: { analdrv_tasks: ['hessian'] }, thermo: { temperature: 298.15, pressure: 1.0 } },
      marker: 'analdrv_tasks = ["hessian"]' },
    { task_id: 'response', job_type: 'energy',
      rest_options: { tddft: { response_tddft: true, external_field_freq: 0.1 } },
      marker: 'response_tddft = true' },
    { task_id: 'multipoles', job_type: 'energy',
      rest_options: { ctrl: { analdrv_tasks: ['multipole'] }, analdrv: { multipole_orders: [1, 2], multipole_origin: [0, 0, 1] } },
      marker: '[analdrv]' },
    { task_id: 'rrs', job_type: 'energy',
      rest_options: { geom: { rrs_pbc: true, pbc_dim: 1, unit_cell_index: [0, 1], rrs_pbc_vec: [0, 0, 1.48], max_step: [0], k_points: [10] } },
      marker: 'rrs_pbc = true' },
  ]
  for (const { marker, ...value } of propertyCases) {
    const saved = await ctx.tools.get('create_aifs_plan').execute({ plan: {
      question: 'Verify reviewed property contract', goal: 'other',
      tasks: [{ ...plan.plan.tasks[0], ...value }],
    } }, execution)
    assert.equal(saved.ok, true, JSON.stringify(saved))
    assert.equal(saved.statuses[0].state, 'ready_for_card', JSON.stringify(saved.statuses))
    const result = await ctx.tools.get('generate_aifs_task_card').execute({ plan_id: saved.plan_id, task_id: value.task_id }, execution)
    assert.equal(result.ok, true, JSON.stringify(result))
    assert.equal(result.validation.valid, true)
    assert(result.content.includes(marker), result.content)
    assert.equal(await (await fetch(result.download_url)).text(), result.content)
  }
  const blockedGradient = await ctx.tools.get('create_aifs_plan').execute({ plan: {
    question: 'Reject unsupported RSH excited gradient without replacing the method', goal: 'other',
    tasks: [{ ...plan.plan.tasks[0], task_id: 'blocked_gradient', job_type: 'force',
      decision: { xc: 'wB97X', source: 'user', rationale: 'Explicit user method' },
      rest_options: { tddft: { tddft_grad_state: 1 } },
    }],
  } }, execution)
  assert.equal(blockedGradient.ok, true, JSON.stringify(blockedGradient))
  assert.equal(blockedGradient.statuses[0].state, 'needs_input')
  assert.equal((await ctx.tools.get('generate_aifs_task_card').execute({ plan_id: blockedGradient.plan_id, task_id: 'blocked_gradient' }, execution)).ok, false)
  const skills = await ctx.skills.list()
  assert(skills.some(skill => skill.name === 'aifs-molecular-planning'))
  const skill = await ctx.skills.get('aifs-molecular-planning')
  assert(skill.content.includes('create_aifs_plan'))
  const example = JSON.parse(/```json\n([\s\S]*?)\n```/.exec(skill.content)[1])
  const optimizedPlan = await ctx.tools.get('create_aifs_plan').execute({ plan: example }, execution)
  assert.equal(optimizedPlan.ok, true, JSON.stringify(optimizedPlan))
  assert.deepEqual(optimizedPlan.statuses.map(task => task.state), ['ready_for_card', 'needs_input'])
  const geometryCard = await ctx.tools.get('generate_aifs_task_card').execute({ plan_id: optimizedPlan.plan_id, task_id: 'opt_H2' }, execution)
  assert.equal(geometryCard.ok, true, JSON.stringify(geometryCard))
  assert(geometryCard.content.includes('xc = "PBE"'))
  const waitForResult = await ctx.tools.get('generate_aifs_task_card').execute({ plan_id: optimizedPlan.plan_id, task_id: 'sp_H2' }, execution)
  assert.equal(waitForResult.ok, false)
  example.tasks[1].inputs.position = 'H 0 0 0\nH 0 0 1.4'
  example.tasks[1].inputs.position_unit = 'bohr'
  const revision = await ctx.tools.get('revise_aifs_plan').execute({ plan_id: optimizedPlan.plan_id, expected_version: 1, change_reason: 'User provided optimized coordinates in Bohr', plan: example }, execution)
  assert.equal(revision.ok, true, JSON.stringify(revision))
  const optimizedCard = await ctx.tools.get('generate_aifs_task_card').execute({ plan_id: optimizedPlan.plan_id, task_id: 'sp_H2' }, execution)
  assert.equal(optimizedCard.position_unit, 'bohr')
  assert.equal(optimizedCard.validation.valid, true)
  assert(optimizedCard.content.includes('xc = "XYG7"'))
  assert.equal(await (await fetch(optimizedCard.download_url)).text(), optimizedCard.content)
  await fiber.dispose()
  assert.equal(ctx.tools.schemas().length, 0)
  assert.equal(routes.size, 0)
  await assert.rejects(fetch(`${firstUrl}/health`, { signal: AbortSignal.timeout(1000) }))
  const reloaded = await ctx.plugin(plugin, config)
  const next = await untilReady()
  assert.equal(ctx.tools.schemas().length, 10)
  const historical = await ctx.tools.get('get_aifs_card').execute({ plan_id: plan.plan_id, card_id: card.card_id }, execution)
  assert.equal(historical.ok, true, JSON.stringify(historical))
  assert.equal(await (await fetch(historical.download_url)).text(), card.content)
  await routes.get('/api/aifs/retry').fetch(new Request('http://localhost/api/aifs/retry', { method: 'POST' }))
  assert.equal((await status()).baseUrl, next.baseUrl)
  await reloaded.dispose()

  // A failed startup retains model-visible schemas and produces the actual
  // runtime error. An explicit retry recovers the same tool definitions.
  const delayedRuntime = join(dataDir, 'runtime available after retry')
  const failed = await ctx.plugin(plugin, plugin.Config({ ...config, runtimeRoot: delayedRuntime }))
  assert.equal(ctx.tools.schemas().length, 10)
  const failureDeadline = Date.now() + 5000
  while ((await status()).state !== 'failed' && Date.now() < failureDeadline) await delay(25)
  assert.equal((await status()).state, 'failed')
  await assert.rejects(ctx.tools.get('get_rest_capabilities').execute({}, execution), /AIFS 后端尚不可用.*ENOENT/)
  assert.equal((await ctx.systemPrompt.assemble()).tools.length, 10)
  await cp(join(stage, 'runtimes'), delayedRuntime, { recursive: true })
  await routes.get('/api/aifs/retry').fetch(new Request('http://localhost/api/aifs/retry', { method: 'POST' }))
  const recoveredStatus = await status()
  assert.equal(recoveredStatus.state, 'ready', JSON.stringify(recoveredStatus))
  assert.equal((await ctx.tools.get('get_rest_capabilities').execute({}, execution)).ok, true)
  const recovered = await ctx.tools.get('get_aifs_card').execute({ plan_id: plan.plan_id, card_id: card.card_id }, execution)
  assert.equal(await (await fetch(recovered.download_url)).text(), card.content)
  await failed.dispose()
  assert.equal(ctx.tools.schemas().length, 0)
  const report = { realDshServices: 'passed', hostKind: installedPackages ? 'installed-desktop' : 'source', dshVersion: hostManifest.version, aifsVersion: packageManifest.version, toolCount: 10, skill: skill.name,
    checks: ['compiled-host-plugin-no-peer-links', 'tool-schemas-before-ready', 'call-waits-for-owned-startup', 'schemas-retained-on-startup-failure', 'explicit-retry-recovers-same-tools', 'per-task-geometry-and-double-hybrid-energy-methods', 'model-prompt-tool-schemas', 'create-plan-tool', 'nested-plan-schema', 'rest-capability-query', 'frequency-thermo-task-card', 'explicit-lda-functional-card', 'open-shell-rsh-analdrv-card', 'response-tddft-card', 'multipole-card', 'rrs-pbc-card', 'block-unimplemented-rsh-excited-gradient', 'advanced-card-download', 'skill-example', 'explicit-angstrom-and-bohr', 'wait-for-optimized-result', 'revise-plan-tool', 'task-card-tool', 'download', 'card-after-reload', 'real-cordis', 'real-subprocess', 'real-skill-registry', 'enable', 'disable', 'reload', 'retry-while-ready', 'route-disposal', 'backend-exit'],
    desktopUi: 'not tested', recordedAt: new Date().toISOString() }
  await mkdir(join(root, '.local'), { recursive: true })
  await writeFile(join(root, installedPackages ? '.local/installed-desktop-host-verification.json' : '.local/desktop-host-verification.json'), JSON.stringify(report, null, 2) + '\n')
  console.log(JSON.stringify(report, null, 2))
} finally {
  await ctx.fiber.dispose()
  await rm(dataDir, { recursive: true, force: true })
}
