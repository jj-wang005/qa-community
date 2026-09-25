import { computed, reactive } from 'vue'

const ACCESS_KEY = 'qa_access_token'
const REFRESH_KEY = 'qa_refresh_token'
const USER_KEY = 'qa_username'

const state = reactive({
  accessToken: localStorage.getItem(ACCESS_KEY) ?? '',
  refreshToken: localStorage.getItem(REFRESH_KEY) ?? '',
  username: localStorage.getItem(USER_KEY) ?? '',
})

function saveTokens(accessToken: string, refreshToken: string, username = state.username) {
  Object.assign(state, { accessToken, refreshToken, username })
  localStorage.setItem(ACCESS_KEY, accessToken)
  localStorage.setItem(REFRESH_KEY, refreshToken)
  localStorage.setItem(USER_KEY, username)
}

function clearAuth() {
  Object.assign(state, { accessToken: '', refreshToken: '', username: '' })
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
  localStorage.removeItem(USER_KEY)
}

export const auth = { state, isAuthenticated: computed(() => Boolean(state.accessToken)), saveTokens, clearAuth }
