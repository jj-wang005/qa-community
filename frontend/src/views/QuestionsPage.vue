<script setup lang="ts">
import { ArrowUpRight, Eye, MessageSquare, PenLine, RefreshCw, Sparkles, X } from 'lucide-vue-next'
import { computed, onMounted, onBeforeUnmount, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/client'
import { auth } from '../stores/auth'
import { drafts } from '../stores/drafts'
import type { Question } from '../types'
import EmptyState from '../components/EmptyState.vue'

const router = useRouter()
const route = useRoute()
const questions = ref<Question[]>([])
const sort = ref<'hot' | 'new'>(route.query.sort === 'new' ? 'new' : 'hot')
function readPage() { const value = Number(route.query.page); return Number.isSafeInteger(value) && value > 0 ? value : 1 }
const page = ref(readPage())
const hasMore = ref(false)
const publishError = ref('')
const success = ref('')
let requestId = 0
const modal = ref<HTMLFormElement | null>(null)
let previousFocus: HTMLElement | null = null
const loading = ref(true)
const error = ref('')
const composeOpen = ref(false)
const title = computed({ get: () => drafts.title, set: value => { drafts.title = value } })
const content = computed({ get: () => drafts.content, set: value => { drafts.content = value } })
const publishing = ref(false)

const formatDate = (value: string) => new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric' }).format(new Date(value))

watch(composeOpen, async (open) => {
  document.body.style.overflow = open ? 'hidden' : ''
  if (open) { previousFocus = document.activeElement as HTMLElement; await nextTick(); modal.value?.querySelector('input')?.focus() }
  else previousFocus?.focus()
})
function closeCompose() { if (!publishing.value) composeOpen.value = false }
function modalKey(event: KeyboardEvent) {
  if (event.key === 'Escape') closeCompose()
  if (event.key !== 'Tab') return
  const items = modal.value?.querySelectorAll<HTMLElement>('button:not(:disabled), input, textarea')
  if (!items?.length) return
  const first = items[0], last = items[items.length - 1]
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
}
onBeforeUnmount(() => { requestId++; document.body.style.overflow = '' })
async function loadQuestions() {
  const current = ++requestId
  loading.value = true; error.value = ''; questions.value = []
  try {
    const result = await api<Question[]>(`/api/v1/questions?sort=${sort.value}&page=${page.value}&size=20`)
    if (current !== requestId) return
    questions.value = result; hasMore.value = result.length === 20
  }
  catch (err) { if (current !== requestId) return; error.value = err instanceof Error ? err.message : '问题列表加载失败' }
  finally { if (current === requestId) loading.value = false }
}

async function changePage(next: number, order = sort.value) {
  await router.push({ path: '/questions', query: { sort: order, page: next } })
}
watch(() => route.query, () => {
  sort.value = route.query.sort === 'new' ? 'new' : 'hot'
  page.value = readPage(); loadQuestions()
})
async function publish() {
  if (publishing.value || !title.value.trim() || !content.value.trim()) return
  if (!auth.isAuthenticated.value) return router.push({ path: '/login', query: { redirect: route.fullPath } })
  publishing.value = true; publishError.value = ''
  try {
    await api('/api/v1/questions', { method: 'POST', body: JSON.stringify({ title: title.value, content: content.value }) })
    title.value = ''; content.value = ''; composeOpen.value = false; success.value = '问题已发布'
    if (page.value === 1 && sort.value === 'new') await loadQuestions()
    else await changePage(1, 'new')
  } catch (err) { publishError.value = err instanceof Error ? err.message : '发布失败' }
  finally { publishing.value = false }
}

onMounted(() => {
  loadQuestions()
  if (route.query.compose === '1' && auth.isAuthenticated.value) {
    composeOpen.value = true
    const query = { ...route.query }; delete query.compose
    router.replace({ path: route.path, query })
  }
})
</script>

<template>
  <section class="community-hero">
    <div><p class="eyebrow">真实讨论 · 可追溯回答</p><h1>社区里正在讨论什么？</h1><p>浏览开发问题，补充你的经验，或者让 AI 从已有讨论中整理答案。</p></div>
    <RouterLink class="agent-invite" to="/assistant"><Sparkles :size="20" /><span><small>不知道从哪里开始？</small><strong>问问社区 AI</strong></span><ArrowUpRight :size="19" /></RouterLink>
  </section>

  <section class="section-toolbar">
    <div class="segmented" aria-label="问题排序"><button :class="{ active: sort === 'hot' }" @click="changePage(1, 'hot')">热门讨论</button><button :class="{ active: sort === 'new' }" @click="changePage(1, 'new')">最新发布</button></div>
    <button class="primary-button" @click="auth.isAuthenticated.value ? composeOpen = true : router.push({ path: '/login', query: { redirect: route.fullPath } })"><PenLine :size="17" />发布问题</button>
  </section>

  <p v-if="success" class="notice success" role="status">{{ success }}</p>
  <p v-if="error" class="notice error" role="alert">{{ error }} <button @click="loadQuestions"><RefreshCw :size="15" />重试</button></p>
  <div v-if="loading" class="question-list" aria-label="正在加载"><div v-for="n in 4" :key="n" class="question-card skeleton" /></div>
  <EmptyState v-else-if="!error && !questions.length" :title="page > 1 ? '这一页没有更多问题' : '这里还没有问题'" description="发布第一个问题，给社区一个讨论的起点。" />
  <div v-else class="question-list">
    <RouterLink v-for="(question, index) in questions" :key="question.id" class="question-card" :to="{ path: `/questions/${question.id}`, query: { from: route.fullPath } }">
      <span class="question-index">{{ String((page - 1) * 20 + index + 1).padStart(2, '0') }}</span>
      <div class="question-body"><div class="question-meta"><span>{{ question.author_name }}</span><time>{{ formatDate(question.created_at) }}</time></div><h2>{{ question.title }}</h2><p>{{ question.content }}</p></div>
      <div class="question-stats"><span><MessageSquare :size="16" />{{ question.answer_count }}</span><span><Eye :size="16" />{{ question.view_count }}</span><ArrowUpRight class="open-arrow" :size="20" /></div>
    </RouterLink>
  </div>

  <nav class="pagination" aria-label="问题分页"><button class="secondary-button" :disabled="loading || page === 1" @click="changePage(page - 1)">上一页</button><span>第 {{ page }} 页</span><button class="secondary-button" :disabled="loading || !hasMore || !!error" @click="changePage(page + 1)">下一页</button></nav>
  <div v-if="composeOpen" class="modal-backdrop" @click.self="closeCompose" @keydown="modalKey">
    <form ref="modal" class="modal-card" role="dialog" aria-modal="true" aria-label="发布问题" @submit.prevent="publish"><div class="modal-heading"><div><p class="eyebrow">发起新讨论</p><h2>把问题描述清楚</h2></div><button type="button" class="icon-button" aria-label="关闭" :disabled="publishing" @click="closeCompose"><X :size="20" /></button></div><label><span>问题标题</span><input v-model.trim="title" maxlength="200" required placeholder="一句话说明你遇到的问题"></label><label><span>问题详情</span><textarea v-model.trim="content" maxlength="1000" required rows="7" placeholder="补充背景、尝试过的方法和期望结果"></textarea><small>{{ content.length }} / 1000</small></label><p v-if="publishError" class="notice error" role="alert">{{ publishError }}</p><button class="primary-button wide" :disabled="publishing || !title.trim() || !content.trim()">{{ publishing ? '正在发布…' : '发布问题' }}</button></form>
  </div>
</template>
