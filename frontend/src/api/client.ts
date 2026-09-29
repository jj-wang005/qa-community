import { auth } from '../stores/auth'

interface ValidationIssue { msg: string; loc?: Array<string | number> }
interface ApiErrorBody { message?: string; detail?: string | ValidationIssue[]; errors?: ValidationIssue[] }

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function parseError(response: Response) {
  const body = await response.json().catch(() => ({})) as ApiErrorBody
  const issues = body.errors ?? (Array.isArray(body.detail) ? body.detail : undefined)
  if (issues?.length) {
    const labels: Record<string, string> = { title: '标题', content: '内容', username: '用户名', password: '密码', question: '问题' }
    return issues.map(issue => {
      const field = String(issue.loc?.at(-1) ?? '')
      return `${labels[field] ?? field}${field ? '：' : ''}${issue.msg}`
    }).join('；')
  }
  return body.message ?? (Array.isArray(body.detail) ? body.detail.map(item => item.msg).join('；') : body.detail) ?? (response.status >= 500 ? '服务暂时不可用，请稍后重试。' : `请求失败（${response.status}）`)
}

let refreshing: Promise<boolean> | null = null
function refreshAccessToken(): Promise<boolean> {
  if (!refreshing) refreshing = performRefresh().finally(() => { refreshing = null })
  return refreshing
}
async function performRefresh() {
  const token = auth.state.refreshToken
  if (!auth.state.refreshToken) return false
  const response = await fetch('/api/v1/auth/refresh', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: token }), signal: AbortSignal.timeout(15000),
  })
  if (auth.state.refreshToken !== token) return false
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) { auth.clearAuth(); return false }
    throw new ApiError(await parseError(response), response.status)
  }
  const data = await response.json()
  if (auth.state.refreshToken !== token) return false
  auth.saveTokens(data.access_token, data.refresh_token)
  return true
}

export async function api<T>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const token = auth.state.accessToken
  const anonymous = /\/auth\/(login|register)$/.test(path)
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  if (token && !anonymous) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(path, { ...init, headers, signal: init.signal ?? AbortSignal.timeout(30000) })
  if (response.status === 401 && !anonymous && retry && ((token !== auth.state.accessToken && auth.state.accessToken) || await refreshAccessToken())) return api<T>(path, init, false)
  if (!response.ok) {
    if (response.status === 401 && !anonymous && auth.state.accessToken === token) auth.clearAuth()
    throw new ApiError(await parseError(response), response.status)
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>
}

export async function openEventStream(path: string, body: unknown, onEvent: (event: string, data: string) => void, signal?: AbortSignal, retry = true): Promise<void> {
  const token = auth.state.accessToken
  const headers = new Headers({ 'Content-Type': 'application/json' })
  if (auth.state.accessToken) headers.set('Authorization', `Bearer ${auth.state.accessToken}`)
  const response = await fetch(path, { method: 'POST', headers, body: JSON.stringify(body), signal })
  if (response.status === 401 && retry && ((token !== auth.state.accessToken && auth.state.accessToken) || await refreshAccessToken())) {
    return openEventStream(path, body, onEvent, signal, false)
  }
  if (!response.ok) throw new ApiError(await parseError(response), response.status)
  if (!response.body) throw new Error('浏览器没有收到事件流')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try { while (true) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const blocks = buffer.split(/\r?\n\r?\n/)
    buffer = blocks.pop() ?? ''
    if (done && buffer.trim()) { blocks.push(buffer); buffer = '' }
    for (const block of blocks) {
      let event = 'message'
      const data: string[] = []
      for (const line of block.split(/\r?\n/)) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
      }
      if (data.length) onEvent(event, data.join('\n'))
    }
    if (done) break
  } } finally { reader.releaseLock() }
}
