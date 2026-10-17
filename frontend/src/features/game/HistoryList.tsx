import type { HistoryEntry } from '../../api/types'
import { AnswerBadge } from './AnswerBadge'

export function HistoryList({ history }: { history: HistoryEntry[] }) {
  return (
    <section className="card history" aria-labelledby="history-title">
      <h2 id="history-title">Your questions</h2>
      {history.length === 0 ? (
        <p className="muted">No questions yet. Start broad: “Is it alive?”</p>
      ) : (
        <ol className="history-list">
          {[...history].reverse().map((entry) => (
            <li key={entry.number} className="history-item">
              <span className="history-number" aria-hidden="true">
                {entry.number}
              </span>
              <span className="history-question">
                <span className="sr-only">Question {entry.number}: </span>
                {entry.question}
              </span>
              <AnswerBadge answer={entry.answer} />
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
