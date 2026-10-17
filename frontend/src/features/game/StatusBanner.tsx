import type { Notice } from '../../state/gameReducer'

export function StatusBanner({ notice, onDismiss }: { notice: Notice; onDismiss: () => void }) {
  return (
    <div className={`banner banner-${notice.tone}`} role={notice.tone === 'error' ? 'alert' : 'status'}>
      <p>{notice.message}</p>
      <button type="button" className="btn btn-link" onClick={onDismiss} aria-label="Dismiss message">
        ✕
      </button>
    </div>
  )
}
