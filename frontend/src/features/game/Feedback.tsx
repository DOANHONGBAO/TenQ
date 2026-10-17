import type { Answer } from '../../api/types'
import type { LastAnswer } from '../../state/gameReducer'
import { AnswerBadge } from './AnswerBadge'

const EXPLAIN: Record<Answer, string> = {
  YES: 'Good lead. Keep narrowing it down.',
  NO: 'Not that. Try another angle.',
  IRRELEVANT: 'That cannot really be answered for this word. Try a more concrete question.',
  PENALTY: 'That was not a genuine yes/no question about the word, so it cost a question.',
  WIN: 'You found the word!',
}

/** The latest answer, announced to screen readers through the polite live region. */
export function Feedback({ last }: { last: LastAnswer | null }) {
  return (
    <div className="feedback" aria-live="polite" aria-atomic="true">
      {last && (
        <p className={`feedback-body feedback-${last.answer.toLowerCase()}`}>
          <span className="sr-only">
            {last.kind === 'guess' ? 'Guess' : 'Question'} {last.number}:{' '}
          </span>
          <AnswerBadge answer={last.answer} kind={last.kind} />{' '}
          <span>
            {last.kind === 'guess' && last.answer === 'NO'
              ? `“${last.question}” is not the word. Keep going!`
              : EXPLAIN[last.answer]}
          </span>
        </p>
      )}
    </div>
  )
}
