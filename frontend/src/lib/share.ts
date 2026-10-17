import type { Answer, GameState } from '../api/types'
import { challengeNumber, formatDuration } from './format'

const EMOJI: Record<Answer, string> = {
  YES: '🟩',
  NO: '🟥',
  IRRELEVANT: '⬜',
  PENALTY: '🟨',
  WIN: '🎯',
}

/** Spoiler-free summary: answers as squares, never the questions or the word. */
export function buildShareText(game: GameState, url: string): string {
  const header = `TenQ.ai #${String(challengeNumber(game.game_date))} (${game.game_date})`
  const result =
    game.status === 'won'
      ? `Solved in ${String(game.used)}/${String(game.max_questions)}${
          game.duration_ms === null ? '' : ` · ${formatDuration(game.duration_ms)}`
        }`
      : `X/${String(game.max_questions)}`
  const squares = game.history.map((h) => EMOJI[h.answer]).join('')
  return `${header}\n${result}\n${squares}\n${url}`
}

export async function shareResult(text: string): Promise<'shared' | 'copied' | 'failed'> {
  try {
    if (typeof navigator.share === 'function') {
      await navigator.share({ text })
      return 'shared'
    }
    await navigator.clipboard.writeText(text)
    return 'copied'
  } catch {
    return 'failed'
  }
}
