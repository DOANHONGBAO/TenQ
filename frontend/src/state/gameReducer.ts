// Pure state transitions for the game screen. The server is the source of truth: every
// game state here was received from the API; the reducer never counts attempts itself.

import type { Answer, AttemptKind, GameState } from '../api/types'

export type Phase = 'booting' | 'ready' | 'maintenance' | 'error'

export interface Notice {
  tone: 'info' | 'warning' | 'error'
  message: string
}

export interface LastAnswer {
  number: number
  answer: Answer
  question: string
  kind: AttemptKind
}

export interface ViewState {
  phase: Phase
  game: GameState | null
  // server_time - local clock when the game was received; corrects the countdown only.
  clockOffsetMs: number
  submitting: boolean
  lastAnswer: LastAnswer | null
  notice: Notice | null
}

export type Action =
  | { type: 'game_loaded'; game: GameState; receivedAt: number }
  | { type: 'boot_failed'; phase: 'maintenance' | 'error'; message: string }
  | { type: 'submit_started' }
  | { type: 'submit_succeeded'; game: GameState; last: LastAnswer; receivedAt: number }
  | { type: 'submit_failed'; notice: Notice }
  | { type: 'notice'; notice: Notice | null }

export const initialState: ViewState = {
  phase: 'booting',
  game: null,
  clockOffsetMs: 0,
  submitting: false,
  lastAnswer: null,
  notice: null,
}

function offset(game: GameState, receivedAt: number): number {
  const server = Date.parse(game.server_time)
  return Number.isFinite(server) ? server - receivedAt : 0
}

export function gameReducer(state: ViewState, action: Action): ViewState {
  switch (action.type) {
    case 'game_loaded': {
      const newDay = state.game !== null && state.game.game_date !== action.game.game_date
      return {
        ...state,
        phase: 'ready',
        game: action.game,
        clockOffsetMs: offset(action.game, action.receivedAt),
        lastAnswer: newDay ? null : state.lastAnswer,
        notice: newDay ? { tone: 'info', message: 'A new daily challenge has started.' } : state.notice,
      }
    }
    case 'boot_failed':
      return { ...state, phase: action.phase, notice: { tone: 'error', message: action.message } }
    case 'submit_started':
      return { ...state, submitting: true, notice: null }
    case 'submit_succeeded':
      return {
        ...state,
        phase: 'ready',
        submitting: false,
        game: action.game,
        clockOffsetMs: offset(action.game, action.receivedAt),
        lastAnswer: action.last,
      }
    case 'submit_failed':
      return { ...state, submitting: false, notice: action.notice }
    case 'notice':
      return { ...state, notice: action.notice }
  }
}

export function isFinished(game: GameState | null): boolean {
  return game !== null && (game.status === 'won' || game.status === 'lost')
}
