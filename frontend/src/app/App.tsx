import { useBackendHealth } from '../features/health/useBackendHealth'

const STATUS_LABEL = {
  checking: 'Checking backend…',
  online: 'Backend online',
  offline: 'Backend offline',
} as const

export function App() {
  const status = useBackendHealth()

  return (
    <main className="page">
      <h1>TenQ.ai</h1>
      <p className="tagline">One secret a day. Ten questions. Can you deduce it?</p>
      <p className={`status status-${status}`} role="status">
        {STATUS_LABEL[status]}
      </p>
    </main>
  )
}
