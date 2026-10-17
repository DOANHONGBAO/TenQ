// Cloudflare Turnstile (invisible mode) loader and token helper.
// The site key is public; the secret key exists only on the backend.

const SCRIPT_URL = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
const TOKEN_TIMEOUT_MS = 30_000

interface TurnstileRenderOptions {
  sitekey: string
  action: string
  execution: 'render' | 'execute'
  appearance: 'always' | 'execute' | 'interaction-only'
  callback: (token: string) => void
  'error-callback': () => void
  'expired-callback': () => void
}

interface TurnstileApi {
  render: (container: HTMLElement, options: TurnstileRenderOptions) => string
  execute: (widgetId: string) => void
  reset: (widgetId: string) => void
}

declare global {
  interface Window {
    turnstile?: TurnstileApi
  }
}

let scriptPromise: Promise<TurnstileApi> | null = null

function loadScript(): Promise<TurnstileApi> {
  scriptPromise ??= new Promise<TurnstileApi>((resolve, reject) => {
    const script = document.createElement('script')
    script.src = SCRIPT_URL
    script.async = true
    script.onload = () => {
      if (window.turnstile) {
        resolve(window.turnstile)
      } else {
        reject(new Error('Turnstile did not initialise'))
      }
    }
    script.onerror = () => {
      scriptPromise = null
      reject(new Error('Turnstile script failed to load'))
    }
    document.head.appendChild(script)
  })
  return scriptPromise
}

/**
 * Obtain one fresh, single-use token. The widget is reset afterwards, so a later call
 * (for example after the cookie was cleared) always gets a new token instead of a spent one.
 */
export async function getTurnstileToken(siteKey: string, action: string): Promise<string> {
  const turnstile = await loadScript()
  const container = document.createElement('div')
  container.hidden = true
  document.body.appendChild(container)

  let widgetId = ''
  try {
    return await new Promise<string>((resolve, reject) => {
      const timer = window.setTimeout(() => {
        reject(new Error('Turnstile timed out'))
      }, TOKEN_TIMEOUT_MS)
      const done = (fn: () => void) => {
        window.clearTimeout(timer)
        fn()
      }
      widgetId = turnstile.render(container, {
        sitekey: siteKey,
        action,
        execution: 'execute',
        appearance: 'interaction-only',
        callback: (token) => {
          done(() => {
            resolve(token)
          })
        },
        'error-callback': () => {
          done(() => {
            reject(new Error('Turnstile error'))
          })
        },
        'expired-callback': () => {
          done(() => {
            reject(new Error('Turnstile token expired'))
          })
        },
      })
      turnstile.execute(widgetId)
    })
  } finally {
    if (widgetId) {
      turnstile.reset(widgetId)
    }
    container.remove()
  }
}
