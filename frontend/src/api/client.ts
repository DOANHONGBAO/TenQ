// The only module that talks to FastAPI. Every call has a timeout, sends the session cookie,
// parses the error envelope, and validates the response shape.

import { API_BASE_URL } from '../lib/env'
import {
  type AskResult,
  type GameState,
  type Leaderboard,
  type PuzzleAnswer,
  isAskResult,
  isGameState,
  isLeaderboard,
  isPuzzleAnswer,
} from './types'

const DEFAULT_TIMEOUT_MS = 10_000
// The AI judge may take up to ~20 s server-side; give it a little more.
export const ASK_TIMEOUT_MS = 25_000

export type ApiErrorKind = 'http' | 'network' | 'timeout' | 'invalid'

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly status: number
  readonly code: string
  readonly retryAfterS: number | null
  readonly details: Record<string, string>

  constructor(
    kind: ApiErrorKind,
    message: string,
    opts: { status?: number; code?: string; retryAfterS?: number | null; details?: Record<string, string> } = {},
  ) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = opts.status ?? 0
    this.code = opts.code ?? kind.toUpperCase()
    this.retryAfterS = opts.retryAfterS ?? null
    this.details = opts.details ?? {}
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST'
  body?: unknown
  headers?: Record<string, string>
  timeoutMs?: number
}

async function request(path: string, opts: RequestOptions = {}): Promise<unknown> {
  const controller = new AbortController()
  const timer = setTimeout(() => {
    controller.abort()
  }, opts.timeoutMs ?? DEFAULT_TIMEOUT_MS)
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: opts.method ?? 'GET',
      credentials: 'include',
      headers: {
        Accept: 'application/json',
        ...(opts.body === undefined ? {} : { 'Content-Type': 'application/json' }),
        ...opts.headers,
      },
      ...(opts.body === undefined ? {} : { body: JSON.stringify(opts.body) }),
      signal: controller.signal,
    })
  } catch (error: unknown) {
    if (controller.signal.aborted) {
      throw new ApiError('timeout', 'The server took too long to answer.')
    }
    throw new ApiError('network', error instanceof Error ? error.message : 'Network error')
  } finally {
    clearTimeout(timer)
  }

  const payload: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const envelope =
      typeof payload === 'object' && payload !== null && 'error' in payload ? payload.error : null
    const err = (typeof envelope === 'object' && envelope !== null ? envelope : {}) as Record<
      string,
      unknown
    >
    const retry = Number(response.headers.get('Retry-After'))
    const details = typeof err.details === 'object' && err.details !== null ? err.details : {}
    throw new ApiError('http', typeof err.message === 'string' ? err.message : 'Request failed', {
      status: response.status,
      code: typeof err.code === 'string' ? err.code : `HTTP_${String(response.status)}`,
      retryAfterS: Number.isFinite(retry) && retry > 0 ? retry : null,
      details: details as Record<string, string>,
    })
  }
  return payload
}

function expect<T>(value: unknown, guard: (v: unknown) => v is T): T {
  if (!guard(value)) {
    throw new ApiError('invalid', 'Unexpected response from the server.')
  }
  return value
}

export const api = {
  async health(): Promise<boolean> {
    const body = await request('/health', { timeoutMs: 5_000 })
    return typeof body === 'object' && body !== null && 'status' in body && body.status === 'ok'
  },
  async createSession(turnstileToken: string): Promise<void> {
    await request('/session', { method: 'POST', body: { turnstile_token: turnstileToken } })
  },
  async getGame(): Promise<GameState> {
    return expect(await request('/game/today'), isGameState)
  },
  async ask(question: string, idempotencyKey: string): Promise<AskResult> {
    const body = await request('/game/today/questions', {
      method: 'POST',
      body: { question },
      headers: { 'Idempotency-Key': idempotencyKey },
      timeoutMs: ASK_TIMEOUT_MS,
    })
    return expect(body, isAskResult)
  },
  async leaderboard(limit = 20): Promise<Leaderboard> {
    return expect(await request(`/leaderboard/today?limit=${String(limit)}`), isLeaderboard)
  },
  async answer(gameDate: string): Promise<PuzzleAnswer> {
    return expect(await request(`/puzzles/${gameDate}/answer`), isPuzzleAnswer)
  },
}

export type Api = typeof api
