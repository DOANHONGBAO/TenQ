import { useEffect, useRef, useState } from 'react'

import type { GameState } from '../../api/types'
import { formatDuration } from '../../lib/format'
import { buildShareText, shareResult } from '../../lib/share'

/**
 * Win or lose screen. It never shows the secret word: on a win the player already typed it,
 * and on a loss the word is revealed only after the UTC reset (see YesterdayAnswer).
 */
interface Props {
  game: GameState
  /** The leaderboard name saved in this visit, if any. */
  playerName: string | null
  onChooseName: () => void
}

export function ResultPanel({ game, playerName, onChooseName }: Props) {
  const headingRef = useRef<HTMLHeadingElement>(null)
  const [shareState, setShareState] = useState<'idle' | 'copied' | 'shared' | 'failed'>('idle')
  const won = game.status === 'won'

  // Move focus to the result so keyboard and screen reader users notice the game ended.
  useEffect(() => {
    headingRef.current?.focus()
  }, [])

  const onShare = async () => {
    setShareState(await shareResult(buildShareText(game, window.location.origin)))
  }

  return (
    <section className={`card result ${won ? 'result-won' : 'result-lost'}`} aria-labelledby="result-title">
      <h2 id="result-title" ref={headingRef} tabIndex={-1}>
        {won ? 'Solved!' : 'Out of questions'}
      </h2>
      {won ? (
        <p>
          Solved in <strong>{game.used}</strong> of {game.max_questions} questions
          {game.duration_ms !== null && (
            <>
              {' '}
              in <strong>{formatDuration(game.duration_ms)}</strong>
            </>
          )}
          .
        </p>
      ) : (
        <p>
          You used all {game.max_questions} questions. The word is revealed after the next reset at
          00:00 UTC.
        </p>
      )}
      {won && playerName && (
        <p className="result-name">
          On the leaderboard as <strong>{playerName}</strong>
        </p>
      )}
      <div className="result-actions">
        <button type="button" className="btn btn-primary" onClick={() => void onShare()}>
          Share result
        </button>
        {won && (
          <button type="button" className="btn btn-secondary" onClick={onChooseName}>
            {playerName ? 'Change my name' : 'Add my name'}
          </button>
        )}
        <span className="share-status" role="status">
          {shareState === 'copied' && 'Copied to clipboard. No spoilers included.'}
          {shareState === 'shared' && 'Shared!'}
          {shareState === 'failed' && 'Could not share. Try copying manually.'}
        </span>
      </div>
    </section>
  )
}
