<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowUpRight, Clock3, MessageSquare, PenLine, RefreshCw, UserRound } from 'lucide-vue-next'
import { api } from '../api/client'
import { auth } from '../stores/auth'
import { history } from '../stores/history'
import type { Question } from '../types'
import MyAnswers from '../components/MyAnswers.vue'
import EmptyState from '../components/EmptyState.vue'

const route = useRoute()
const tab = computed(() => route.query.tab === 'history' ? 'history' : route.query.tab === 'answers' ? 'answers' : 'questions')
const questions = ref<Question[]>([])
const loading = ref(false)
const error = ref('')
const reachedEnd = ref(false)
const checked = ref(0)
let nextPage = 1
let controller: AbortController | null = null
const date = (value: string) => new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium' }).format(new Date(value))

// The existing public endpoint has no author filter: scan bounded batches,
// deduplicate by ID, and never present a partial count as a lifetime total.
async function loadMine(reset = false) {
  if (loading.value && !reset) return
  controller?.abort()
  const request = new AbortController()
  controller = request
  const username = auth.state.username
  if (reset) { questions.value = []; nextPage = 1; checked.value = 0; reachedEnd.value = false }
  if (!username) return
  loading.value = true; error.value = ''
  try {
    for (let batch = 0; batch < 5 && !reachedEnd.value; batch++) {
      const rows = await api<Question[]>(`/api/v1/questions?sort=new&page=${nextPage}&size=100`, { signal: AbortSignal.any([request.signal, AbortSignal.timeout(30000)]) })
      if (request.signal.aborted || username !== auth.state.username) return
      const merged = new Map(questions.value.map(item => [item.id, item]))
      rows.filter(item => item.author_name === username).forEach(item => merged.set(item.id, item))
      questions.value = [...merged.values()].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at) || b.id - a.id)
      checked.value += rows.length; nextPage++; reachedEnd.value = rows.length < 100
    }
  } catch (err) {
    if (!request.signal.aborted) error.value = err instanceof Error ? err.message : '提问加载失败，请重试'
  } finally { if (controller === request) loading.value = false }
}
watch(() => auth.state.username, () => loadMine(true), { immediate: true })
onBeforeUnmount(() => controller?.abort())
</script>

<template>
  <section class="profile-hero">
    <div class="profile-avatar" aria-hidden="true">{{ auth.state.username.slice(0, 1).toUpperCase() || 'Q' }}</div>
    <div class="profile-identity"><p class="eyebrow">我的社区空间</p><h1>{{ auth.state.username }}</h1><p>记录你的提问与回答，回到值得继续的讨论。</p><span class="profile-status"><UserRound :size="14" />已登录</span></div>
    <RouterLink class="primary-button" to="/questions?compose=1"><PenLine :size="17" />发布新问题</RouterLink>
  </section>

  <div class="profile-layout">
    <aside class="profile-sidebar">
      <h2>个人中心</h2>
      <RouterLink :class="{ selected: tab === 'questions' }" :aria-current="tab === 'questions' ? 'page' : undefined" to="/profile"><MessageSquare :size="18" />我的提问</RouterLink>
      <RouterLink :class="{ selected: tab === 'answers' }" :aria-current="tab === 'answers' ? 'page' : undefined" to="/profile?tab=answers"><PenLine :size="18" />我的回答</RouterLink>
      <RouterLink :class="{ selected: tab === 'history' }" :aria-current="tab === 'history' ? 'page' : undefined" to="/profile?tab=history"><Clock3 :size="18" />最近浏览</RouterLink>
      <p>每一次提问，<br>都是知识积累的开始。</p>
    </aside>
    <section class="profile-content">
      <template v-if="tab === 'questions'">
        <header class="profile-section-heading"><div><h2>我的提问</h2><p>已找到 {{ questions.length }} 个提问</p></div><button class="secondary-button" :disabled="loading" @click="loadMine(true)"><RefreshCw :size="16" />刷新</button></header>
        <p v-if="error" class="notice error" role="alert">{{ error }} <button @click="loadMine()">重试</button></p>
        <p v-if="loading" class="muted" role="status">正在查找你的提问…</p>
        <EmptyState v-if="!loading && !error && !questions.length" :title="reachedEnd ? '还没有找到你的提问' : '暂未找到你的提问'" :description="reachedEnd ? '把遇到的问题写下来，让社区一起帮你解答。' : '可以继续查找更早的提问。'" />
        <RouterLink v-for="question in questions" :key="question.id" class="profile-question" :to="{ path: `/questions/${question.id}`, query: { from: '/profile' } }"><div><h3>{{ question.title }}</h3><p>{{ question.content }}</p><small>{{ date(question.created_at) }} · {{ question.answer_count }} 个回答 · {{ question.view_count }} 次浏览</small></div><ArrowUpRight :size="20" /></RouterLink>
        <div v-if="!reachedEnd && !loading && !error" class="profile-more"><p>已查阅最近 {{ checked }} 条社区问题，还可以查找更早的提问。</p><button class="secondary-button" @click="loadMine()">继续查找</button></div>
      </template>
      <MyAnswers v-else-if="tab === 'answers'" />
      <template v-else>
        <header class="profile-section-heading"><div><h2>最近浏览</h2><p>仅保存在此浏览器，按账户区分，最多保留 30 条。</p></div><button v-if="history.visits.value.length" class="text-button" @click="history.clear">清空记录</button></header>
        <EmptyState v-if="!history.visits.value.length" title="还没有浏览记录" description="登录后打开问题详情，就可以在这里找到它。" />
        <RouterLink v-for="item in history.visits.value" :key="item.id" class="profile-question" :to="{ path: `/questions/${item.id}`, query: { from: '/profile?tab=history' } }"><div><h3>{{ item.title }}</h3><small>{{ date(item.visitedAt) }} 浏览</small></div><ArrowUpRight :size="20" /></RouterLink>
      </template>
    </section>
  </div>
</template>
