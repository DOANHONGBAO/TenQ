// Pure display helpers. None of them decides game state: the server does.

// Day #1 of the daily challenge (display only).
export const LAUNCH_DATE = '2026-10-17'
const DAY_MS = 86_400_000

export function challengeNumber(gameDate: string): number {
  const days = Math.round((Date.parse(`${gameDate}T00:00:00Z`) - Date.parse(`${LAUNCH_DATE}T00:00:00Z`)) / DAY_MS)
  return Math.max(1, days + 1)
}

export function formatGameDate(gameDate: string): string {
  return new Date(`${gameDate}T00:00:00Z`).toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  })
}

export function formatCountdown(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  return [h, m, s].map((n) => String(n).padStart(2, '0')).join(':')
}

export function formatDuration(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h > 0) return `${String(h)}h ${String(m).padStart(2, '0')}m`
  return `${String(m)}:${String(s).padStart(2, '0')}`
}

export function previousDate(gameDate: string): string {
  return new Date(Date.parse(`${gameDate}T00:00:00Z`) - DAY_MS).toISOString().slice(0, 10)
}
