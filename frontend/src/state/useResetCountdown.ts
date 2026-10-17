import { useEffect, useRef, useState } from 'react'

import { useGame } from './GameContext'

/**
 * Milliseconds until the next UTC reset, from the server's next_reset_at corrected by the
 * server clock offset. When it reaches zero it asks the server for the new state: the
 * countdown itself never decides that a new day has started.
 */
export function useResetCountdown(): number | null {
  const { state, refresh } = useGame()
  const [now, setNow] = useState(() => Date.now())
  const lastRefresh = useRef(0)

  useEffect(() => {
    const timer = setInterval(() => {
      setNow(Date.now())
    }, 1_000)
    return () => {
      clearInterval(timer)
    }
  }, [])

  const resetAt = state.game ? Date.parse(state.game.next_reset_at) : null
  const remaining = resetAt === null ? null : resetAt - (now + state.clockOffsetMs)

  useEffect(() => {
    // At (or just after) the reset, poll the server at most every 5 s until it moves on.
    if (remaining !== null && remaining <= 0 && now - lastRefresh.current > 5_000) {
      lastRefresh.current = now
      void refresh()
    }
  }, [remaining, now, refresh])

  return remaining === null ? null : Math.max(0, remaining)
}
