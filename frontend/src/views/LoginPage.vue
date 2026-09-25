<script setup lang="ts">
import { ArrowRight, KeyRound, UserRound } from 'lucide-vue-next'
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import { auth } from '../stores/auth'

const router = useRouter()
const mode = ref<'login' | 'register'>('login')
const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''; loading.value = true
  try {
    if (mode.value === 'register') await api('/api/v1/auth/register', { method: 'POST', body: JSON.stringify({ username: username.value, password: password.value }) })
    const data = await api<{ access_token: string; refresh_token: string }>('/api/v1/auth/login', { method: 'POST', body: JSON.stringify({ username: username.value, password: password.value }) })
    auth.saveTokens(data.access_token, data.refresh_token, username.value)
    router.push('/questions')
  } catch (err) { error.value = err instanceof Error ? err.message : '请求未完成' }
  finally { loading.value = false }
}
</script>

<template>
  <section class="auth-layout">
    <div class="auth-story">
      <p class="eyebrow">QA COMMUNITY</p>
      <h1>让问题留下来，<br><em>让答案说得清。</em></h1>
      <p>这里的 AI 不替你拍板。它会检索社区资料、标明来源，并在执行点赞前等待你的确认。</p>
      <div class="auth-proof"><span>检索</span><i /><span>回答</span><i /><span class="amber">确认</span></div>
    </div>
    <form class="auth-card" @submit.prevent="submit">
      <div><p class="eyebrow">{{ mode === 'login' ? '欢迎回来' : '加入讨论' }}</p><h2>{{ mode === 'login' ? '登录账户' : '创建账户' }}</h2><p class="muted">{{ mode === 'login' ? '继续参与真实、可追溯的技术讨论。' : '用户名 3–16 位，密码 6–16 位。' }}</p></div>
      <label><span>用户名</span><div class="field-with-icon"><UserRound :size="18" /><input v-model.trim="username" minlength="3" maxlength="16" autocomplete="username" required placeholder="输入用户名"></div></label>
      <label><span>密码</span><div class="field-with-icon"><KeyRound :size="18" /><input v-model="password" type="password" minlength="6" maxlength="16" :autocomplete="mode === 'login' ? 'current-password' : 'new-password'" required placeholder="输入密码"></div></label>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <button class="primary-button wide" :disabled="loading">{{ loading ? '正在处理…' : mode === 'login' ? '登录' : '注册并登录' }}<ArrowRight :size="18" /></button>
      <button class="text-button" type="button" @click="mode = mode === 'login' ? 'register' : 'login'; error = ''">{{ mode === 'login' ? '没有账户？现在注册' : '已有账户？返回登录' }}</button>
    </form>
  </section>
</template>
