<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { ArrowUpRight, Check, RefreshCw } from 'lucide-vue-next'
import { api } from '../api/client'
import { auth } from '../stores/auth'
import type { Answer, Question } from '../types'
import EmptyState from './EmptyState.vue'

type MyAnswer = Answer & { questionTitle: string; answerPage: number }
const answers = ref<MyAnswer[]>([])
const loading = ref(false)
const error = ref('')
const finished = ref(false)
const checked = ref(0)
let questionPage = 1
let queue: Question[] = []
let questionIndex = 0
let answerPage = 1
let lastQuestions = false
let controller: AbortController | null = null
const date = (value: string) => new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium' }).format(new Date(value))

// No user-answer endpoint exists. Keep resumable cursors and cap each batch
// at 30 requests, including nested answer pages; never imply partial totals.
async function load(reset = false) {
  if (loading.value && !reset) return
  controller?.abort()
  const request = new AbortController()
  controller = request
  if (reset) {
    answers.value = []; finished.value = false; checked.value = 0
    questionPage = 1; queue = []; questionIndex = 0; answerPage = 1; lastQuestions = false
  }
  const username = auth.state.username
  if (!username) { loading.value = false; return }
  loading.value = true; error.value = ''
  try {
    for (let budget = 0; budget < 30 && !finished.value; budget++) {
      const init = { signal: AbortSignal.any([request.signal, AbortSignal.timeout(30000)]) }
      if (questionIndex >= queue.length) {
        if (lastQuestions) { finished.value = true; break }
        const rows = await api<Question[]>(`/api/v1/questions?sort=new&page=${questionPage}&size=100`, init)
        if (request.signal.aborted || username !== auth.state.username) return
        queue = rows; questionIndex = 0; questionPage++; lastQuestions = rows.length < 100
        continue
      }
      const question = queue[questionIndex]!
      const rows = await api<Answer[]>(`/api/v1/questions/${question.id}/answers?sort=new&page=${answerPage}&size=100`, init)
      if (request.signal.aborted || username !== auth.state.username) return
      const merged = new Map(answers.value.map(item => [item.id, item]))
      rows.forEach((item, index) => {
        if (item.author_name === username) merged.set(item.id, { ...item, questionTitle: question.title, answerPage: Math.floor(((answerPage - 1) * 100 + index) / 20) + 1 })
      })
      answers.value = [...merged.values()].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at) || b.id - a.id)
      if (rows.length < 100) { questionIndex++; answerPage = 1; checked.value++ }
      else answerPage++
    }
    if (lastQuestions && questionIndex >= queue.length) finished.value = true
  } catch (err) {
    if (!request.signal.aborted) error.value = err instanceof Error ? err.message : '回答加载失败'
  } finally { if (controller === request) loading.value = false }
}
watch(() => auth.state.username, () => load(true), { immediate: true })
onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <header class="profile-section-heading"><div><h2>我的回答</h2><p>已找到 {{ answers.length }} 条回答</p></div><button class="secondary-button" :disabled="loading" @click="load(true)"><RefreshCw :size="16" />刷新</button></header>
  <p v-if="loading" class="muted" role="status">正在查找你的回答…已查阅 {{ checked }} 个问题</p>
  <p v-if="error" class="notice error" role="alert">{{ error }} <button @click="load()">重试</button></p>
  <EmptyState v-if="!loading && !error && !answers.length" :title="finished ? '还没有找到你的回答' : '暂未找到你的回答'" :description="finished ? '分享你的经验，帮助社区里的其他人。' : '可以继续查找其他问题下的回答。'" />
  <article v-for="answer in answers" :key="answer.id" class="profile-answer">
    <RouterLink class="profile-answer-title" :to="{ path: `/questions/${answer.question_id}`, query: { from: '/profile?tab=answers', answerPage: answer.answerPage, answer: answer.id } }"><h3>{{ answer.questionTitle }}</h3><ArrowUpRight :size="18" /></RouterLink>
    <p class="profile-answer-body">{{ answer.content }}</p>
    <footer><time>{{ date(answer.created_at) }}</time><span>{{ answer.like_count }} 人觉得有帮助</span><span v-if="answer.is_accepted" class="accepted-label"><Check :size="15" />已采纳</span><span v-else>未采纳</span></footer>
  </article>
  <div v-if="!finished && !loading && !error" class="profile-more"><p>已查阅 {{ checked }} 个问题，当前显示已找到的回答。</p><button class="secondary-button" @click="load()">继续查找</button></div>
</template>
