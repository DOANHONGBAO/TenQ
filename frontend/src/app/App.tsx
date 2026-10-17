import { api } from '../api/client'
import type { Api } from '../api/client'
import { turnstileTokenProvider } from '../features/session/session'
import type { TokenProvider } from '../features/session/session'
import { GameProvider } from '../state/GameProvider'
import { GameScreen } from './GameScreen'

interface Props {
  client?: Api
  getToken?: TokenProvider
}

export function App({ client = api, getToken = turnstileTokenProvider }: Props) {
  return (
    <GameProvider client={client} getToken={getToken}>
      <GameScreen client={client} />
    </GameProvider>
  )
}
