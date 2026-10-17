// The only client-side persistence: an unfinished submission, so a retry after a reload
// reuses the same Idempotency-Key and can never be charged twice. Game state itself always
// comes from the server.

const KEY = 'tenq.pendingSubmission'

export interface PendingSubmission {
  gameDate: string
  kind: 'question' | 'guess'
  question: string
  idempotencyKey: string
}

function isPending(v: unknown): v is PendingSubmission {
  return (
    typeof v === 'object' &&
    v !== null &&
    'gameDate' in v &&
    'kind' in v &&
    (v.kind === 'question' || v.kind === 'guess') &&
    'question' in v &&
    'idempotencyKey' in v &&
    typeof v.gameDate === 'string' &&
    typeof v.question === 'string' &&
    typeof v.idempotencyKey === 'string'
  )
}

export function loadPending(): PendingSubmission | null {
  try {
    const raw = sessionStorage.getItem(KEY)
    const parsed: unknown = raw === null ? null : JSON.parse(raw)
    return isPending(parsed) ? parsed : null
  } catch {
    return null
  }
}

export function savePending(pending: PendingSubmission | null): void {
  try {
    if (pending === null) sessionStorage.removeItem(KEY)
    else sessionStorage.setItem(KEY, JSON.stringify(pending))
  } catch {
    // Storage can be unavailable (private mode); the game still works without it.
  }
}
