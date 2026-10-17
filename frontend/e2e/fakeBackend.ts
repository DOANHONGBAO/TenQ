// A stateful fake of the TenQ API and of Cloudflare Turnstile, installed with page.route().
// It follows docs/api-contract.md closely enough to drive the real SPA end to end.

import type { Page, Route } from '@playwright/test'

type Answer = 'YES' | 'NO' | 'IRRELEVANT' | 'PENALTY' | 'WIN'

interface Entry {
  number: number
  question: string
  answer: Answer
  asked_at: string
  kind: 'question' | 'guess'
}

export interface FakeBackend {
  secret: string
  answers: Answer[]
  history: Entry[]
  sessionCreated: number
  down: boolean
  winners: { rank: number; display_name: string; questions: number; duration_ms: number }[]
}

const NOW = '2026-10-20T12:00:00.000Z'
const HINTS = ['Hint one: it lives in cold water.', 'Hint two: animal.', 'Hint three: tusks.', 'Hint four: W…']

const TURNSTILE_STUB = `
  window.turnstile = {
    render: function (el, opts) { window.__tsOpts = opts; return 'w1'; },
    execute: function () { setTimeout(function () { window.__tsOpts.callback('e2e-token-' + Date.now()); }, 10); },
    reset: function () { window.__tsResets = (window.__tsResets || 0) + 1; },
  };
`

export async function installFakeBackend(page: Page, overrides: Partial<FakeBackend> = {}) {
  const state: FakeBackend = {
    secret: 'walrus',
    answers: [],
    history: [],
    sessionCreated: 0,
    down: false,
    winners: [],
    ...overrides,
  }
  let hasSession = false

  const status = (): string => {
    if (state.history.some((h) => h.answer === 'WIN')) return 'won'
    if (state.history.length >= 10) return 'lost'
    return state.history.length ? 'in_progress' : 'not_started'
  }
  const game = () => {
    const used = state.history.length
    const st = status()
    const over = st === 'won' || st === 'lost'
    return {
      game_date: '2026-10-20',
      status: st,
      max_questions: 10,
      used,
      remaining: 10 - used,
      in_progress: false,
      history: state.history,
      started_at: used ? NOW : null,
      finished_at: over ? NOW : null,
      duration_ms: st === 'won' ? 95_000 : null,
      hints: HINTS.slice(0, Math.min(4, Math.floor(used / 2))),
      hints_total: 4,
      next_hint_in: over || used >= 8 ? null : 2 - (used % 2),
      server_time: NOW,
      next_reset_at: '2026-10-21T00:00:00.000Z',
    }
  }
  const json = (route: Route, code: number, body: unknown) =>
    route.fulfill({ status: code, contentType: 'application/json', body: JSON.stringify(body) })
  const error = (route: Route, code: number, errorCode: string) =>
    json(route, code, { error: { code: errorCode, message: errorCode, request_id: 'e2e' } })

  await page.route('https://challenges.cloudflare.com/turnstile/**', (route) =>
    route.fulfill({ status: 200, contentType: 'text/javascript', body: TURNSTILE_STUB }),
  )

  await page.route('**/api/v1/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname.replace('/api/v1', '')
    if (state.down) return error(route, 503, 'SERVICE_UNAVAILABLE')
    if (path === '/session' && request.method() === 'POST') {
      const body = request.postDataJSON() as { turnstile_token?: string }
      if (!body.turnstile_token) return error(route, 403, 'TURNSTILE_FAILED')
      hasSession = true
      state.sessionCreated += 1
      return json(route, 201, { display_name: 'Player-E2E001' })
    }
    if (path === '/leaderboard/today') {
      return json(route, 200, {
        game_date: '2026-10-20',
        entries: state.winners,
        me: null,
        total_winners: state.winners.length,
      })
    }
    if (path.startsWith('/puzzles/')) return error(route, 404, 'NOT_FOUND')
    if (!hasSession) return error(route, 401, 'SESSION_REQUIRED')
    if (path === '/game/today') return json(route, 200, game())

    const isGuess = path === '/game/today/guesses'
    if (path === '/game/today/questions' || isGuess) {
      if (status() === 'won') return error(route, 409, 'GAME_FINISHED')
      if (status() === 'lost') return error(route, 409, 'ATTEMPT_LIMIT_REACHED')
      const body = request.postDataJSON() as { question?: string; guess?: string }
      const text = (isGuess ? body.guess : body.question) ?? ''
      const answer: Answer = isGuess
        ? text.toLowerCase() === state.secret
          ? 'WIN'
          : 'NO'
        : (state.answers.shift() ?? 'NO')
      const number = state.history.length + 1
      state.history.push({ number, question: text, answer, asked_at: NOW, kind: isGuess ? 'guess' : 'question' })
      return json(route, 200, { number, answer, game: game() })
    }
    return error(route, 404, 'NOT_FOUND')
  })
  return state
}
