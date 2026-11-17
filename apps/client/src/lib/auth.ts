import { ref } from 'vue'
import { SESSION, storedSession, accessToken, dataMode, serverRequest } from './transport'
export interface User {
  id: string
  username: string
  name: string
  role: 'member' | 'admin'
}
interface AuthResponse {
  user: User
  access_token: string
  expires_at: number
}
export interface AuthGateway {
  login(username: string, password: string, remember: boolean): Promise<User>
  register(name: string, username: string, password: string): Promise<User>
  logout(): Promise<void>
  restore(): Promise<void>
}
const previous = storedSession()
export const user = ref<User | null>(previous?.accessToken ? (previous.user as User) : null)
function clear() {
  uni.removeStorageSync(SESSION)
  // #ifdef H5
  sessionStorage.removeItem(SESSION)
  // #endif
  user.value = null
}
function save(result: AuthResponse, remember: boolean) {
  clear()
  const session = {
    user: result.user,
    expires: result.expires_at * 1000,
    accessToken: result.access_token,
  }
  // #ifdef H5
  if (!remember) sessionStorage.setItem(SESSION, JSON.stringify(session))
  // #endif
  // #ifndef H5
  uni.setStorageSync(SESSION, session)
  // #endif
  if (remember) uni.setStorageSync(SESSION, session)
  user.value = result.user
}
function requireService() {
  if (dataMode() !== 'live') throw new Error('账户服务暂不可用，请使用已连接服务的版本')
}
export const auth: AuthGateway = {
  async login(raw, password, remember) {
    const username = raw.trim().toLowerCase()
    if (!username || !password) throw new Error('请填写账号和密码')
    requireService()
    const result = await serverRequest<AuthResponse>(
      '/api/auth/login',
      'POST',
      { username, password, remember },
      '',
    )
    save(result, remember)
    return result.user
  },
  async register(name, raw, password) {
    const username = raw.trim().toLowerCase()
    if (!/^[a-zA-Z][a-zA-Z0-9_]{2,23}$/.test(username))
      throw new Error('账号需为 3–24 位字母、数字或下划线，以字母开头')
    if (!name.trim() || name.trim().length > 20) throw new Error('请填写 1–20 字的称呼')
    if (password.length < 6 || password.length > 64) throw new Error('密码长度需为 6–64 位')
    requireService()
    const result = await serverRequest<AuthResponse>(
      '/api/auth/register',
      'POST',
      { name: name.trim(), username, password },
      '',
    )
    save(result, false)
    return result.user
  },
  async logout() {
    const token = accessToken()
    clear()
    if (dataMode() === 'live' && token)
      try {
        await serverRequest('/api/auth/logout', 'POST', undefined, token)
      } catch {}
  },
  async restore() {
    if (dataMode() !== 'live') {
      clear()
      return
    }
    if (!accessToken()) {
      clear()
      return
    }
    try {
      const result = await serverRequest<{ user: User }>('/api/auth/me', 'GET')
      user.value = result.user
    } catch {
      clear()
    }
  },
}
