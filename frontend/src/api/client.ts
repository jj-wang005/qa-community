import { auth } from '../stores/auth'

interface ApiErrorBody { message?: string; detail?: string }

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function parseError(response: Response) {
  const body = await response.json().catch(() => ({})) as ApiErrorBody
  return body.message ?? body.detail ?? `请求失败（${response.status}）`
}

async function refreshAccessToken() {
  if (!auth.state.refreshToken) return false
  const response = await fetch('/api/v1/auth/refresh', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: auth.state.refreshToken }),
  })
  if (!response.ok) { auth.clearAuth(); return false }
  const data = await response.json()
  auth.saveTokens(data.access_token, data.refresh_token)
  return true
}

export async function api<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  if (auth.state.accessToken) headers.set('Authorization', `Bearer ${auth.state.accessToken}`)
  const response = await fetch(path, { ...init, headers })
  if (response.status === 401 && retry && await refreshAccessToken()) return api<T>(path, init, false)
  if (!response.ok) throw new ApiError(await parseError(response), response.status)
  return response.json() as Promise<T>
}

export async function openEventStream(path: string, body: unknown, onEvent: (event: string, data: string) => void, retry = true): Promise<void> {
  const headers = new Headers({ 'Content-Type': 'application/json' })
  if (auth.state.accessToken) headers.set('Authorization', `Bearer ${auth.state.accessToken}`)
  const response = await fetch(path, { method: 'POST', headers, body: JSON.stringify(body) })
  if (response.status === 401 && retry && await refreshAccessToken()) {
    return openEventStream(path, body, onEvent, false)
  }
  if (!response.ok) throw new ApiError(await parseError(response), response.status)
  if (!response.body) throw new Error('浏览器没有收到事件流')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n')
    const blocks = buffer.split('\n\n')
    buffer = blocks.pop() ?? ''
    for (const block of blocks) {
      let event = 'message'
      const data: string[] = []
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
      }
      if (data.length) onEvent(event, data.join('\n'))
    }
    if (done) break
  }
}
