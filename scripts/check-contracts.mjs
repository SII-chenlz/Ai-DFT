/** Node-only stale-artifact gate. CI also regenerates from Python in check mode. */
import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { join, resolve } from 'node:path'

const defaultRoot = fileURLToPath(new URL('../', import.meta.url))
const digest = text => createHash('sha256').update(text.replace(/\r\n/g, '\n')).digest('hex')
export async function checkContracts(root = defaultRoot) {
  const contract = JSON.parse(await readFile(join(root, 'contracts/backend-schema.json'), 'utf8'))
  if (contract.contract_version !== 1 || !contract.source_hashes || !Object.keys(contract.source_hashes).length) throw new Error('Unsupported AIFS contract manifest')
  for (const [path, expected] of Object.entries(contract.source_hashes)) {
    if (digest(await readFile(join(root, path), 'utf8')) !== expected) {
      throw new Error(`Contract out of date: ${path}; run python -m aifs.contracts --write`)
    }
  }
  if (digest(await readFile(join(root, 'dsh-plugin-aifs/src/generated/backend.ts'), 'utf8')) !== contract.generated_ts_sha256) {
    throw new Error('Generated contract out of date: run python -m aifs.contracts --write')
  }
}
if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  await checkContracts()
  console.log('AIFS generated contracts checked')
}
