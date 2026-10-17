import { HttpError, getJson, postJson } from '../../lib/http'

export interface SessionInfo {
  display_name: string
}

function isSessionInfo(value: unknown): value is SessionInfo {
  return (
    typeof value === 'object' &&
    value !== null &&
    'display_name' in value &&
    typeof value.display_name === 'string'
  )
}

/** True if the browser already holds a valid session cookie. */
export async function hasSession(): Promise<boolean> {
  try {
    await getJson('/game/today')
    return true
  } catch (error: unknown) {
    if (error instanceof HttpError && error.status === 401) {
      return false
    }
    throw error
  }
}

export async function createSession(turnstileToken: string): Promise<SessionInfo> {
  const body = await postJson('/session', { turnstile_token: turnstileToken })
  if (!isSessionInfo(body)) {
    throw new Error('Unexpected session response')
  }
  return body
}
