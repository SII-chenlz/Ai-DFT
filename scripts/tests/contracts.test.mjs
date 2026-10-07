import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, mkdir, readFile, writeFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { checkContracts } from '../check-contracts.mjs'

const source = new URL('../../', import.meta.url)
test('contract gate rejects source and generated drift without rewriting either', async () => {
  const root = await mkdtemp(join(tmpdir(), 'AIFS contract drift '))
  try {
    const artifact = JSON.parse(await readFile(new URL('contracts/backend-schema.json', source), 'utf8'))
    for (const path of [...Object.keys(artifact.source_hashes), 'contracts/backend-schema.json', 'dsh-plugin-aifs/src/generated/backend.ts']) {
      const destination = join(root, path)
      await mkdir(join(destination, '..'), { recursive: true })
      await writeFile(destination, await readFile(new URL(path, source)))
    }
    await checkContracts(root)
    const path = join(root, 'backend/src/aifs/workflow_models.py')
    const original = await readFile(path, 'utf8')
    await writeFile(path, original + '\n# changed model\n')
    await assert.rejects(checkContracts(root), /out of date/)
    assert.equal(await readFile(path, 'utf8'), original + '\n# changed model\n')
    await writeFile(path, original)
    const generated = join(root, 'dsh-plugin-aifs/src/generated/backend.ts')
    await writeFile(generated, (await readFile(generated, 'utf8')).replace('"reaction_energy"', '"invented_goal"'))
    await assert.rejects(checkContracts(root), /out of date/)
  } finally { await rm(root, { recursive: true, force: true }) }
})
