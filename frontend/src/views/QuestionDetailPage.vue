<script setup lang="ts">
import { ArrowLeft, Check, Eye, Heart, MessageSquare, Send } from 'lucide-vue-next'
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/client'
import { auth } from '../stores/auth'
import { drafts } from '../stores/drafts'
import { history } from '../stores/history'
import type { Answer, Question } from '../types'
import EmptyState from '../components/EmptyState.vue'

const route = useRoute(); const router = useRouter(); const id = computed(() => Number(route.params.id))
const question = ref<Question | null>(null); const answers = ref<Answer[]>([])
const answerText = computed({ get: () => drafts.answers[String(id.value)] ?? '', set: value => { drafts.answers[String(id.value)] = value } }); const error = ref(''); const loading = ref(true); const submitting = ref(false)
const page = ref(1); const sort = ref('hot'); const hasMore = ref(false); const accepting = ref(false); const deleting = ref(false)
const canManage = computed(() => auth.isAuthenticated.value && question.value?.author_name === auth.state.username)
const answersLoading = ref(false)
const answersError = ref('')
const returnTo = computed(() => {
  const value = route.query.from
  return typeof value === 'string' && /^\/(?:questions|profile)(?:\?|$)/.test(value) ? value : '/questions'
})
let requestId = 0
let answersRequestId = 0
const likingIds = reactive(new Set<number>())
const formatDate = (value: string) => new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium' }).format(new Date(value))

async function load() {
  const current = ++requestId
  loading.value = true; error.value = ''
  try {
    if (!Number.isSafeInteger(id.value) || id.value < 1) throw new Error('问题地址无效')
    const detail = await api<Question>(`/api/v1/questions/${id.value}`)
    if (current !== requestId) return
    question.value = detail
    history.record(detail)
    await loadAnswers()
    loading.value = false
    await nextTick()
    if (current === requestId && route.query.answer) document.getElementById(`answer-${Number(route.query.answer)}`)?.scrollIntoView({ block: 'center' })
  }
  catch (err) { if (current === requestId) error.value = err instanceof Error ? err.message : '内容加载失败' }
  finally { if (current === requestId) loading.value = false }
}
async function loadAnswers() {
  const current = ++answersRequestId
  const questionId = id.value
  answersLoading.value = true; answersError.value = ''; answers.value = []
  try {
    const result = await api<Answer[]>(`/api/v1/questions/${questionId}/answers?sort=${sort.value}&page=${page.value}&size=20`)
    if (current !== answersRequestId || questionId !== id.value) return
    answers.value = result; hasMore.value = result.length === 20
  } catch (err) {
    if (current === answersRequestId) answersError.value = err instanceof Error ? err.message : '回答加载失败'
  } finally { if (current === answersRequestId) answersLoading.value = false }
}
async function requireLogin() { if (!auth.isAuthenticated.value) { await router.push({ path: '/login', query: { redirect: route.fullPath } }); return false } return true }
async function submitAnswer() {
  if (submitting.value || !answerText.value.trim() || !await requireLogin()) return
  error.value = ''
  submitting.value = true
  try {
    await api<Answer>(`/api/v1/questions/${id.value}/answers`, { method: 'POST', body: JSON.stringify({ content: answerText.value }) })
    answerText.value = ''
    if (question.value) question.value.answer_count += 1
    page.value = 1; sort.value = 'new'; await loadAnswers()
  }
  catch (err) { error.value = err instanceof Error ? err.message : '回答发布失败' }
  finally { submitting.value = false }
}
async function toggleLike(answer: Answer) {
  if (likingIds.has(answer.id) || !await requireLogin()) return
  likingIds.add(answer.id); error.value = ''
  try {
    const result = await api<{ '点赞数量': number }>(`/api/v1/like/${answer.id}`, { method: answer.is_liked ? 'DELETE' : 'POST' })
    answer.is_liked = !answer.is_liked
    answer.like_count = result['点赞数量']
  } catch (err) { error.value = err instanceof Error ? err.message : (answer.is_liked ? '取消点赞失败' : '点赞失败') }
  finally { likingIds.delete(answer.id) }
}
async function accept(answer: Answer) {
  if (accepting.value || !await requireLogin()) return
  accepting.value = true; error.value = ''
  try { await api(`/api/v1/answers/${answer.id}/accept`, { method: 'POST' }); answer.is_accepted = true }
  catch (err) { error.value = err instanceof Error ? err.message : '采纳失败' }
  finally { accepting.value = false }
}
async function remove(answer?: Answer) {
  if (deleting.value || !window.confirm(answer ? '确定删除这条回答？删除后无法恢复。' : '确定删除这个问题及其回答？删除后无法恢复。')) return
  deleting.value = true; error.value = ''
  try {
    await api(answer ? `/api/v1/answers/${answer.id}` : `/api/v1/questions/${id.value}`, { method: 'DELETE' })
    if (!answer) { history.remove(id.value); await router.replace(returnTo.value) }
    else {
      if (question.value) question.value.answer_count = Math.max(0, question.value.answer_count - 1)
      page.value = 1; await loadAnswers()
    }
  } catch (err) { error.value = err instanceof Error ? err.message : '删除失败' }
  finally { deleting.value = false }
}
watch(() => route.params.id, () => { question.value = null; answers.value = []; const targetPage = Number(route.query.answerPage); page.value = Number.isSafeInteger(targetPage) && targetPage > 0 ? targetPage : 1; sort.value = route.query.answer ? 'new' : 'hot'; load() }, { immediate: true })
watch(() => auth.state.username, () => { if (question.value) loadAnswers() })
onBeforeUnmount(() => { requestId++; answersRequestId++ })
</script>

<template>
  <button class="back-link" @click="router.push(returnTo)"><ArrowLeft :size="17" />{{ returnTo.startsWith('/profile') ? '返回个人中心' : '返回问题列表' }}</button>
  <p v-if="error" class="notice error" role="alert">{{ error }} <button @click="load">重新加载</button><RouterLink v-if="!auth.isAuthenticated.value" :to="{ path: '/login', query: { redirect: route.fullPath } }">登录</RouterLink></p>
  <div v-if="loading" class="detail-loading skeleton" />
  <template v-else-if="question">
    <article class="question-detail"><div class="detail-kicker"><span>问题 #{{ question.id }}</span><span>{{ formatDate(question.created_at) }}</span></div><h1>{{ question.title }}</h1><p>{{ question.content }}</p><footer><span>由 {{ question.author_name }} 发布</span><span><Eye :size="16" />{{ question.view_count }} 次浏览</span><span><MessageSquare :size="16" />{{ question.answer_count }} 个回答</span><button v-if="canManage" class="text-button danger" :disabled="deleting" @click="remove()">删除问题</button></footer></article>
    <section class="answers-section"><div class="section-title"><div><p class="eyebrow">社区回答</p><h2>{{ question.answer_count }} 条讨论</h2></div><label>回答排序<select v-model="sort" @change="page = 1; loadAnswers()" :disabled="answersLoading || submitting"><option value="hot">最有帮助</option><option value="new">最新回答</option><option value="accepted">已采纳</option></select></label></div>
      <p v-if="answersError" class="notice error" role="alert">{{ answersError }} <button @click="loadAnswers">重试回答加载</button></p>
      <div v-if="answersLoading" class="skeleton" aria-label="正在加载回答" />
      <EmptyState v-else-if="!answersError && !answers.length" :title="sort === 'accepted' ? '暂无已采纳回答' : page > 1 ? '这一页没有更多回答' : '还没有回答'" description="切换排序、返回上一页，或分享你的处理方式。" />
      <article v-for="answer in answers" :key="answer.id" :id="`answer-${answer.id}`" :class="['answer-card', { accepted: answer.is_accepted }]">
        <div class="answer-author"><span class="avatar">{{ answer.author_name.slice(0, 1).toUpperCase() }}</span><span><strong>{{ answer.author_name }}</strong><small>{{ formatDate(answer.created_at) }}</small></span><span v-if="answer.is_accepted" class="accepted-label"><Check :size="15" />已采纳</span></div>
        <p>{{ answer.content }}</p>
        <footer><button :class="{ liked: answer.is_liked }" :aria-pressed="answer.is_liked" :disabled="likingIds.has(answer.id)" @click="toggleLike(answer)"><Heart :size="16" :fill="answer.is_liked ? 'currentColor' : 'none'" />{{ answer.is_liked ? '已点赞' : '有帮助' }} {{ answer.like_count }}</button><button v-if="canManage && !answer.is_accepted" :disabled="accepting" @click="accept(answer)"><Check :size="16" />采纳回答</button><button v-if="auth.isAuthenticated.value && answer.author_name === auth.state.username" :disabled="deleting" @click="remove(answer)">删除</button><span>回答 ID {{ answer.id }}</span></footer>
      </article>
      <nav class="pagination" aria-label="回答分页"><button class="secondary-button" :disabled="page === 1 || answersLoading || submitting" @click="page--; loadAnswers()">上一页</button><span>第 {{ page }} 页</span><button class="secondary-button" :disabled="!hasMore || answersLoading || submitting || !!answersError" @click="page++; loadAnswers()">下一页</button></nav>
    </section>
    <form class="answer-composer" @submit.prevent="submitAnswer"><div><p class="eyebrow">补充你的经验</p><h2>写下一个可执行的回答</h2></div><textarea v-model.trim="answerText" maxlength="1000" required rows="5" placeholder="说清楚你的判断、操作步骤和适用边界…"></textarea><div><small>{{ answerText.length }} / 1000</small><button class="primary-button" :disabled="submitting || !answerText.trim()"><Send :size="17" />{{ submitting ? '发布中…' : '发布回答' }}</button></div></form>
  </template>
</template>
