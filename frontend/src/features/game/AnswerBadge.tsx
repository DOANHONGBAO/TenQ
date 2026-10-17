import type { Answer } from '../../api/types'

const TEXT: Record<Answer, string> = {
  YES: 'Yes',
  NO: 'No',
  IRRELEVANT: 'Irrelevant',
  PENALTY: 'Penalty',
  WIN: 'Correct!',
}

export function AnswerBadge({ answer }: { answer: Answer }) {
  return <span className={`badge badge-${answer.toLowerCase()}`}>{TEXT[answer]}</span>
}
