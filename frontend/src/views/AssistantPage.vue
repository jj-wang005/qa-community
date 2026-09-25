<script setup lang="ts">
import { Bot, Check, CircleDot, Clock3, Database, Send, ShieldCheck, ThumbsUp, X } from 'lucide-vue-next'
import { nextTick, ref } from 'vue'
import { openEventStream } from '../api/client'
import { auth } from '../stores/auth'
import type { ChatMessage, PendingApproval } from '../types'

const question = ref('')
const messages = ref<ChatMessage[]>([])
const sessionId = ref<string | null>(null)
const pending = ref<PendingApproval | null>(null)
const sending = ref(false)
const error = ref('')
const conversation = ref<HTMLElement | null>(null)
const suggestions = ['社区里有哪些关于 JWT 过期的讨论？', '最新发布的问题有哪些？', '回答 ID 7 说了什么？']

const id = () => crypto.randomUUID()
async function scrollToBottom() { await nextTick(); conversation.value?.scrollTo({ top: conversation.value.scrollHeight, behavior: 'smooth' }) }

function handleEvent(event: string, data: string, assistant: ChatMessage) {
  if (event === 'approval_required') {
    pending.value = JSON.parse(data) as PendingApproval
    sessionId.value = pending.value.session_id
    return
  }
  if (event === 'error') { error.value = data; return }
  if (data.startsWith('[SESSION_ID]:')) { sessionId.value = data.slice('[SESSION_ID]:'.length); return }
  assistant.content += (assistant.content ? '\n' : '') + data
  scrollToBottom()
}

async function send(preset?: string) {
  const content = (preset ?? question.value).trim()
  if (!content || sending.value) return
  question.value = ''; error.value = ''; pending.value = null
  messages.value.push({ id: id(), role: 'user', content })
  const assistant: ChatMessage = { id: id(), role: 'assistant', content: '' }
  messages.value.push(assistant); sending.value = true; await scrollToBottom()
  try {
    await openEventStream('/api/v1/ai/chat', { question: content, session_id: sessionId.value }, (event, data) => handleEvent(event, data, assistant))
    if (!assistant.content && pending.value) assistant.content = '我准备执行一项写操作，需要你先确认。'
  } catch (err) { error.value = err instanceof Error ? err.message : '对话请求未完成'; messages.value = messages.value.filter((item) => item.id !== assistant.id) }
  finally { sending.value = false; await scrollToBottom() }
}

async function decide(decision: 'approve' | 'reject') {
  if (!pending.value || sending.value) return
  error.value = ''; sending.value = true
  const approval = pending.value; pending.value = null
  const assistant: ChatMessage = { id: id(), role: 'assistant', content: '' }
  messages.value.push({ id: id(), role: 'system', content: decision === 'approve' ? '你已批准这次操作。' : '你已拒绝这次操作。' }, assistant)
  try {
    await openEventStream('/api/v1/ai/approve', { session_id: approval.session_id, approval_id: approval.approval_id, decisions: approval.actions.map(() => ({ type: decision })) }, (event, data) => handleEvent(event, data, assistant))
    if (!assistant.content && !pending.value) assistant.content = decision === 'approve' ? '操作已处理。' : '已跳过这次操作。'
  } catch (err) { error.value = err instanceof Error ? err.message : '审批请求未完成'; assistant.content = '审批结果暂时无法确认，请先查询点赞状态后再决定是否重试。' }
  finally { sending.value = false; await scrollToBottom() }
}
</script>

<template>
  <section class="assistant-layout">
    <aside class="agent-rail">
      <div><p class="eyebrow">AGENT TRACE</p><h1>社区 AI</h1><p>从社区讨论中找资料，也能在你确认后完成点赞。</p></div>
      <ol class="trace-list">
        <li class="active"><span><CircleDot :size="17" /></span><div><strong>理解问题</strong><small>保留你的会话上下文</small></div></li>
        <li><span><Database :size="17" /></span><div><strong>检索资料</strong><small>历史知识库或实时社区</small></div></li>
        <li><span><ShieldCheck :size="17" /></span><div><strong>检查回答</strong><small>安全检查后完整发送</small></div></li>
        <li :class="{ active: pending }"><span><ThumbsUp :size="17" /></span><div><strong>人工确认</strong><small>写操作不会自动执行</small></div></li>
      </ol>
      <div class="rail-note"><Clock3 :size="17" /><span><strong>不是逐字生成</strong><small>答案完成检查后一次返回。</small></span></div>
    </aside>

    <section class="chat-panel">
      <header class="chat-header"><span class="bot-avatar"><Bot :size="22" /></span><div><h2>问答助手</h2><p><i />知识库与社区实时数据已接入</p></div><span v-if="auth.isAuthenticated.value" class="login-chip">已登录 · 可审批操作</span><RouterLink v-else class="login-chip guest" to="/login">登录后可审批点赞</RouterLink></header>
      <div ref="conversation" class="conversation" aria-live="polite">
        <div v-if="!messages.length" class="chat-welcome"><span class="bot-avatar large"><Bot :size="30" /></span><p class="eyebrow">带来源的社区助手</p><h2>先问一个具体问题</h2><p>我会在历史知识库与当前社区数据之间选择合适的检索方式。资料不足时，也会直接说明。</p><div class="suggestions"><button v-for="item in suggestions" :key="item" @click="send(item)">{{ item }}</button></div></div>
        <div v-for="message in messages" :key="message.id" :class="['message-row', message.role]">
          <span v-if="message.role === 'assistant'" class="message-avatar"><Bot :size="18" /></span>
          <div class="message-bubble"><small>{{ message.role === 'user' ? '你' : message.role === 'assistant' ? '社区 AI' : '操作记录' }}</small><p>{{ message.content || '正在整理完整回答…' }}</p></div>
        </div>
        <article v-if="pending" class="approval-card">
          <div class="approval-title"><span><ShieldCheck :size="22" /></span><div><p class="eyebrow">需要你的确认</p><h3>允许 AI 执行点赞吗？</h3></div></div>
          <div v-for="action in pending.actions" :key="action.args.answer_id" class="approval-action"><ThumbsUp :size="18" /><span><small>即将点赞的回答</small><strong>回答 ID {{ action.args.answer_id }}</strong></span></div>
          <p>操作将使用当前登录身份；确认后参数不能修改。本请求约 {{ Math.floor(pending.expires_in / 60) }} 分钟内有效。</p>
          <div><button class="secondary-button" @click="decide('reject')"><X :size="17" />拒绝</button><button class="approval-button" @click="decide('approve')"><Check :size="17" />批准点赞</button></div>
        </article>
        <p v-if="error" class="notice error" role="alert">{{ error }}</p>
      </div>
      <form class="chat-composer" @submit.prevent="send()"><textarea v-model="question" rows="1" maxlength="200" :disabled="sending" placeholder="问社区知识，或指定回答 ID 发起点赞…" @keydown.enter.exact.prevent="send()" /><div><small>{{ question.length }} / 200 · Enter 发送</small><button class="send-button" :disabled="sending || !question.trim()" aria-label="发送问题"><Send :size="19" /></button></div></form>
    </section>
  </section>
</template>
