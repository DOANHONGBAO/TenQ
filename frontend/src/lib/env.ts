// Only VITE_* variables reach the browser bundle. They must never hold secrets.
const rawBase: unknown = import.meta.env.VITE_API_BASE_URL

export const API_BASE_URL: string =
  typeof rawBase === 'string' && rawBase.length > 0 ? rawBase : '/api/v1'

// Public Turnstile site key. Default: Cloudflare's official invisible test key (always passes).
const rawSiteKey: unknown = import.meta.env.VITE_TURNSTILE_SITE_KEY

export const TURNSTILE_SITE_KEY: string =
  typeof rawSiteKey === 'string' && rawSiteKey.length > 0 ? rawSiteKey : '1x00000000000000000000BB'
