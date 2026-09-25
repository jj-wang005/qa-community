<script setup lang="ts">
import { ArrowUpRight, Eye, MessageSquare, PenLine, RefreshCw, Sparkles, X } from 'lucide-vue-next'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import { auth } from '../stores/auth'
import type { Question } from '../types'
import EmptyState from '../components/EmptyState.vue'

const router = useRouter()
const questions = ref<Question[]>([])
const sort = ref<'hot' | 'new'>('hot')
const loading = ref(true)
const error = ref('')
const composeOpen = ref(false)
const title = ref('')
const content = ref('')
const publishing = ref(false)

const formatDate = (value: string) => new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric' }).format(new Date(value))

async function loadQuestions() {
  loading.value = true; error.value = ''
  try { questions.value = await api<Question[]>(`/api/v1/questions?sort=${sort.value}&page=1&size=20`) }
  catch (err) { error.value = err instanceof Error ? err.message : '问题列表加载失败' }
  finally { loading.value = false }
}

async function publish() {
  if (!auth.isAuthenticated.value) return router.push('/login')
  publishing.value = true; error.value = ''
  try {
    await api('/api/v1/questions', { method: 'POST', body: JSON.stringify({ title: title.value, content: content.value }) })
    title.value = ''; content.value = ''; composeOpen.value = false; sort.value = 'new'; await loadQuestions()
  } catch (err) { error.value = err instanceof Error ? err.message : '发布失败' }
  finally { publishing.value = false }
}

onMounted(loadQuestions)
</script>

<template>
  <section class="community-hero">
    <div><p class="eyebrow">真实讨论 · 可追溯回答</p><h1>社区里正在讨论什么？</h1><p>浏览开发问题，补充你的经验，或者让 AI 从已有讨论中整理答案。</p></div>
    <RouterLink class="agent-invite" to="/assistant"><Sparkles :size="20" /><span><small>不知道从哪里开始？</small><strong>问问社区 AI</strong></span><ArrowUpRight :size="19" /></RouterLink>
  </section>

  <section class="section-toolbar">
    <div class="segmented" aria-label="问题排序"><button :class="{ active: sort === 'hot' }" @click="sort = 'hot'; loadQuestions()">热门讨论</button><button :class="{ active: sort === 'new' }" @click="sort = 'new'; loadQuestions()">最新发布</button></div>
    <button class="primary-button" @click="auth.isAuthenticated.value ? composeOpen = true : router.push('/login')"><PenLine :size="17" />发布问题</button>
  </section>

  <p v-if="error" class="notice error" role="alert">{{ error }} <button @click="loadQuestions"><RefreshCw :size="15" />重试</button></p>
  <div v-if="loading" class="question-list" aria-label="正在加载"><div v-for="n in 4" :key="n" class="question-card skeleton" /></div>
  <EmptyState v-else-if="!questions.length" title="这里还没有问题" description="发布第一个问题，给社区一个讨论的起点。" />
  <div v-else class="question-list">
    <RouterLink v-for="(question, index) in questions" :key="question.id" class="question-card" :to="`/questions/${question.id}`">
      <span class="question-index">{{ String(index + 1).padStart(2, '0') }}</span>
      <div class="question-body"><div class="question-meta"><span>{{ question.author_name }}</span><time>{{ formatDate(question.created_at) }}</time></div><h2>{{ question.title }}</h2><p>{{ question.content }}</p></div>
      <div class="question-stats"><span><MessageSquare :size="16" />{{ question.answer_count }}</span><span><Eye :size="16" />{{ question.view_count }}</span><ArrowUpRight class="open-arrow" :size="20" /></div>
    </RouterLink>
  </div>

  <div v-if="composeOpen" class="modal-backdrop" @click.self="composeOpen = false">
    <form class="modal-card" @submit.prevent="publish"><div class="modal-heading"><div><p class="eyebrow">发起新讨论</p><h2>把问题描述清楚</h2></div><button type="button" class="icon-button" aria-label="关闭" @click="composeOpen = false"><X :size="20" /></button></div><label><span>问题标题</span><input v-model.trim="title" maxlength="200" required placeholder="一句话说明你遇到的问题"></label><label><span>问题详情</span><textarea v-model.trim="content" maxlength="1000" required rows="7" placeholder="补充背景、尝试过的方法和期望结果"></textarea><small>{{ content.length }} / 1000</small></label><button class="primary-button wide" :disabled="publishing">{{ publishing ? '正在发布…' : '发布问题' }}</button></form>
  </div>
</template>
