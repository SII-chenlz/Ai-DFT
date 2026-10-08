/** Model-facing prose is separate from generated structure. Stale paths fail loudly. */
import type { ValueSchemaSpec } from '@deepseek-ai/dsh-tools'

export function withDescriptions<S extends ValueSchemaSpec>(schema: S, descriptions: Record<string, string>): S {
  const used = new Set<string>()
  function walk(value: ValueSchemaSpec, path: string): ValueSchemaSpec {
    const node = structuredClone(value)
    if (descriptions[path] !== undefined) { node.description = descriptions[path]; used.add(path) }
    if ('oneOf' in node) {
      const [first, second, ...rest] = node.oneOf
      node.oneOf = [walk(first, path), walk(second, path), ...rest.map(branch => walk(branch, path))]
    }
    else if (node.type === 'object' && node.properties) {
      node.properties = Object.fromEntries(Object.entries(node.properties).map(([key, child]) => {
        const decorated = walk(child, path ? `${path}.${key}` : key)
        return [key, { ...decorated, ...(child.required ? { required: true as const } : {}) }]
      }))
    } else if (node.type === 'array' && node.items) node.items = walk(node.items, `${path}[]`)
    return node
  }
  const result = walk(schema, '')
  for (const path of Object.keys(descriptions)) if (!used.has(path)) throw new Error(`Unknown schema description path: ${path}`)
  return result as S
}

export const PLAN_DESCRIPTIONS = {
  'tasks[].task_id': 'Stable unique ID, starting with a letter; letters, digits, underscore and hyphen only.',
  'tasks[].job_type': 'REST tasks require energy, opt, force or numerical dipole. Advanced tasks use explicit sections; query get_rest_capabilities.',
  'tasks[].rest_options': 'Extra REST tables keyed by section. Query get_rest_capabilities for types, units and limits. Cannot override core inputs/decisions. Frequency/TDDFT use energy; TS/IRC use opt.',
  'tasks[].analysis_formula': 'Required for analysis tasks. Preserve species, geometry labels, coefficients and correction sources; a saved formula is not a computed result.',
  'tasks[].inputs.position': 'Element x y z lines; leave null while waiting for actual optimized coordinates.',
  'tasks[].inputs.position_unit': 'Confirmed coordinate source unit. Never infer from magnitudes or inherit an initial unit for an optimization result.',
  'tasks[].inputs.position_from_task': 'For prior_result, use a directly dependent optimization task ID.',
  'tasks[].inputs.spin': 'Spin multiplicity 2S+1, minimum 1.',
  'tasks[].decision.basis': 'Confirmed orbital basis inside the configured pool. Null permits saving a draft but blocks task-card generation; choosing xc does not choose its default basis.',
  'tasks[].decision.xc_parser': 'Default legacy; use parse_xc only for methods on that path in get_rest_capabilities.',
  'tasks[].decision.supporting[].note': 'Specific supporting claim. Web requires URL/title and local requires record_id; keep source uncertainty.',
  'tasks[].decision.opposing[].note': 'Specific conflicting claim and scope; web requires URL/title and local requires record_id.',
}

export const REST_DESCRIPTIONS = {
  system_name: 'Short name of the molecular system.',
  position: 'Multi-line geometry, one Element x y z line per atom.',
  position_unit: 'Required confirmed coordinate unit, written to [geom] unit; no guessed default.',
  xc: 'Exact exchange-correlation method name; query get_rest_capabilities before selecting a variant.',
  xc_parser: 'Defaults to legacy; select parse_xc only when the capability contract requires it.',
  rest_options: 'Reviewed REST section settings; no raw TOML or core field overrides. Query capabilities for fields, units and combination limits.',
  basis: 'Required selected basis name inside the configured pool. Relative only; absolute paths and .. segments are rejected.',
  charge: 'Required confirmed net molecular charge; no guessed neutral default.',
  spin: 'Required confirmed multiplicity 2S+1, minimum 1; no guessed singlet default.',
  spin_polarization: 'Derived from spin when omitted or null.',
  outputs: 'Extra REST output items. The backend enforces the declared catalog.',
}
