import type {
  Alert,
  CoverageCheck,
  CoverageDetail,
  CoverageSession,
  CoverageStartBody,
  ConfigBackup,
  ConfigJob,
  ConfigPreview,
  ConfigSaved,
  ConfigSchema,
  Link,
  Node,
  TelemetryPoint,
  Traceroute,
} from './types'

export class ApiError extends Error {
  status: number
  retryAfter: number | null
  code: string | null
  constructor(status: number, message: string, retryAfter: number | null = null, code: string | null = null) {
    super(message)
    this.status = status
    this.retryAfter = retryAfter
    this.code = code
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
    let code: string | null = null
    try {
      const j = await res.json()
      if (typeof j?.detail === 'string') detail = j.detail
      else if (typeof j?.detail?.message === 'string') detail = j.detail.message
      if (typeof j?.code === 'string') code = j.code
      else if (typeof j?.detail?.code === 'string') code = j.detail.code
    } catch {
      /* corpo non JSON */
    }
    const ra = res.headers.get('Retry-After')
    const retryAfter = ra !== null && ra !== '' && !Number.isNaN(Number(ra)) ? Number(ra) : null
    // 401 su /auth/login significa PIN errato, non sessione scaduta
    if (res.status === 401 && path !== '/auth/login') emitAuthRequired()
    throw new ApiError(res.status, detail, retryAfter, code)
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

const nodePath = (id: string) => `/nodes/${encodeURIComponent(id)}`

export const telemetry = (id: string, hours = 168) =>
  getJSON<TelemetryPoint[]>(`${nodePath(id)}/telemetry?hours=${hours}`)
export const setMine = (id: string, mine: boolean) => send<Node>('PUT', `${nodePath(id)}/mine`, { mine })
export const links = (hours = 24) => getJSON<Link[]>(`/links?hours=${hours}`)
export const alerts = () => getJSON<Alert[]>('/alerts')
export const traceroute = (id: string, radioId?: string) =>
  send<Traceroute>('POST', `${nodePath(id)}/traceroute`, radioId ? { radio_id: radioId } : {})
export const traceroutes = (id: string) => getJSON<Traceroute[]>(`${nodePath(id)}/traceroutes`)

export const coverageSessions = () => getJSON<CoverageSession[]>('/coverage/sessions')
export const coverageSession = (id: number) => getJSON<CoverageDetail>(`/coverage/sessions/${id}`)
export const startCoverage = (body: CoverageStartBody) => send<CoverageSession>('POST', '/coverage/sessions', body)
export const stopCoverage = (id: number) => send<CoverageSession>('POST', `/coverage/sessions/${id}/stop`)
export const patchCoverage = (id: number, body: { name?: string; notes?: string; base_lat?: number; base_lon?: number }) =>
  send<CoverageSession>('PATCH', `/coverage/sessions/${id}`, body)
export const deleteCoverage = (id: number) => send<void>('DELETE', `/coverage/sessions/${id}`)
export const coverageCheck = (radioId: string, mobileId: string) =>
  getJSON<CoverageCheck>(
    `/coverage/check?radio_id=${encodeURIComponent(radioId)}&mobile_id=${encodeURIComponent(mobileId)}`,
  )

const cfgPath = (id: string) => `/config/${encodeURIComponent(id)}`
export const configSchema = () => getJSON<ConfigSchema>('/config/schema')
export const radioAdminKey = (radioId: string) =>
  getJSON<{ public_key_b64: string }>(`/radios/${encodeURIComponent(radioId)}/admin-key`)
export const readConfig = (nodeId: string, body: { radio_id?: string; sections?: string[] } = {}) =>
  send<ConfigJob>('POST', `${cfgPath(nodeId)}/read`, body)
export const savedConfig = (nodeId: string) => getJSON<ConfigSaved>(cfgPath(nodeId))
export const previewConfig = (nodeId: string, changes: Record<string, unknown>) =>
  send<ConfigPreview>('POST', `${cfgPath(nodeId)}/preview`, { changes })
export const applyConfig = (nodeId: string, previewId: string, confirmRisky = false) =>
  send<ConfigJob>('POST', `${cfgPath(nodeId)}/apply`, { preview_id: previewId, confirm_risky: confirmRisky })
export const rebootNode = (nodeId: string, radioId?: string) =>
  send<ConfigJob>('POST', `${cfgPath(nodeId)}/reboot`, { radio_id: radioId, confirm: true })
export const setFixedPosition = (nodeId: string, body: { lat: number; lon: number; alt?: number } | { remove: true }) =>
  send<ConfigJob>('POST', `${cfgPath(nodeId)}/fixed-position`, { ...body, confirm: true })
export const configBackups = (nodeId: string) => getJSON<ConfigBackup[]>(`${cfgPath(nodeId)}/backups`)
export const configBackup = (id: number) => getJSON<ConfigBackup>(`/config/backups/${id}`)
export const previewRestore = (id: number) => send<ConfigPreview>('POST', `/config/backups/${id}/preview-restore`)
export const revealPsk = (nodeId: string, index: number) =>
  send<{ psk: string }>('POST', `${cfgPath(nodeId)}/channels/${index}/reveal-psk`)
export const configJob = (id: number) => getJSON<ConfigJob>(`/config/jobs/${id}`)
