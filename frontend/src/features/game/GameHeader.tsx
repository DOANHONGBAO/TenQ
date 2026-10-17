import { Logo } from '../../components/Logo'
import { challengeNumber, formatCountdown, formatGameDate } from '../../lib/format'
import { useGame } from '../../state/GameContext'
import { useResetCountdown } from '../../state/useResetCountdown'

export function GameHeader() {
  const { state } = useGame()
  const remaining = useResetCountdown()
  const game = state.game

  return (
    <header className="site-header">
      <Logo />
      {game && (
        <div className="daily">
          <p className="daily-title">
            Daily Challenge <strong>#{challengeNumber(game.game_date)}</strong>
          </p>
          <p className="daily-date">
            <time dateTime={game.game_date}>{formatGameDate(game.game_date)}</time> · UTC
          </p>
        </div>
      )}
      {remaining !== null && (
        <p className="countdown">
          <span className="countdown-label">Next word in</span>
          <span className="countdown-value" role="timer" aria-live="off">
            {formatCountdown(remaining)}
          </span>
        </p>
      )}
    </header>
  )
}
