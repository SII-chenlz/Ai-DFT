/** Routes run behind DSH's existing authenticated /api admission. */
import type { RuntimeStatus } from './runtime.ts'
export interface ConnectionService {
  fetch: { register(route: { path: string; methods: string[]; requestBody: 'buffered'; fetch(request: Request): Promise<Response> }): () => Promise<void> }
}
export function registerStatusRoutes(connection: ConnectionService, status: () => RuntimeStatus, retry: () => Promise<void>): () => Promise<void> {
  const unregister = [
    connection.fetch.register({ path: '/api/aifs/status', methods: ['GET'], requestBody: 'buffered', fetch: async () => Response.json(status()) }),
    connection.fetch.register({ path: '/api/aifs/retry', methods: ['POST'], requestBody: 'buffered', fetch: async () => { await retry(); return Response.json(status()) } }),
  ]
  return async () => { for (const dispose of unregister.reverse()) await dispose() }
}
