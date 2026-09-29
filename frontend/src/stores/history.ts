import { ref, watch } from 'vue'
import { auth } from './auth'
import type { Question } from '../types'

export interface Visit { id: number; title: string; visitedAt: string }
const key = () => `qa_visits:${encodeURIComponent(auth.state.username)}`
const visits = ref<Visit[]>([])
function restore() {
  visits.value = []
  if (!auth.isAuthenticated.value || !auth.state.username) return
  try {
    const data: unknown = JSON.parse(localStorage.getItem(key()) ?? '[]')
    if (Array.isArray(data)) visits.value = data.filter((item): item is Visit =>
      item && Number.isSafeInteger(item.id) && item.id > 0 && typeof item.title === 'string' &&
      typeof item.visitedAt === 'string' && Number.isFinite(Date.parse(item.visitedAt)),
    ).slice(0, 30)
  } catch { /* History is optional when storage is unavailable. */ }
}
function persist() {
  try { localStorage.setItem(key(), JSON.stringify(visits.value)) } catch { /* Keep in memory. */ }
}
function record(question: Question) {
  if (!auth.isAuthenticated.value || !auth.state.username) return
  visits.value = [{ id: question.id, title: question.title, visitedAt: new Date().toISOString() }, ...visits.value.filter(item => item.id !== question.id)].slice(0, 30)
  persist()
}
function remove(id: number) { visits.value = visits.value.filter(item => item.id !== id); persist() }
function clear() { visits.value = []; persist() }
watch(() => auth.state.username, restore, { immediate: true, flush: 'sync' })
export const history = { visits, record, remove, clear }
