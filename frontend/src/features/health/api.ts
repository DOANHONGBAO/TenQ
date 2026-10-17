import { getJson } from '../../lib/http'

export interface Health {
  status: 'ok'
}

function isHealth(value: unknown): value is Health {
  return typeof value === 'object' && value !== null && 'status' in value && value.status === 'ok'
}

/** Fetch the backend liveness probe and validate its shape instead of trusting it. */
export async function fetchHealth(signal?: AbortSignal): Promise<Health> {
  const body = await getJson('/health', signal)
  if (!isHealth(body)) {
    throw new Error('Unexpected health response')
  }
  return body
}
