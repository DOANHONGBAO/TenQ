import { useEffect, useState } from 'react'

import { fetchHealth } from './api'

export type BackendStatus = 'checking' | 'online' | 'offline'

export function useBackendHealth(): BackendStatus {
  const [status, setStatus] = useState<BackendStatus>('checking')

  useEffect(() => {
    const controller = new AbortController()
    fetchHealth(controller.signal)
      .then(() => {
        setStatus('online')
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          console.warn('Backend health check failed', error)
          setStatus('offline')
        }
      })
    return () => {
      controller.abort()
    }
  }, [])

  return status
}
