import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ApiError } from '../api/client'
import type { Answer } from '../api/types'
import { createFakeServer, httpError } from '../test/fakeApi'
import type { FakeServer } from '../test/fakeApi'
import { App } from './App'

function renderApp(server: FakeServer, getToken = vi.fn(() => Promise.resolve('token-1'))) {
  const view = render(<App client={server.api} getToken={getToken} />)
  return { ...view, getToken, user: userEvent.setup() }
}

async function ready() {
  return screen.findByRole('heading', { name: /questions left/i })
}

async function askQuestion(user: ReturnType<typeof userEvent.setup>, text: string) {
  const input = screen.getByLabelText(/ask a yes\/no question/i)
  await user.clear(input)
  await user.type(input, text)
  await user.click(screen.getByRole('button', { name: /^ask$/i }))
}

describe('session and loading', () => {
  it('shows a loading state, passes Turnstile once, then shows the game', async () => {
    const server = createFakeServer()
    const { getToken } = renderApp(server)

    expect(screen.getByText(/preparing today/i)).toBeInTheDocument()
    expect(await ready()).toHaveTextContent('10 of 10 questions left')
    expect(getToken).toHaveBeenCalledTimes(1)
    expect(server.api.createSession).toHaveBeenCalledWith('token-1')
    expect(screen.getByText(/daily challenge/i)).toHaveTextContent('#4')
  })

  it('reuses an existing session without Turnstile', async () => {
    const server = createFakeServer({ hasSession: true })
    const { getToken } = renderApp(server)
    await ready()
    expect(getToken).not.toHaveBeenCalled()
  })

  it('recovers when the session expires mid-game', async () => {
    const server = createFakeServer({ hasSession: true })
    const { user, getToken } = renderApp(server)
    await ready()
    server.hasSession = false // cookie cleared or expired

    await askQuestion(user, 'Is it alive?')

    expect(await screen.findByText('9')).toBeInTheDocument()
    expect(getToken).toHaveBeenCalledTimes(1)
  })

  it('shows a maintenance screen and recovers with Try again', async () => {
    const server = createFakeServer({
      hasSession: true,
      getGameFailures: [new ApiError('network', 'offline')],
    })
    const { user } = renderApp(server)

    expect(await screen.findByRole('heading', { name: /be right back/i })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /try again/i }))
    expect(await ready()).toBeInTheDocument()
  })

  it('shows an error screen if the session cannot be created', async () => {
    const server = createFakeServer()
    renderApp(server, vi.fn(() => Promise.reject(new Error('turnstile failed'))))
    expect(await screen.findByRole('heading', { name: /something went wrong/i })).toBeInTheDocument()
  })
})

describe('asking questions', () => {
  it.each<[Answer, RegExp]>([
    ['YES', /good lead/i],
    ['NO', /not that/i],
    ['IRRELEVANT', /cannot really be answered/i],
    ['PENALTY', /not a genuine yes\/no question/i],
  ])('shows feedback for %s and updates the remaining attempts', async (answer, text) => {
    const server = createFakeServer({ hasSession: true, nextAnswers: [answer] })
    const { user } = renderApp(server)
    await ready()

    await askQuestion(user, 'Is it alive?')

    const live = await screen.findByText(text)
    expect(live.closest('[aria-live="polite"]')).not.toBeNull()
    expect(screen.getByRole('heading', { name: /questions left/i })).toHaveTextContent('9 of 10')
    const history = screen.getByRole('region', { name: /your questions/i })
    expect(within(history).getByText('Is it alive?')).toBeInTheDocument()
  })

  it('disables input and submit while judging, and sends a double click once', async () => {
    const server = createFakeServer({ hasSession: true, holdAsks: true })
    const { user } = renderApp(server)
    await ready()
    await user.type(screen.getByLabelText(/ask a yes\/no question/i), 'Is it alive?')

    const button = screen.getByRole('button', { name: /^ask$/i })
    await user.dblClick(button)

    expect(await screen.findByRole('button', { name: /judging/i })).toBeDisabled()
    expect(screen.getByLabelText(/ask a yes\/no question/i)).toBeDisabled()
    await act(async () => {
      server.release()
      await Promise.resolve()
    })
    await screen.findByText(/not that/i)
    expect(server.askCalls).toHaveLength(1)
  })

  it('keeps the server count when the judge is unavailable and retries with the same key', async () => {
    const server = createFakeServer({
      hasSession: true,
      askFailures: [{ error: httpError(503, 'AI_UNAVAILABLE') }],
    })
    const { user } = renderApp(server)
    await ready()

    await askQuestion(user, 'Is it alive?')
    expect(await screen.findByText(/you were not charged/i)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /questions left/i })).toHaveTextContent('10 of 10')

    await user.click(screen.getByRole('button', { name: /^ask$/i })) // the text is still there
    await screen.findByText(/not that/i)
    expect(server.askCalls[0]?.key).toBe(server.askCalls[1]?.key)
  })

  it('after a timeout shows the count the server really has', async () => {
    // The server charged the question but the response never arrived.
    const server = createFakeServer({
      hasSession: true,
      askFailures: [{ error: new ApiError('timeout', 'slow'), charge: true }],
    })
    const { user } = renderApp(server)
    await ready()

    await askQuestion(user, 'Is it alive?')

    expect(await screen.findByText(/could not reach the server/i)).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /questions left/i })).toHaveTextContent('9 of 10')
    })
  })

  it('explains invalid questions without charging', async () => {
    const server = createFakeServer({
      hasSession: true,
      askFailures: [{ error: httpError(422, 'INVALID_QUESTION', { reason: 'not_a_question' }) }],
    })
    const { user } = renderApp(server)
    await ready()
    await askQuestion(user, 'Is it alive')
    expect(await screen.findByText(/end your question with a question mark/i)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /questions left/i })).toHaveTextContent('10 of 10')
  })
})

describe('persistence', () => {
  it('keeps history after a page refresh because state comes from the server', async () => {
    const server = createFakeServer({ hasSession: true, nextAnswers: ['YES', 'NO'] })
    const first = renderApp(server)
    await ready()
    await askQuestion(first.user, 'Is it alive?')
    await askQuestion(first.user, 'Is it big?')
    await screen.findByText('Is it big?')
    first.unmount()

    renderApp(server) // the "refreshed" page
    expect(await ready()).toHaveTextContent('8 of 10')
    expect(screen.getByText('Is it alive?')).toBeInTheDocument()
    expect(screen.getByText('Is it big?')).toBeInTheDocument()
  })

  it('reuses the idempotency key for an unfinished submission after a refresh', async () => {
    const server = createFakeServer({
      hasSession: true,
      askFailures: [{ error: new ApiError('network', 'down') }],
    })
    const first = renderApp(server)
    await ready()
    await askQuestion(first.user, 'Is it alive?')
    await screen.findByText(/could not reach the server/i)
    first.unmount()

    const second = renderApp(server)
    await ready()
    await askQuestion(second.user, 'Is it alive?')
    await screen.findByText(/not that/i)
    expect(server.askCalls[1]?.key).toBe(server.askCalls[0]?.key)
  })
})

describe('end of game', () => {
  it('shows the winning screen, focuses it, and hides the form', async () => {
    const server = createFakeServer({ hasSession: true, nextAnswers: ['NO', 'WIN'] })
    const { user } = renderApp(server)
    await ready()
    await askQuestion(user, 'Is it alive?')
    await askQuestion(user, 'Is it a walrus?')

    const heading = await screen.findByRole('heading', { name: /you got it/i })
    expect(heading).toHaveFocus()
    expect(screen.getByText(/solved in/i)).toHaveTextContent('Solved in 2 of 10 questions in 2:05')
    expect(screen.queryByLabelText(/ask a yes\/no question/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /share result/i })).toBeInTheDocument()
  })

  it('shows the losing screen without revealing the word', async () => {
    const history = Array.from({ length: 10 }, (_, i) => ({
      number: i + 1,
      question: `Is it number ${String(i)}?`,
      answer: 'NO' as const,
      asked_at: '2026-10-20T11:00:00.000Z',
      kind: 'question' as const,
    }))
    const server = createFakeServer({ hasSession: true, history, status: 'lost' })
    renderApp(server)

    expect(await screen.findByRole('heading', { name: /out of questions/i })).toBeInTheDocument()
    expect(screen.getByText(/revealed after the next reset/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^ask$/i })).not.toBeInTheDocument()
    expect(await ready()).toHaveTextContent('0 of 10')
  })
})

describe('accessibility', () => {
  it('can be played with the keyboard only', async () => {
    const server = createFakeServer({ hasSession: true, nextAnswers: ['YES'] })
    const { user } = renderApp(server)
    await ready()

    const input = screen.getByLabelText(/ask a yes\/no question/i)
    await waitFor(() => {
      expect(input).toHaveFocus()
    })
    await user.keyboard('Is it alive?{Enter}')

    await screen.findByText(/good lead/i)
    await waitFor(() => {
      expect(input).toHaveFocus() // focus returns for the next question
    })
    expect(input).toHaveValue('')
  })

  it('offers a skip link and labelled regions', async () => {
    const server = createFakeServer({ hasSession: true })
    renderApp(server)
    await ready()
    expect(screen.getByRole('link', { name: /skip to the game/i })).toHaveAttribute('href', '#play')
    expect(screen.getByRole('region', { name: /leaderboard/i })).toBeInTheDocument()
    expect(screen.getByRole('timer')).toHaveTextContent(/^1[12]:[0-5]\d:[0-5]\d$/)
  })
})

describe('leaderboard', () => {
  it('lists winners and the caller rank', async () => {
    const server = createFakeServer({
      hasSession: true,
      leaderboard: {
        game_date: '2026-10-20',
        entries: [{ rank: 1, display_name: 'Player-ABC123', questions: 3, duration_ms: 61_000 }],
        me: { rank: 1, questions: 3, duration_ms: 61_000 },
        total_winners: 1,
      },
    })
    renderApp(server)
    const board = await screen.findByRole('region', { name: /leaderboard/i })
    expect(await within(board).findByText('Player-ABC123')).toBeInTheDocument()
    expect(within(board).getByText('1:01')).toBeInTheDocument()
    expect(within(board).getByText(/you are/i)).toHaveTextContent('#1 of 1')
  })
})

describe('hints and guesses', () => {
  async function guessWord(user: ReturnType<typeof userEvent.setup>, word: string) {
    const input = screen.getByLabelText(/guess the word/i)
    await user.clear(input)
    await user.type(input, word)
    await user.click(screen.getByRole('button', { name: /^guess$/i }))
  }

  it('unlocks one hint after every two tries', async () => {
    const server = createFakeServer({ hasSession: true })
    const { user } = renderApp(server)
    await ready()
    const hints = screen.getByRole('region', { name: /hints/i })
    expect(within(hints).getByText(/next hint after 2 more tries/i)).toBeInTheDocument()
    expect(within(hints).queryByRole('listitem')).not.toBeInTheDocument()

    await askQuestion(user, 'Is it alive?')
    expect(await within(hints).findByText(/next hint after 1 more try/i)).toBeInTheDocument()
    await guessWord(user, 'penguin') // guesses count towards hints too
    // Wait for the guess to be judged before looking for the hint (CI machines are slower).
    await screen.findByText(/“penguin” is not the word/i, {}, { timeout: 5000 })

    expect(await within(hints).findByText('Hint one: vague.', {}, { timeout: 5000 })).toBeInTheDocument()
    expect(within(hints).queryByText('Hint two: a category.')).not.toBeInTheDocument()
    expect(hints).toHaveTextContent('1/4')
  })

  it('a wrong guess costs one try and is labelled in the history', async () => {
    const server = createFakeServer({ hasSession: true })
    const { user } = renderApp(server)
    await ready()

    await guessWord(user, 'penguin')

    expect(await screen.findByText(/“penguin” is not the word/i)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /questions left/i })).toHaveTextContent('9 of 10')
    const history = screen.getByRole('region', { name: /questions and guesses/i })
    expect(within(history).getByText('Wrong')).toBeInTheDocument()
    expect(within(history).getByText(/guess:/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/guess the word/i)).toHaveValue('')
  })

  it('a correct guess wins the game', async () => {
    const server = createFakeServer({ hasSession: true })
    const { user } = renderApp(server)
    await ready()

    await guessWord(user, 'Walrus')

    expect(await screen.findByRole('heading', { name: /you got it/i })).toBeInTheDocument()
    expect(screen.queryByLabelText(/guess the word/i)).not.toBeInTheDocument()
    expect(server.api.guess).toHaveBeenCalledTimes(1)
  })

  it('explains an invalid guess without charging', async () => {
    const server = createFakeServer({ hasSession: true })
    const { user } = renderApp(server)
    await ready()
    await guessWord(user, 'two words')
    expect(await screen.findByText(/single english word/i)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /questions left/i })).toHaveTextContent('10 of 10')
  })
})
