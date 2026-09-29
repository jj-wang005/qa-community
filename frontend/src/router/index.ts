import { createRouter, createWebHistory } from 'vue-router'
import { auth } from '../stores/auth'
import QuestionsPage from '../views/QuestionsPage.vue'
import QuestionDetailPage from '../views/QuestionDetailPage.vue'
import AssistantPage from '../views/AssistantPage.vue'
import LoginPage from '../views/LoginPage.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/questions' },
    { path: '/questions', component: QuestionsPage },
    { path: '/questions/:id', component: QuestionDetailPage },
    { path: '/assistant', component: AssistantPage },
    { path: '/login', component: LoginPage },
    { path: '/profile', component: () => import('../views/ProfilePage.vue'), meta: { requiresAuth: true } },
    { path: '/:pathMatch(.*)*', component: () => import('../views/NotFoundPage.vue') },
  ],
  scrollBehavior: (_to, _from, savedPosition) => savedPosition ?? ({ top: 0 }),
})

router.beforeEach((to) => {
  if (to.meta.requiresAuth && !auth.isAuthenticated.value) return { path: '/login', query: { redirect: to.fullPath } }
  return to.path === '/login' && auth.isAuthenticated.value ? '/profile' : true
})
export default router
