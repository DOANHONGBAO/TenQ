import { createContext, useContext } from 'react'

import type { ViewState } from './gameReducer'

export interface GameContextValue {
  state: ViewState
  ask: (question: string) => Promise<boolean>
  refresh: () => Promise<void>
  dismissNotice: () => void
  /** Local time corrected by the server offset, for display only. */
  serverNow: () => number
}

export const GameContext = createContext<GameContextValue | null>(null)

export function useGame(): GameContextValue {
  const value = useContext(GameContext)
  if (value === null) throw new Error('useGame must be used inside <GameProvider>')
  return value
}
