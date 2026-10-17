import { API_BASE_URL } from './env'

export class HttpError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'HttpError'
    this.status = status
  }
}

/** GET a JSON resource from the API. Cookies are sent so the session works later. */
export async function getJson(path: string, signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'GET',
    credentials: 'include',
    headers: { Accept: 'application/json' },
    ...(signal ? { signal } : {}),
  })
  if (!response.ok) {
    throw new HttpError(response.status, `Request failed with status ${String(response.status)}`)
  }
  return response.json() as Promise<unknown>
}

/** POST JSON to the API and return the parsed body (credentials included for the cookie). */
export async function postJson(path: string, body: unknown): Promise<unknown> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    throw new HttpError(response.status, `Request failed with status ${String(response.status)}`)
  }
  return response.json() as Promise<unknown>
}
