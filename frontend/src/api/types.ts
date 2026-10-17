// Shared API types (docs/api-contract.md sections 3 and 4) and runtime guards.
// Responses are validated at the boundary instead of trusted.

export type Answer = 'YES' | 'NO' | 'IRRELEVANT' | 'PENALTY' | 'WIN'
export type GameStatus = 'not_started' | 'in_progress' | 'won' | 'lost'
export type AttemptKind = 'question' | 'guess'

export interface HistoryEntry {
  number: number
  question: string
  answer: Answer
  asked_at: string
  kind: AttemptKind
}

export interface GameState {
  game_date: string
  status: GameStatus
  max_questions: number
  used: number
  remaining: number
  in_progress: boolean
  history: HistoryEntry[]
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
  hints: string[]
  hints_total: number
  next_hint_in: number | null
  server_time: string
  next_reset_at: string
}

export interface AskResult {
  number: number
  answer: Answer
  game: GameState
}

export interface LeaderboardEntry {
  rank: number
  display_name: string
  questions: number
  duration_ms: number
}

export interface Leaderboard {
  game_date: string
  entries: LeaderboardEntry[]
  me: { rank: number; questions: number; duration_ms: number } | null
  total_winners: number
}

export interface PuzzleAnswer {
  game_date: string
  word: string
}

const ANSWERS: readonly string[] = ['YES', 'NO', 'IRRELEVANT', 'PENALTY', 'WIN']
const STATUSES: readonly string[] = ['not_started', 'in_progress', 'won', 'lost']

type Obj = Record<string, unknown>

function isObj(value: unknown): value is Obj {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
const isStr = (v: unknown): v is string => typeof v === 'string'
const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
const isStrOrNull = (v: unknown): v is string | null => v === null || isStr(v)

export function isAnswer(value: unknown): value is Answer {
  return isStr(value) && ANSWERS.includes(value)
}

function isHistoryEntry(v: unknown): v is HistoryEntry {
  return (
    isObj(v) &&
    isNum(v.number) &&
    isStr(v.question) &&
    isAnswer(v.answer) &&
    isStr(v.asked_at) &&
    (v.kind === 'question' || v.kind === 'guess')
  )
}

export function isGameState(v: unknown): v is GameState {
  return (
    isObj(v) &&
    isStr(v.game_date) &&
    isStr(v.status) &&
    STATUSES.includes(v.status) &&
    isNum(v.max_questions) &&
    isNum(v.used) &&
    isNum(v.remaining) &&
    typeof v.in_progress === 'boolean' &&
    Array.isArray(v.history) &&
    v.history.every(isHistoryEntry) &&
    isStrOrNull(v.started_at) &&
    isStrOrNull(v.finished_at) &&
    (v.duration_ms === null || isNum(v.duration_ms)) &&
    Array.isArray(v.hints) &&
    v.hints.every(isStr) &&
    isNum(v.hints_total) &&
    (v.next_hint_in === null || isNum(v.next_hint_in)) &&
    isStr(v.server_time) &&
    isStr(v.next_reset_at)
  )
}

export function isAskResult(v: unknown): v is AskResult {
  return isObj(v) && isNum(v.number) && isAnswer(v.answer) && isGameState(v.game)
}

function isLeaderboardEntry(v: unknown): v is LeaderboardEntry {
  return (
    isObj(v) && isNum(v.rank) && isStr(v.display_name) && isNum(v.questions) && isNum(v.duration_ms)
  )
}

export function isLeaderboard(v: unknown): v is Leaderboard {
  if (!isObj(v) || !isStr(v.game_date) || !Array.isArray(v.entries) || !isNum(v.total_winners)) {
    return false
  }
  const me = v.me
  const meOk =
    me === null || (isObj(me) && isNum(me.rank) && isNum(me.questions) && isNum(me.duration_ms))
  return meOk && v.entries.every(isLeaderboardEntry)
}

export function isPuzzleAnswer(v: unknown): v is PuzzleAnswer {
  return isObj(v) && isStr(v.game_date) && isStr(v.word)
}
