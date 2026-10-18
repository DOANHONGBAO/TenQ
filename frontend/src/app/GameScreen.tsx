import { useState } from 'react'

import type { Api } from '../api/client'
import { WinCelebration } from '../features/celebration/WinCelebration'
import { AttemptsMeter } from '../features/game/AttemptsMeter'
import { Feedback } from '../features/game/Feedback'
import { GameHeader } from '../features/game/GameHeader'
import { GuessForm } from '../features/game/GuessForm'
import { HintsPanel } from '../features/game/HintsPanel'
import { HistoryList } from '../features/game/HistoryList'
import { QuestionForm } from '../features/game/QuestionForm'
import { ResultPanel } from '../features/game/ResultPanel'
import { StatusBanner } from '../features/game/StatusBanner'
import { YesterdayAnswer } from '../features/game/YesterdayAnswer'
import { LeaderboardPanel } from '../features/leaderboard/LeaderboardPanel'
import { isFinished } from '../state/gameReducer'
import { useGame } from '../state/GameContext'
import { PrivacyNotice } from './PrivacyNotice'

export function GameScreen({ client }: { client: Api }) {
  const { state, dismissNotice, refresh } = useGame()
  const game = state.game
  const [dialog, setDialog] = useState<'celebrate' | 'name' | null>(null)
  const [playerName, setPlayerName] = useState<string | null>(null)

  // Celebrate only a win that just happened here, not a finished game loaded on a later visit.
  // (State adjusted during render when a new answer arrives, as React recommends over an effect.)
  const last = state.lastAnswer
  const [seenLast, setSeenLast] = useState(last)
  if (last !== seenLast) {
    setSeenLast(last)
    if (last?.answer === 'WIN') setDialog('celebrate')
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#play">
        Skip to the game
      </a>
      <GameHeader />
      <main id="play" className="layout" tabIndex={-1}>
        {state.notice && <StatusBanner notice={state.notice} onDismiss={dismissNotice} />}

        {state.phase === 'booting' && (
          <section className="card loading" aria-busy="true" aria-live="polite">
            <span className="spinner" aria-hidden="true" /> Preparing today’s challenge…
          </section>
        )}

        {(state.phase === 'maintenance' || state.phase === 'error') && !game && (
          <section className="card maintenance" aria-labelledby="maint-title">
            <h2 id="maint-title">
              {state.phase === 'maintenance' ? 'We’ll be right back' : 'Something went wrong'}
            </h2>
            <p>
              {state.phase === 'maintenance'
                ? 'TenQ is temporarily unavailable. Your progress is saved on our server; we will reconnect automatically.'
                : 'We could not start your game. Please check your connection and try again.'}
            </p>
            <button type="button" className="btn btn-primary" onClick={() => void refresh()}>
              Try again
            </button>
          </section>
        )}

        {game && (
          <>
            <div className="play-column">
              <AttemptsMeter game={game} />
              {isFinished(game) ? (
                <ResultPanel
                  game={game}
                  playerName={playerName}
                  onChooseName={() => {
                    setDialog('name')
                  }}
                />
              ) : (
                <>
                  <QuestionForm />
                  <Feedback last={state.lastAnswer} />
                  <GuessForm />
                </>
              )}
              <HintsPanel game={game} />
              <HistoryList history={game.history} />
            </div>
            <aside className="side-column">
              <LeaderboardPanel
                client={client}
                trigger={`${game.game_date}:${game.status}:${playerName ?? ''}`}
              />
              <YesterdayAnswer key={game.game_date} client={client} gameDate={game.game_date} />
            </aside>
          </>
        )}
      </main>
      <PrivacyNotice />
      {game && dialog !== null && (
        <WinCelebration
          client={client}
          game={game}
          mode={dialog}
          onClose={() => {
            setDialog(null)
            document.getElementById('result-title')?.focus()
          }}
          onNameSaved={setPlayerName}
        />
      )}
    </div>
  )
}
