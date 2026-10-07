/** Python-derived contract with model-facing guidance. */
import { PLAN_DRAFT_SCHEMA as generated } from './generated/backend.ts'
import { withDescriptions, PLAN_DESCRIPTIONS } from './schema-descriptions.ts'

export const PLAN_DRAFT_SCHEMA = withDescriptions(generated, PLAN_DESCRIPTIONS)
