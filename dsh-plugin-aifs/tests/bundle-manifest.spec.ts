import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const packagePath = join(process.cwd(), 'package.json')
const patchPath = join(process.cwd(), 'cordis.patch.yml')

describe('Harness bundle manifest', () => {
  it('declares a profile patch that inserts the AIFS plugin', () => {
    const manifest = JSON.parse(readFileSync(packagePath, 'utf8')) as {
      dsh?: { bundle?: { patch?: string } }
    }
    expect(manifest.dsh?.bundle?.patch).toBe('./cordis.patch.yml')

    const patch = readFileSync(patchPath, 'utf8')
    expect(patch).toContain("id: aifs")
    expect(patch).toContain("name: '@aifs/dsh-plugin-aifs'")
  })
})
