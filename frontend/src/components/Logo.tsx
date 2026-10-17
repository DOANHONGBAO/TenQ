export function Logo() {
  return (
    <span className="logo" aria-label="TenQ.ai">
      <svg className="logo-mark" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
        <rect x="1" y="1" width="30" height="30" rx="9" />
        <text x="16" y="21.5" textAnchor="middle">
          10
        </text>
      </svg>
      <span className="logo-text" aria-hidden="true">
        TenQ<span className="logo-dot">.ai</span>
      </span>
    </span>
  )
}
