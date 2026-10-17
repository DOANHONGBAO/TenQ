// Owns the game screen state and every effect that talks to the API.
// Components read state via useGame() and call the actions it exposes.

import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react'
import type { ReactNode } from 'react'

import { ApiError } from '../api/client'
import type { Api } from '../api/client'
import type { AttemptKind, GameState } from '../api/types'
import { startSession } from '../features/session/session'
import type { TokenProvider } from '../features/session/session'
import { loadPending, savePending } from '../lib/storage'
import { describeAskError } from './errorMessages'
import { gameReducer, initialState, isFinished } from './gameReducer'
import { GameContext } from './GameContext'
import type { GameContextValue } from './GameContext'


interface Props {
  client: Api
  getToken: TokenProvider
  children: ReactNode
}

function isSessionMissing(error: unknown): boolean {
  return error instanceof ApiError && error.code === 'SESSION_REQUIRED'
}

function isMaintenance(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (error.kind === 'network' || error.kind === 'timeout' || error.status === 503 || error.status === 502)
  )
}

export function GameProvider({ client, getToken, children }: Props) {
  const [state, dispatch] = useReducer(gameReducer, initialState)
  // Latest state for async callbacks (updated after each render, never read during render).
  const stateRef = useRef(state)
  useEffect(() => {
    stateRef.current = state
  }, [state])
  // Synchronous guard: a double click must not send two questions before React re-renders.
  const inFlight = useRef(false)

  /** Run a call; if the session is missing (first visit, cleared cookie), create one and retry once. */
  const withSession = useCallback(
    async <T,>(call: () => Promise<T>): Promise<T> => {
      try {
        return await call()
      } catch (error: unknown) {
        if (!isSessionMissing(error)) throw error
        await startSession(client, getToken)
        return call()
      }
    },
    [client, getToken],
  )

  const loadGame = useCallback(async (): Promise<GameState | null> => {
    try {
      const game = await withSession(() => client.getGame())
      dispatch({ type: 'game_loaded', game, receivedAt: Date.now() })
      return game
    } catch (error: unknown) {
      if (stateRef.current.game === null) {
        dispatch({
          type: 'boot_failed',
          phase: isMaintenance(error) ? 'maintenance' : 'error',
          message: isMaintenance(error)
            ? 'TenQ is temporarily unavailable. We will keep trying.'
            : 'We could not start your game. Please reload the page.',
        })
      }
      return null
    }
  }, [client, withSession])

  const refresh = useCallback(async () => {
    await loadGame()
  }, [loadGame])

  const submit = useCallback(
    async (kind: AttemptKind, raw: string): Promise<boolean> => {
      const current = stateRef.current
      const question = raw.trim()
      if (inFlight.current || current.game === null || isFinished(current.game) || !question) {
        return false
      }
      inFlight.current = true
      const stored = loadPending()
      const key =
        stored !== null &&
        stored.kind === kind &&
        stored.question === question &&
        stored.gameDate === current.game.game_date
          ? stored.idempotencyKey
          : crypto.randomUUID()
      savePending({ gameDate: current.game.game_date, kind, question, idempotencyKey: key })
      dispatch({ type: 'submit_started' })
      try {
        const result = await withSession(() =>
          kind === 'guess' ? client.guess(question, key) : client.ask(question, key),
        )
        savePending(null)
        dispatch({
          type: 'submit_succeeded',
          game: result.game,
          last: { number: result.number, answer: result.answer, question, kind },
          receivedAt: Date.now(),
        })
        return true
      } catch (error: unknown) {
        const outcome = describeAskError(error)
        if (!outcome.keepPending) savePending(null)
        dispatch({ type: 'submit_failed', notice: { tone: outcome.tone, message: outcome.message } })
        // Never guess the attempt count locally: re-read it from the server.
        await loadGame()
        return false
      } finally {
        inFlight.current = false
      }
    },
    [client, loadGame, withSession],
  )
  const ask = useCallback((question: string) => submit('question', question), [submit])
  const guess = useCallback((word: string) => submit('guess', word), [submit])

  // Boot, then keep trying while in maintenance.
  useEffect(() => {
    void loadGame()
  }, [loadGame])
  useEffect(() => {
    if (state.phase !== 'maintenance') return
    const timer = setInterval(() => {
      void loadGame()
    }, 15_000)
    return () => {
      clearInterval(timer)
    }
  }, [state.phase, loadGame])

  // Coming back to the tab: show the latest state without a manual refresh.
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === 'visible') void loadGame()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [loadGame])

  const value = useMemo<GameContextValue>(
    () => ({
      state,
      ask,
      guess,
      refresh,
      dismissNotice: () => {
        dispatch({ type: 'notice', notice: null })
      },
      serverNow: () => Date.now() + stateRef.current.clockOffsetMs,
    }),
    [state, ask, guess, refresh],
  )
  return <GameContext.Provider value={value}>{children}</GameContext.Provider>
}
