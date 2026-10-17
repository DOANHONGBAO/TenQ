// Only VITE_* variables reach the browser bundle. They must never hold secrets.
const rawBase: unknown = import.meta.env.VITE_API_BASE_URL

export const API_BASE_URL: string =
  typeof rawBase === 'string' && rawBase.length > 0 ? rawBase : '/api/v1'
