import { useCallback, useEffect, useState } from 'react'

import type { Api } from '../api/client'
import type { Leaderboard } from '../api/types'

export interface LeaderboardView {
  board: Leaderboard | null
  failed: boolean
  reload: () => void
}

/** Today's leaderboard; reloads when the trigger changes (new day, a win) and every minute. */
export function useLeaderboard(client: Api, trigger: string): LeaderboardView {
  const [board, setBoard] = useState<Leaderboard | null>(null)
  const [failed, setFailed] = useState(false)

  const reload = useCallback(() => {
    client
      .leaderboard(10)
      .then((next) => {
        setBoard(next)
        setFailed(false)
      })
      .catch(() => {
        setFailed(true)
      })
  }, [client])

  useEffect(() => {
    reload()
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') reload()
    }, 60_000)
    return () => {
      clearInterval(timer)
    }
  }, [reload, trigger])

  return { board, failed, reload }
}
