import { ApiError } from '../api/client'

const INVALID_REASONS: Record<string, string> = {
  too_short: 'That question is too short.',
  too_long: 'Please keep your question under 150 characters.',
  invalid_characters: 'Please use plain English letters, numbers, and punctuation.',
  not_a_question: 'Please end your question with a question mark (?).',
}

export interface ErrorOutcome {
  message: string
  tone: 'info' | 'warning' | 'error'
  // Keep the Idempotency-Key so a retry of the same question can never be charged twice.
  keepPending: boolean
}

/** Map an API failure to a polite message. Wording never reveals implementation details. */
export function describeAskError(error: unknown): ErrorOutcome {
  if (!(error instanceof ApiError)) {
    return { tone: 'error', keepPending: true, message: 'Something went wrong. Please try again.' }
  }
  if (error.kind === 'timeout' || error.kind === 'network') {
    return {
      tone: 'warning',
      keepPending: true,
      message:
        'We could not reach the server. Your question was not lost: press Ask again to retry safely.',
    }
  }
  switch (error.code) {
    case 'INVALID_QUESTION':
      return {
        tone: 'warning',
        keepPending: false,
        message: INVALID_REASONS[error.details.reason ?? ''] ?? 'Please ask a short English yes/no question.',
      }
    case 'DUPLICATE_QUESTION':
      return { tone: 'info', keepPending: false, message: 'You already asked that today. Try a different question.' }
    case 'AI_UNAVAILABLE':
      return {
        tone: 'warning',
        keepPending: true,
        message: 'The judge is busy right now. You were not charged; please try again in a moment.',
      }
    case 'AI_INVALID_RESPONSE':
      return {
        tone: 'warning',
        keepPending: false,
        message: 'The judge could not answer that clearly. You were not charged; try rephrasing.',
      }
    case 'RATE_LIMITED':
      return {
        tone: 'warning',
        keepPending: true,
        message: `You are going a little fast. Please wait ${String(error.retryAfterS ?? 10)} seconds.`,
      }
    case 'QUESTION_IN_PROGRESS':
      return { tone: 'info', keepPending: true, message: 'Your previous question is still being judged.' }
    case 'GAME_FINISHED':
    case 'ATTEMPT_LIMIT_REACHED':
      return { tone: 'info', keepPending: false, message: "Today's game is over. Come back after the reset!" }
    case 'SERVICE_UNAVAILABLE':
      return { tone: 'error', keepPending: true, message: 'TenQ is under maintenance. Please try again soon.' }
    default:
      return { tone: 'error', keepPending: false, message: 'Something went wrong. Please try again.' }
  }
}
