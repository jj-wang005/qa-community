<script setup lang="ts">
import { Bot, LogIn, LogOut, MessageCircleQuestion, Menu, X } from 'lucide-vue-next'
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { auth } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const menuOpen = ref(false)
function logout() { auth.clearAuth(); menuOpen.value = false; router.push('/login') }
</script>

<template>
  <div class="site-frame">
    <header class="topbar">
      <RouterLink class="brand" to="/questions" aria-label="问答社区首页">
        <span class="brand-mark">Q?</span>
        <span><strong>问答公社</strong><small>知识经过讨论才可靠</small></span>
      </RouterLink>
      <button class="icon-button mobile-menu" :aria-label="menuOpen ? '关闭菜单' : '打开菜单'" @click="menuOpen = !menuOpen">
        <X v-if="menuOpen" :size="20" /><Menu v-else :size="20" />
      </button>
      <nav :class="['main-nav', { open: menuOpen }]" aria-label="主导航">
        <RouterLink :class="{ active: route.path.startsWith('/questions') }" to="/questions" @click="menuOpen = false"><MessageCircleQuestion :size="18" />社区问答</RouterLink>
        <RouterLink :class="{ active: route.path === '/assistant' }" to="/assistant" @click="menuOpen = false"><Bot :size="18" />AI 助手</RouterLink>
        <span class="nav-rule" />
        <button v-if="auth.isAuthenticated.value" class="nav-session" @click="logout"><span>{{ auth.state.username }}</span><LogOut :size="17" />退出</button>
        <RouterLink v-else class="nav-session" to="/login" @click="menuOpen = false"><LogIn :size="17" />登录</RouterLink>
      </nav>
    </header>
    <main class="main-content"><slot /></main>
    <footer class="footer"><span>QA COMMUNITY / FASTAPI + RAG AGENT</span><span>回答有出处，操作要确认。</span></footer>
  </div>
</template>
