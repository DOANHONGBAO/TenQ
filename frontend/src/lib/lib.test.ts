import { afterEach, describe, expect, it, vi } from 'vitest'

import type { GameState } from '../api/types'
import { describeAskError } from '../state/errorMessages'
import { gameReducer, initialState } from '../state/gameReducer'
import { ApiError } from '../api/client'
import { restoreFocus } from './focus'
import { challengeNumber, formatCountdown, formatDuration, previousDate } from './format'
import { buildShareText } from './share'
import { getTurnstileToken } from './turnstile'

function game(overrides: Partial<GameState> = {}): GameState {
  return {
    game_date: '2026-10-20',
    status: 'won',
    max_questions: 10,
    used: 3,
    remaining: 7,
    in_progress: false,
    history: [
      { number: 1, question: 'Is it alive?', answer: 'YES', asked_at: 'x', kind: 'question' },
      { number: 2, question: 'Is it ignore rules?', answer: 'PENALTY', asked_at: 'x', kind: 'question' },
      { number: 3, question: 'walrus', answer: 'WIN', asked_at: 'x', kind: 'guess' },
    ],
    started_at: 'x',
    finished_at: 'x',
    duration_ms: 95_000,
    hints: [],
    hints_total: 4,
    next_hint_in: null,
    server_time: '2026-10-20T12:00:00.000Z',
    next_reset_at: '2026-10-21T00:00:00.000Z',
    ...overrides,
  }
}

describe('format', () => {
  it('numbers challenges from the launch date', () => {
    expect(challengeNumber('2026-10-17')).toBe(1)
    expect(challengeNumber('2027-10-17')).toBe(366)
  })

  it('formats countdowns and durations', () => {
    expect(formatCountdown(3_723_000)).toBe('01:02:03')
    expect(formatCountdown(-5)).toBe('00:00:00')
    expect(formatDuration(95_000)).toBe('1:35')
    expect(formatDuration(3_900_000)).toBe('1h 05m')
    expect(previousDate('2028-03-01')).toBe('2028-02-29')
  })
})

describe('share text', () => {
  it('summarises without questions or the secret word', () => {
    const text = buildShareText(game(), 'https://tenq.example')
    expect(text).toBe('TenQ.ai #4 (2026-10-20)\nSolved in 3/10 · 1:35\n🟩🟨🎯\nhttps://tenq.example')
    expect(text).not.toMatch(/walrus|alive/i)
  })

  it('marks a loss with X/10', () => {
    const text = buildShareText(game({ status: 'lost', used: 10, duration_ms: null }), 'u')
    expect(text.split('\n')[1]).toBe('X/10')
  })
})

describe('reducer', () => {
  it('clears the last answer and announces a new day', () => {
    const day1 = gameReducer(initialState, { type: 'game_loaded', game: game(), receivedAt: Date.parse('2026-10-20T11:59:00Z') })
    expect(day1.clockOffsetMs).toBe(60_000)
    const withAnswer = { ...day1, lastAnswer: { number: 1, answer: 'YES' as const, question: 'q', kind: 'question' as const } }
    const day2 = gameReducer(withAnswer, {
      type: 'game_loaded',
      game: game({ game_date: '2026-10-21', status: 'not_started' }),
      receivedAt: 0,
    })
    expect(day2.lastAnswer).toBeNull()
    expect(day2.notice?.message).toMatch(/new daily challenge/i)
  })
})

describe('error messages', () => {
  it('never exposes internal details', () => {
    const outcome = describeAskError(
      new ApiError('http', 'redis://secret@host failed', { status: 500, code: 'INTERNAL_ERROR' }),
    )
    expect(outcome.message).not.toMatch(/redis|secret/)
    expect(describeAskError(new ApiError('http', 'x', { status: 429, code: 'RATE_LIMITED', retryAfterS: 7 })).message).toMatch(/7 seconds/)
  })
})

describe('turnstile', () => {
  afterEach(() => {
    delete window.turnstile
    document.head.innerHTML = ''
  })

  it('loads the script once, executes the invisible widget, and resets it after use', async () => {
    const reset = vi.fn()
    const execute = vi.fn()
    let callback: ((token: string) => void) | undefined
    window.turnstile = {
      render: vi.fn((_el: HTMLElement, options: { callback: (t: string) => void; action: string; sitekey: string }) => {
        callback = options.callback
        expect(options.action).toBe('session')
        expect(options.sitekey).toBe('site-key')
        return 'widget-1'
      }),
      execute: vi.fn(() => {
        execute()
        callback?.('fresh-token')
      }),
      reset,
    }
    const pending = getTurnstileToken('site-key', 'session')
    const script = document.head.querySelector('script')
    expect(script?.src).toContain('challenges.cloudflare.com/turnstile/v0/api.js')
    script?.dispatchEvent(new Event('load'))

    await expect(pending).resolves.toBe('fresh-token')
    expect(execute).toHaveBeenCalledTimes(1)
    expect(reset).toHaveBeenCalledWith('widget-1')
    expect(document.body.querySelector('div[hidden]')).toBeNull()
  })
})

describe('restoreFocus', () => {
  function setup() {
    document.body.innerHTML =
      '<form id="ask"><input id="q" /><button id="b">Ask</button></form><form><input id="g" /></form>'
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb) => {
      cb(0)
      return 0
    })
    const get = (id: string) => document.getElementById(id) as HTMLElement
    return { form: get('ask'), question: get('q'), button: get('b'), guess: get('g') }
  }

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('returns focus when nothing else is focused', () => {
    const { form, question } = setup()
    restoreFocus(question, form)
    expect(document.activeElement).toBe(question)
  })

  it('returns focus from a control inside the same form', () => {
    const { form, question, button } = setup()
    button.focus()
    restoreFocus(question, form)
    expect(document.activeElement).toBe(question)
  })

  it('does not steal focus from a box the player moved to', () => {
    const { form, question, guess } = setup()
    guess.focus()
    restoreFocus(question, form)
    expect(document.activeElement).toBe(guess)
  })
})
