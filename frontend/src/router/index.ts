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
  ],
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach((to) => to.path === '/login' && auth.isAuthenticated.value ? '/questions' : true)
export default router
