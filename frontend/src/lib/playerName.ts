// The last leaderboard name this browser saved, only to prefill the form next time.
// The server stores the real value; this copy may be missing (private mode, cleared storage).

const KEY = 'tenq.playerName'

export function loadPlayerName(): string {
  try {
    return localStorage.getItem(KEY) ?? ''
  } catch {
    return ''
  }
}

export function savePlayerName(name: string): void {
  try {
    localStorage.setItem(KEY, name)
  } catch {
    // Storage can be unavailable; the name is still saved on the server.
  }
}
