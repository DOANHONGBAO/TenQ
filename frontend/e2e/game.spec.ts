import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

import { installFakeBackend } from './fakeBackend.ts'

const remaining = (page: Page) => page.getByRole('heading', { name: /questions left/i })

async function ask(page: Page, text: string) {
  await page.getByLabel(/ask a yes\/no question/i).fill(text)
  await page.getByLabel(/ask a yes\/no question/i).press('Enter')
}

test('first visit passes Turnstile once and starts a fresh game', async ({ page }) => {
  const backend = await installFakeBackend(page)
  await page.goto('/')

  await expect(remaining(page)).toHaveText(/10 of 10 questions left/)
  await expect(page.getByText(/daily challenge/i)).toContainText('#4')
  await expect(page.getByText(/one idea per question/i)).toBeVisible()
  expect(backend.sessionCreated).toBe(1)
  expect(await page.evaluate(() => (window as unknown as { __tsResets?: number }).__tsResets)).toBe(1)
})

test('a full losing game, then refresh keeps the result', async ({ page }) => {
  await installFakeBackend(page, { answers: ['YES', 'NO', 'IRRELEVANT', 'PENALTY'] })
  await page.goto('/')
  await expect(remaining(page)).toBeVisible()

  for (let n = 1; n <= 10; n++) {
    await ask(page, `Is it question ${String(n)}?`)
    if (n < 10) await expect(remaining(page)).toHaveText(new RegExp(`${String(10 - n)} of 10`))
  }

  await expect(page.getByRole('heading', { name: /out of questions/i })).toBeVisible()
  await expect(page.getByLabel(/ask a yes\/no question/i)).toHaveCount(0)
  await expect(page.getByText(/revealed after the next reset/i)).toBeVisible()
  await expect(page.getByText('walrus')).toHaveCount(0)
  await expect(page.getByRole('region', { name: /hints/i })).toContainText('4/4')

  await page.reload()
  await expect(page.getByRole('heading', { name: /out of questions/i })).toBeVisible()
  await expect(page.getByText('Is it question 10?')).toBeVisible()
})

test('refresh in the middle of a game keeps history and attempts', async ({ page }) => {
  await installFakeBackend(page, { answers: ['YES', 'NO'] })
  await page.goto('/')
  await ask(page, 'Is it alive?')
  await expect(remaining(page)).toHaveText(/9 of 10/)
  await ask(page, 'Is it big?')
  await expect(remaining(page)).toHaveText(/8 of 10/)

  await page.reload()

  await expect(remaining(page)).toHaveText(/8 of 10/)
  await expect(page.getByText('Is it alive?')).toBeVisible()
  await expect(page.getByRole('region', { name: /hints/i })).toContainText('Hint one')
})

test('winning with the guess box shows the win screen and share', async ({ page }) => {
  await installFakeBackend(page)
  await page.goto('/')
  await page.getByLabel(/guess the word/i).fill('penguin')
  await page.getByRole('button', { name: /^guess$/i }).click()
  await expect(page.getByText(/“penguin” is not the word/i)).toBeVisible()

  await page.getByLabel(/guess the word/i).fill('Walrus')
  await page.getByRole('button', { name: /^guess$/i }).click()

  // Celebration: the chest opens, then the winner can put a name on the leaderboard.
  const dialog = page.getByRole('dialog', { name: /you got it/i })
  await expect(dialog).toBeVisible()
  const name = dialog.getByLabel(/your name on today’s leaderboard/i)
  await expect(name).toBeFocused()
  await name.fill('Trang')
  await dialog.getByRole('button', { name: /save my name/i }).click()
  await expect(dialog).toContainText('You are on the board as Trang')
  await dialog.getByRole('button', { name: /awesome/i }).click()
  await expect(dialog).toHaveCount(0)

  const heading = page.getByRole('heading', { name: /solved/i })
  await expect(heading).toBeFocused()
  await expect(page.getByText(/solved in 2 of 10 questions/i)).toBeVisible()
  await expect(page.getByText(/on the leaderboard as trang/i)).toBeVisible()
  await expect(page.getByRole('region', { name: /leaderboard/i })).toContainText('Trang')
  await expect(page.getByRole('button', { name: /share result/i })).toBeVisible()
})

test('leaderboard lists anonymous winners', async ({ page }) => {
  await installFakeBackend(page, {
    winners: [
      { rank: 1, display_name: 'Player-AAA111', questions: 3, duration_ms: 61_000 },
      { rank: 2, display_name: 'Player-BBB222', questions: 4, duration_ms: 30_000 },
    ],
  })
  await page.goto('/')
  const board = page.getByRole('region', { name: /leaderboard/i })
  await expect(board.getByRole('row')).toHaveCount(3)
  await expect(board).toContainText('Player-AAA111')
  await expect(board).toContainText('1:01')
})

test('maintenance state, then recovery with Try again', async ({ page }) => {
  const backend = await installFakeBackend(page, { down: true })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: /be right back/i })).toBeVisible()

  backend.down = false
  await page.getByRole('button', { name: /try again/i }).click()
  await expect(remaining(page)).toHaveText(/10 of 10/)
})

test('layout fits the viewport without horizontal scrolling', async ({ page }) => {
  await installFakeBackend(page)
  await page.goto('/')
  await expect(remaining(page)).toBeVisible()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  expect(overflow).toBeLessThanOrEqual(0)
  // overflow-x: clip hides the page scroll, so also check that no card is cut off.
  const cutOff = await page.evaluate(
    () =>
      [...document.querySelectorAll('.card')].filter(
        (card) => card.getBoundingClientRect().right > window.innerWidth,
      ).length,
  )
  expect(cutOff).toBe(0)
  await expect(page.getByLabel(/ask a yes\/no question/i)).toBeInViewport()
})
