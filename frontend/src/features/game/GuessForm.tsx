import { useId, useRef, useState } from 'react'
import type { SyntheticEvent } from 'react'

import { useGame } from '../../state/GameContext'

/** Direct guess of the secret word. Judged exactly by the server; costs one of the 10 tries. */
export function GuessForm() {
  const { state, guess } = useGame()
  const [word, setWord] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const noteId = useId()
  const trimmed = word.trim()
  const remaining = state.game?.remaining ?? 0

  const onSubmit = async (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (state.submitting || trimmed.length === 0) return
    const ok = await guess(trimmed)
    if (ok) setWord('')
    requestAnimationFrame(() => inputRef.current?.focus())
  }

  return (
    <form className="card guess" onSubmit={(e) => void onSubmit(e)} aria-busy={state.submitting}>
      <label htmlFor="guess" className="ask-label">
        Guess the word
      </label>
      <div className="ask-row">
        <input
          ref={inputRef}
          id="guess"
          name="guess"
          type="text"
          autoComplete="off"
          autoCapitalize="none"
          spellCheck={false}
          maxLength={32}
          placeholder="walrus"
          value={word}
          onChange={(e) => {
            setWord(e.target.value)
          }}
          aria-describedby={noteId}
          disabled={state.submitting}
        />
        <button
          type="submit"
          className="btn btn-secondary"
          disabled={state.submitting || trimmed.length === 0}
        >
          Guess
        </button>
      </div>
      <p id={noteId} className="ask-hint">
        <span>One word. A guess uses 1 of your {remaining} remaining tries.</span>
      </p>
    </form>
  )
}
