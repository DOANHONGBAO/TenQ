import type { Api } from '../../api/client'
import { TURNSTILE_SITE_KEY } from '../../lib/env'
import { getTurnstileToken } from '../../lib/turnstile'

export type TokenProvider = () => Promise<string>

export const turnstileTokenProvider: TokenProvider = () =>
  getTurnstileToken(TURNSTILE_SITE_KEY, 'session')

// One session setup at a time, even if several requests discover a missing session together.
let pending: Promise<void> | null = null

/** Pass Turnstile once and create the anonymous session cookie. */
export function startSession(client: Api, getToken: TokenProvider): Promise<void> {
  pending ??= (async () => {
    const token = await getToken()
    await client.createSession(token)
  })().finally(() => {
    pending = null
  })
  return pending
}
