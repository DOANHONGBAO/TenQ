import type { Answer, AttemptKind } from '../../api/types'

const TEXT: Record<Answer, string> = {
  YES: 'Yes',
  NO: 'No',
  IRRELEVANT: 'Irrelevant',
  PENALTY: 'Penalty',
  WIN: 'Correct!',
}

export function AnswerBadge({ answer, kind = 'question' }: { answer: Answer; kind?: AttemptKind }) {
  const text = kind === 'guess' && answer === 'NO' ? 'Wrong' : TEXT[answer]
  return <span className={`badge badge-${answer.toLowerCase()}`}>{text}</span>
}
