import { useEffect, useId, useRef, useState } from 'react'
import type { SyntheticEvent } from 'react'

import { useGame } from '../../state/GameContext'

const MAX_LENGTH = 150

export function QuestionForm() {
  const { state, ask } = useGame()
  const [question, setQuestion] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const hintId = useId()
  const disabled = state.submitting
  const trimmed = question.trim()

  // Return focus to the input when an answer arrives, so keyboard play keeps flowing.
  useEffect(() => {
    if (!state.submitting) inputRef.current?.focus()
  }, [state.submitting])

  const onSubmit = async (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (disabled || trimmed.length === 0) return
    const ok = await ask(trimmed)
    if (ok) setQuestion('')
  }

  return (
    <form className="card ask" onSubmit={(e) => void onSubmit(e)} aria-busy={state.submitting}>
      <label htmlFor="question" className="ask-label">
        Ask a yes/no question in English
      </label>
      <div className="ask-row">
        <input
          ref={inputRef}
          id="question"
          name="question"
          type="text"
          autoComplete="off"
          spellCheck
          maxLength={MAX_LENGTH}
          placeholder="Is it bigger than a car?"
          value={question}
          onChange={(e) => {
            setQuestion(e.target.value)
          }}
          aria-describedby={hintId}
          disabled={disabled}
        />
        <button type="submit" className="btn btn-primary" disabled={disabled || trimmed.length === 0}>
          {state.submitting ? (
            <>
              <span className="spinner" aria-hidden="true" /> Judging…
            </>
          ) : (
            'Ask'
          )}
        </button>
      </div>
      <p id={hintId} className="ask-hint">
        <span>End with “?”.</span>
        <span aria-label={`${String(question.length)} of ${String(MAX_LENGTH)} characters`}>
          {question.length}/{MAX_LENGTH}
        </span>
      </p>
    </form>
  )
}
