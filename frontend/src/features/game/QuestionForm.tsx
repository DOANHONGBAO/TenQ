import { useEffect, useId, useRef, useState } from 'react'
import type { SyntheticEvent } from 'react'

import { restoreFocus } from '../../lib/focus'
import { useGame } from '../../state/GameContext'

const MAX_LENGTH = 150

export function QuestionForm() {
  const { state, ask } = useGame()
  const [question, setQuestion] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const hintId = useId()
  const disabled = state.submitting
  const trimmed = question.trim()

  // Start with the question box focused.
  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const onSubmit = async (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault()
    const form = event.currentTarget
    if (disabled || trimmed.length === 0) return
    const ok = await ask(trimmed)
    if (ok) setQuestion('')
    // Return focus to this input when the answer arrives, so keyboard play keeps flowing.
    restoreFocus(inputRef.current, form)
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
