import { useEffect, useState } from 'react'

import { TURNSTILE_SITE_KEY } from '../../lib/env'
import { getTurnstileToken } from '../../lib/turnstile'
import { createSession, hasSession } from './api'

export type SessionStatus = 'checking' | 'ready' | 'failed'

// One setup per page load, even if React mounts the hook twice (StrictMode in development).
let pending: Promise<void> | null = null

function ensureSession(): Promise<void> {
  pending ??= (async () => {
    if (!(await hasSession())) {
      const token = await getTurnstileToken(TURNSTILE_SITE_KEY, 'session')
      await createSession(token)
    }
  })().catch((error: unknown) => {
    pending = null // allow a retry on the next mount
    throw error
  })
  return pending
}

/** Ensure an anonymous session exists: reuse the cookie, otherwise pass Turnstile once. */
export function useAnonymousSession(): SessionStatus {
  const [status, setStatus] = useState<SessionStatus>('checking')

  useEffect(() => {
    let cancelled = false
    ensureSession()
      .then(() => {
        if (!cancelled) setStatus('ready')
      })
      .catch((error: unknown) => {
        console.warn('Session setup failed', error)
        if (!cancelled) setStatus('failed')
      })
    return () => {
      cancelled = true
    }
  }, [])

  return status
}
