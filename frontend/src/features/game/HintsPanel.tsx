import type { GameState } from '../../api/types'

/** Hints unlocked so far (the server decides how many), plus when the next one arrives. */
export function HintsPanel({ game }: { game: GameState }) {
  const locked = game.hints_total - game.hints.length
  return (
    <section className="card hints" aria-labelledby="hints-title">
      <h2 id="hints-title">
        Hints <span className="muted">{game.hints.length}/{game.hints_total}</span>
      </h2>
      {game.hints.length > 0 && (
        <ol className="hint-list" aria-live="polite">
          {game.hints.map((hint, i) => (
            <li key={i} className="hint">
              <span className="hint-number" aria-hidden="true">
                {i + 1}
              </span>
              <span>{hint}</span>
            </li>
          ))}
        </ol>
      )}
      {game.next_hint_in !== null && locked > 0 && (
        <p className="muted hint-next">
          Next hint after {game.next_hint_in} more {game.next_hint_in === 1 ? 'try' : 'tries'}.
        </p>
      )}
    </section>
  )
}
