import { useEffect, useId, useRef, useState } from 'react'
import type { KeyboardEvent, SyntheticEvent } from 'react'

import { ApiError } from '../../api/client'
import type { Api } from '../../api/client'
import type { GameState } from '../../api/types'
import { formatDuration } from '../../lib/format'
import { prefersReducedMotion } from '../../lib/motion'
import { loadPlayerName, savePlayerName } from '../../lib/playerName'
import { Confetti } from './Confetti'
import { TreasureChest } from './TreasureChest'

const OPEN_DELAY_MS = 900
const NAME_MAX = 20

interface Props {
  client: Api
  game: GameState
  /** `celebrate`: the chest opens with confetti first; `name`: straight to the name form. */
  mode: 'celebrate' | 'name'
  onClose: () => void
  onNameSaved: (name: string) => void
}

function nameError(error: unknown): string {
  if (error instanceof ApiError && error.code === 'INVALID_NAME') {
    return error.message && error.message !== 'INVALID_NAME'
      ? error.message
      : 'Use 2 to 20 letters, digits, or spaces.'
  }
  if (error instanceof ApiError && error.code === 'RATE_LIMITED') {
    return 'Too many changes. Try again a bit later.'
  }
  return 'Could not save your name right now. Please try again.'
}

/** Win celebration (treasure chest + confetti) followed by the leaderboard name form. */
export function WinCelebration({ client, game, mode, onClose, onNameSaved }: Props) {
  const reduced = prefersReducedMotion()
  const [open, setOpen] = useState(mode === 'name' || reduced)
  const [burst, setBurst] = useState(0)
  const [name, setName] = useState(loadPlayerName)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState<string | null>(null)
  const dialogRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const titleId = useId()
  const errorId = useId()

  // The chest wobbles for a moment, then pops open with confetti.
  useEffect(() => {
    if (open) return
    const timer = setTimeout(() => {
      setOpen(true)
      setBurst((n) => n + 1)
    }, OPEN_DELAY_MS)
    return () => {
      clearTimeout(timer)
    }
  }, [open])

  // Keep keyboard focus inside the dialog; start on the name field once it is shown.
  useEffect(() => {
    if (open) inputRef.current?.focus()
    else dialogRef.current?.focus()
  }, [open])

  const openNow = () => {
    if (open) return
    setOpen(true)
    setBurst((n) => n + 1)
  }

  const onSubmit = async (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault()
    const trimmed = name.trim()
    if (saving || trimmed.length < 2) {
      setError('Use 2 to 20 letters, digits, or spaces.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const result = await client.setName(trimmed)
      savePlayerName(result.display_name)
      setSaved(result.display_name)
      onNameSaved(result.display_name)
    } catch (err: unknown) {
      setError(nameError(err))
    } finally {
      setSaving(false)
    }
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      onClose()
      return
    }
    if (event.key !== 'Tab') return
    const focusable = dialogRef.current?.querySelectorAll<HTMLElement>('button, input')
    if (!focusable || focusable.length === 0) return
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last?.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first?.focus()
    }
  }

  return (
    <div className="overlay" onKeyDown={onKeyDown}>
      <Confetti burst={burst} />
      <div
        ref={dialogRef}
        className="celebration"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        {mode === 'celebrate' && (
          <button type="button" className="chest-button" onClick={openNow} aria-label="Open the chest">
            <TreasureChest open={open} />
          </button>
        )}
        <h2 id={titleId} className="celebration-title">
          {mode === 'celebrate' ? 'You got it!' : 'Your leaderboard name'}
        </h2>
        {mode === 'celebrate' && (
          <p className="celebration-stats">
            <span className="stat-bubble">
              <strong>{game.used}</strong>/{game.max_questions} tries
            </span>
            {game.duration_ms !== null && (
              <span className="stat-bubble">
                <strong>{formatDuration(game.duration_ms)}</strong>
              </span>
            )}
          </p>
        )}

        {open && saved === null && (
          <form className="name-form" onSubmit={(e) => void onSubmit(e)} noValidate>
            <label htmlFor="player-name" className="name-label">
              Put your name on today’s leaderboard
            </label>
            <input
              ref={inputRef}
              id="player-name"
              name="player-name"
              type="text"
              autoComplete="nickname"
              maxLength={NAME_MAX}
              placeholder="Your name"
              value={name}
              onChange={(e) => {
                setName(e.target.value)
              }}
              aria-invalid={error !== null}
              aria-describedby={error ? errorId : undefined}
              disabled={saving}
            />
            {error && (
              <p id={errorId} className="name-error" role="alert">
                {error}
              </p>
            )}
            <div className="name-actions">
              <button type="submit" className="btn btn-primary" disabled={saving}>
                {saving ? 'Saving…' : 'Save my name'}
              </button>
              <button type="button" className="btn btn-ghost" onClick={onClose}>
                Maybe later
              </button>
            </div>
          </form>
        )}

        {saved !== null && (
          <div className="name-saved" role="status">
            <p>
              You are on the board as <strong>{saved}</strong>.
            </p>
            <button type="button" className="btn btn-primary" onClick={onClose}>
              Awesome!
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
