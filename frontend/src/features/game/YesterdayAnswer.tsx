import { useState } from 'react'

import type { Api } from '../../api/client'
import { previousDate } from '../../lib/format'

/**
 * Yesterday's word, which the server allows once that UTC day has ended (OQ-08).
 * The parent keys this component by game date, so a new day starts hidden again.
 */
export function YesterdayAnswer({ client, gameDate }: { client: Api; gameDate: string }) {
  const [word, setWord] = useState<string | null>(null)
  const [revealed, setRevealed] = useState(false)
  const yesterday = previousDate(gameDate)

  const reveal = () => {
    client
      .answer(yesterday)
      .then((answer) => {
        setWord(answer.word)
        setRevealed(true)
      })
      .catch(() => {
        setWord(null)
        setRevealed(true)
      })
  }

  return (
    <p className="yesterday">
      {!revealed ? (
        <button type="button" className="btn btn-link" onClick={reveal}>
          Show yesterday’s word
        </button>
      ) : word ? (
        <span>
          Yesterday’s word: <strong>{word}</strong>
        </span>
      ) : (
        <span className="muted">No puzzle was played yesterday.</span>
      )}
    </p>
  )
}
