import { useBackendHealth } from '../features/health/useBackendHealth'
import { useAnonymousSession } from '../features/session/useAnonymousSession'
import { PrivacyNotice } from './PrivacyNotice'

const STATUS_LABEL = {
  checking: 'Checking backend…',
  online: 'Backend online',
  offline: 'Backend offline',
} as const

const SESSION_LABEL = {
  checking: 'Starting anonymous session…',
  ready: 'Anonymous session ready',
  failed: 'Could not start a session. Please reload the page.',
} as const

export function App() {
  const status = useBackendHealth()
  const session = useAnonymousSession()

  return (
    <main className="page">
      <h1>TenQ.ai</h1>
      <p className="tagline">One secret a day. Ten questions. Can you deduce it?</p>
      <p className={`status status-${status}`} role="status">
        {STATUS_LABEL[status]}
      </p>
      <p className="status">{SESSION_LABEL[session]}</p>
      <PrivacyNotice />
    </main>
  )
}
