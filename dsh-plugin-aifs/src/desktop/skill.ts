/** Register the bundled planning instructions through the DSH Skill service. */
import { readFileSync } from 'node:fs'
import { dirname } from 'node:path'
export interface PlanningCandidate {
  name: string; description: string; invocation: { modelInvocable: boolean; userInvocable: boolean }
  provider: string; source: 'bundled'; rank: number
  resourceBase: { kind: 'directory'; path: string }; locator: string
}
export interface SkillService {
  registerProvider(create: () => { name: string; list: () => Promise<PlanningCandidate[]>; get: (candidate: PlanningCandidate) => Promise<Omit<PlanningCandidate, 'rank' | 'locator'> & { content: string }> }): () => void
}
export function registerPlanningSkill(service: SkillService, path: string): () => void {
  const raw = readFileSync(path, 'utf8')
  const match = /^---\r?\nname: ([^\r\n]+)\r?\ndescription: ([^\r\n]+)\r?\n---\r?\n([\s\S]*)$/.exec(raw)
  if (!match) throw new Error('Invalid bundled AIFS Skill metadata')
  const candidate: PlanningCandidate = {
    name: match[1]!, description: match[2]!, invocation: { modelInvocable: true, userInvocable: true },
    provider: 'aifs', source: 'bundled', rank: 600, resourceBase: { kind: 'directory', path: dirname(path) }, locator: path,
  }
  return service.registerProvider(() => ({
    name: 'aifs', list: async () => [candidate],
    get: async () => { const { rank: _rank, locator: _locator, ...summary } = candidate; return { ...summary, content: match[3]! } },
  }))
}
