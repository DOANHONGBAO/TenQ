// Required disclosure for Cloudflare Turnstile in invisible mode: the check runs without a
// visible widget, so visitors must be told that it happens and which policies apply.
export function PrivacyNotice() {
  return (
    <footer className="privacy">
      <p>
        No account or personal profile is created. An anonymous, signed cookie keeps your game
        for the day. This site is protected by Cloudflare Turnstile to keep bots out; the Cloudflare{' '}
        <a href="https://www.cloudflare.com/privacypolicy/" target="_blank" rel="noreferrer">
          Privacy Policy
        </a>{' '}
        and{' '}
        <a href="https://www.cloudflare.com/website-terms/" target="_blank" rel="noreferrer">
          Terms of Service
        </a>{' '}
        apply. <a href="/privacy.html">How TenQ uses data</a>
      </p>
    </footer>
  )
}
