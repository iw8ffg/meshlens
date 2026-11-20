export class ApiError extends Error {
  status: number
  retryAfter: number | null
  constructor(status: number, message: string, retryAfter: number | null = null) {
    super(message)
    this.status = status
    this.retryAfter = retryAfter
  }
}

export const AUTH_REQUIRED = 'auth-required'

export function emitAuthRequired(): void {
  window.dispatchEvent(new CustomEvent(AUTH_REQUIRED))
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, credentials: 'same-origin' }
  if (body !== undefined) {
    init.headers = { 'Content-Type': 'application/json' }
    init.body = JSON.stringify(body)
  }
  const res = await fetch('/api' + path, init)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const j = await res.json()
      if (typeof j?.detail === 'string') detail = j.detail
    } catch {
      /* corpo non JSON */
    }
    const ra = res.headers.get('Retry-After')
    const retryAfter = ra !== null && ra !== '' && !Number.isNaN(Number(ra)) ? Number(ra) : null
    // 401 su /auth/login significa PIN errato, non sessione scaduta
    if (res.status === 401 && path !== '/auth/login') emitAuthRequired()
    throw new ApiError(res.status, detail, retryAfter)
  }
  if (res.status === 204) return undefined as T
  const text = await res.text()
  return (text ? JSON.parse(text) : undefined) as T
}

export function getJSON<T>(path: string): Promise<T> {
  return request<T>('GET', path)
}

export function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  return request<T>(method, path, body)
}
