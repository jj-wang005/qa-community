<script setup lang="ts">
import { ArrowLeft, Check, Eye, Heart, MessageSquare, Send } from 'lucide-vue-next'
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/client'
import { auth } from '../stores/auth'
import type { Answer, Question } from '../types'
import EmptyState from '../components/EmptyState.vue'

const route = useRoute(); const router = useRouter(); const id = Number(route.params.id)
const question = ref<Question | null>(null); const answers = ref<Answer[]>([])
const answerText = ref(''); const error = ref(''); const loading = ref(true); const submitting = ref(false)
const likingIds = reactive(new Set<number>())
const formatDate = (value: string) => new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium' }).format(new Date(value))

async function load() {
  loading.value = true; error.value = ''
  try { [question.value, answers.value] = await Promise.all([api<Question>(`/api/v1/questions/${id}`), api<Answer[]>(`/api/v1/questions/${id}/answers?sort=hot&page=1&size=50`)]) }
  catch (err) { error.value = err instanceof Error ? err.message : '内容加载失败' }
  finally { loading.value = false }
}
async function requireLogin() { if (!auth.isAuthenticated.value) { await router.push('/login'); return false } return true }
async function submitAnswer() {
  if (!await requireLogin()) return
  submitting.value = true
  try {
    const created = await api<Answer>(`/api/v1/questions/${id}/answers`, { method: 'POST', body: JSON.stringify({ content: answerText.value }) })
    answerText.value = ''
    answers.value.unshift(created)
    if (question.value) question.value.answer_count += 1
  }
  catch (err) { error.value = err instanceof Error ? err.message : '回答发布失败' }
  finally { submitting.value = false }
}
async function toggleLike(answer: Answer) {
  if (!await requireLogin() || likingIds.has(answer.id)) return
  likingIds.add(answer.id); error.value = ''
  try {
    const result = await api<{ '点赞数量': number }>(`/api/v1/like/${answer.id}`, { method: answer.is_liked ? 'DELETE' : 'POST' })
    answer.is_liked = !answer.is_liked
    answer.like_count = result['点赞数量']
  } catch (err) { error.value = err instanceof Error ? err.message : (answer.is_liked ? '取消点赞失败' : '点赞失败') }
  finally { likingIds.delete(answer.id) }
}
async function accept(answer: Answer) {
  if (!await requireLogin()) return
  try { await api(`/api/v1/answers/${answer.id}/accept`, { method: 'POST' }); answer.is_accepted = true }
  catch (err) { error.value = err instanceof Error ? err.message : '采纳失败' }
}
onMounted(load)
</script>

<template>
  <button class="back-link" @click="router.back()"><ArrowLeft :size="17" />返回问题列表</button>
  <p v-if="error" class="notice error" role="alert">{{ error }}</p>
  <div v-if="loading" class="detail-loading skeleton" />
  <template v-else-if="question">
    <article class="question-detail"><div class="detail-kicker"><span>问题 #{{ question.id }}</span><span>{{ formatDate(question.created_at) }}</span></div><h1>{{ question.title }}</h1><p>{{ question.content }}</p><footer><span>由 {{ question.author_name }} 发布</span><span><Eye :size="16" />{{ question.view_count }} 次浏览</span><span><MessageSquare :size="16" />{{ question.answer_count }} 个回答</span></footer></article>
    <section class="answers-section"><div class="section-title"><div><p class="eyebrow">社区回答</p><h2>{{ answers.length }} 条讨论</h2></div></div>
      <EmptyState v-if="!answers.length" title="还没有回答" description="分享你的处理方式，帮助后来遇到相同问题的人。" />
      <article v-for="answer in answers" :key="answer.id" :class="['answer-card', { accepted: answer.is_accepted }]">
        <div class="answer-author"><span class="avatar">{{ answer.author_name.slice(0, 1).toUpperCase() }}</span><span><strong>{{ answer.author_name }}</strong><small>{{ formatDate(answer.created_at) }}</small></span><span v-if="answer.is_accepted" class="accepted-label"><Check :size="15" />已采纳</span></div>
        <p>{{ answer.content }}</p>
        <footer><button :class="{ liked: answer.is_liked }" :aria-pressed="answer.is_liked" :disabled="likingIds.has(answer.id)" @click="toggleLike(answer)"><Heart :size="16" :fill="answer.is_liked ? 'currentColor' : 'none'" />{{ answer.is_liked ? '已点赞' : '有帮助' }} {{ answer.like_count }}</button><button v-if="!answer.is_accepted" @click="accept(answer)"><Check :size="16" />采纳回答</button><span>回答 ID {{ answer.id }}</span></footer>
      </article>
    </section>
    <form class="answer-composer" @submit.prevent="submitAnswer"><div><p class="eyebrow">补充你的经验</p><h2>写下一个可执行的回答</h2></div><textarea v-model.trim="answerText" maxlength="1000" required rows="5" placeholder="说清楚你的判断、操作步骤和适用边界…"></textarea><div><small>{{ answerText.length }} / 1000</small><button class="primary-button" :disabled="submitting"><Send :size="17" />{{ submitting ? '发布中…' : '发布回答' }}</button></div></form>
  </template>
</template>
