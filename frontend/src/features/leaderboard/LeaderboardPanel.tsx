import type { Api } from '../../api/client'
import { formatDuration } from '../../lib/format'
import { useLeaderboard } from '../../state/useLeaderboard'

export function LeaderboardPanel({ client, trigger }: { client: Api; trigger: string }) {
  const { board, failed } = useLeaderboard(client, trigger)

  return (
    <section className="card leaderboard" aria-labelledby="lb-title">
      <h2 id="lb-title">Today’s leaderboard</h2>
      {failed && !board && <p className="muted">The leaderboard is unavailable right now.</p>}
      {!failed && !board && <p className="muted">Loading…</p>}
      {board && board.entries.length === 0 && (
        <p className="muted">No winners yet today. Be the first!</p>
      )}
      {board && board.entries.length > 0 && (
        <table className="lb-table">
          <caption className="sr-only">
            Top players: fewer questions first, then faster time
          </caption>
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">Player</th>
              <th scope="col">Questions</th>
              <th scope="col">Time</th>
            </tr>
          </thead>
          <tbody>
            {board.entries.map((entry) => (
              <tr key={`${String(entry.rank)}-${entry.display_name}`}>
                <td>{entry.rank}</td>
                <td>{entry.display_name}</td>
                <td>{entry.questions}</td>
                <td>{formatDuration(entry.duration_ms)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {board?.me && (
        <p className="lb-me">
          You are <strong>#{board.me.rank}</strong> of {board.total_winners} winners today.
        </p>
      )}
      {board && board.total_winners > 0 && !board.me && (
        <p className="muted">{board.total_winners} winners so far today.</p>
      )}
    </section>
  )
}
