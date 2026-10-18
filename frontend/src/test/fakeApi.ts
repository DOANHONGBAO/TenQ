// In-memory stand-in for the FastAPI backend, implementing the same Api interface.
// The server state lives here, so "refreshing the page" (re-rendering App) keeps it.

import { vi } from 'vitest'

import { ApiError } from '../api/client'
import type { Api } from '../api/client'
import type { Answer, AttemptKind, GameState, HistoryEntry, Leaderboard } from '../api/types'

export interface FakeServer {
  api: Api
  hasSession: boolean
  history: HistoryEntry[]
  status: GameState['status']
  gameDate: string
  serverTime: string
  nextReset: string
  nextAnswers: Answer[]
  /** Errors thrown by the next ask() calls, before or after charging. */
  askFailures: { error: ApiError; charge?: boolean }[]
  getGameFailures: ApiError[]
  askCalls: { question: string; key: string }[]
  /** Pending ask() resolvers when `holdAsks` is true. */
  holdAsks: boolean
  release: () => void
  leaderboard: Leaderboard
  playerName: string | null
  /** The secret word, used only to judge guesses. */
  secret: string
  hints: string[]
  game: () => GameState
}

export function httpError(status: number, code: string, details: Record<string, string> = {}) {
  return new ApiError('http', code, { status, code, details })
}

export function createFakeServer(overrides: Partial<FakeServer> = {}): FakeServer {
  const releases: (() => void)[] = []
  const seenKeys = new Map<string, { number: number; answer: Answer }>()

  const server: FakeServer = {
    hasSession: false,
    history: [],
    status: 'not_started',
    gameDate: '2026-10-20',
    serverTime: '2026-10-20T12:00:00.000Z',
    nextReset: '2026-10-21T00:00:00.000Z',
    nextAnswers: [],
    askFailures: [],
    getGameFailures: [],
    askCalls: [],
    holdAsks: false,
    release: () => {
      releases.splice(0).forEach((fn) => {
        fn()
      })
    },
    leaderboard: { game_date: '2026-10-20', entries: [], me: null, total_winners: 0 },
    playerName: null,
    secret: 'walrus',
    hints: ['Hint one: vague.', 'Hint two: a category.', 'Hint three: traits.', 'Hint four: obvious.'],
    game: () => {
      const used = server.history.length
      return {
        game_date: server.gameDate,
        status: server.status,
        max_questions: 10,
        used,
        remaining: 10 - used,
        in_progress: false,
        history: [...server.history],
        started_at: used ? server.serverTime : null,
        finished_at: server.status === 'won' || server.status === 'lost' ? server.serverTime : null,
        duration_ms: server.status === 'won' ? 125_000 : null,
        hints: server.hints.slice(0, Math.min(4, Math.floor(used / 2))),
        hints_total: 4,
        next_hint_in:
          server.status === 'won' || server.status === 'lost' || used >= 8 ? null : 2 - (used % 2),
        server_time: server.serverTime,
        next_reset_at: server.nextReset,
      }
    },
    api: undefined as unknown as Api,
    ...overrides,
  }

  const requireSession = () => {
    if (!server.hasSession) throw httpError(401, 'SESSION_REQUIRED')
  }

  const charge = (
    question: string,
    kind: AttemptKind = 'question',
    forced?: Answer,
  ): { number: number; answer: Answer } => {
    const answer = forced ?? server.nextAnswers.shift() ?? 'NO'
    const number = server.history.length + 1
    server.history.push({ number, question, answer, asked_at: server.serverTime, kind })
    if (answer === 'WIN') server.status = 'won'
    else if (number >= 10) server.status = 'lost'
    else server.status = 'in_progress'
    return { number, answer }
  }

  server.api = {
    createSession: vi.fn((token: string) => {
      if (!token) return Promise.reject(httpError(403, 'TURNSTILE_FAILED'))
      server.hasSession = true
      return Promise.resolve()
    }),
    getGame: vi.fn(() => {
      const failure = server.getGameFailures.shift()
      if (failure) return Promise.reject(failure)
      requireSession()
      return Promise.resolve(server.game())
    }),
    ask: vi.fn(async (question: string, key: string) => {
      server.askCalls.push({ question, key })
      requireSession()
      if (server.holdAsks) {
        await new Promise<void>((resolve) => releases.push(resolve))
      }
      const replay = seenKeys.get(key)
      if (replay) return { ...replay, game: server.game() }
      const failure = server.askFailures.shift()
      if (failure) {
        if (failure.charge) seenKeys.set(key, charge(question))
        throw failure.error
      }
      if (server.status === 'won') throw httpError(409, 'GAME_FINISHED')
      if (server.status === 'lost') throw httpError(409, 'ATTEMPT_LIMIT_REACHED')
      const result = charge(question)
      seenKeys.set(key, result)
      return { ...result, game: server.game() }
    }),
    guess: vi.fn((word: string, key: string) => {
      server.askCalls.push({ question: `guess:${word}`, key })
      requireSession()
      if (server.status === 'won') return Promise.reject(httpError(409, 'GAME_FINISHED'))
      if (!/^[a-z]+$/i.test(word)) return Promise.reject(httpError(422, 'INVALID_GUESS'))
      const correct = word.toLowerCase() === server.secret
      const result = charge(word, 'guess', correct ? 'WIN' : 'NO')
      return Promise.resolve({ ...result, game: server.game() })
    }),
    leaderboard: vi.fn(() => Promise.resolve(server.leaderboard)),
    setName: vi.fn((name: string) => {
      requireSession()
      if (server.status !== 'won') return Promise.reject(httpError(409, 'NOT_A_WINNER'))
      const clean = name.trim()
      if (clean.length < 2 || clean.length > 20) return Promise.reject(httpError(422, 'INVALID_NAME'))
      server.playerName = clean
      return Promise.resolve({ display_name: clean })
    }),
    answer: vi.fn(() => Promise.reject(httpError(404, 'NOT_FOUND'))),
  }
  return server
}
