import type { Answer, GameState } from '../../api/types'

const LABEL: Record<Answer, string> = {
  YES: 'yes',
  NO: 'no',
  IRRELEVANT: 'irrelevant',
  PENALTY: 'penalty',
  WIN: 'win',
}

/** Ten indicators: used ones show the answer they received; the count comes from the server. */
export function AttemptsMeter({ game }: { game: GameState }) {
  const slots = Array.from({ length: game.max_questions }, (_, i) => game.history[i] ?? null)
  return (
    <section className="card meter" aria-labelledby="meter-title">
      <h2 id="meter-title" className="meter-title">
        <span>{game.remaining}</span> of {game.max_questions} questions left
      </h2>
      <ol className="meter-dots" aria-hidden="true">
        {slots.map((entry, i) => (
          <li
            key={i}
            className={`dot ${entry ? `dot-${LABEL[entry.answer]}` : 'dot-empty'}`}
            title={entry ? `Question ${String(i + 1)}: ${entry.answer}` : `Question ${String(i + 1)}: unused`}
          />
        ))}
      </ol>
    </section>
  )
}
