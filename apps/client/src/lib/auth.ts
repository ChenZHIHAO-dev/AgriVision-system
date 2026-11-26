import { ref } from 'vue'
import {
  clearSession,
  saveSession,
  storedSession,
  accessToken,
  dataMode,
  serverRequest,
} from './transport'
import { beginPreviewAccount, endPreviewAccount, currentPreviewUser } from './preview'
export interface User {
  id: string
  username: string
  name: string
  role: 'member' | 'admin'
  preview?: boolean
}
interface AuthResponse {
  user: User
  access_token: string
  expires_at: number
  continued_case_id?: string
}
export interface AuthSuccess extends User {
  continuedCaseId?: string
}
export interface AuthGateway {
  login(
    username: string,
    password: string,
    remember: boolean,
    continueCaseId?: string,
  ): Promise<AuthSuccess>
  register(
    name: string,
    username: string,
    password: string,
    continueCaseId?: string,
  ): Promise<AuthSuccess>
  previewLogin(continueCaseId?: string): Promise<AuthSuccess>
  logout(): Promise<void>
  restore(): Promise<void>
  expire(): void
}
const previous = storedSession()
export const user = ref<User | null>(previous?.accessToken ? (previous.user as User) : null)
function clear() {
  clearSession()
  user.value = null
}
function save(result: AuthResponse, remember: boolean) {
  endPreviewAccount()
  saveSession(
    {
      user: result.user,
      expires: result.expires_at * 1000,
      accessToken: result.access_token,
    },
    remember,
  )
  user.value = result.user
}
function requireService() {
  if (dataMode() !== 'live')
    throw new Error('当前为离线预览，请使用演示账号体验；真实账户需连接服务器')
}
function finish(result: AuthResponse, remember: boolean, selected?: string): AuthSuccess {
  if (selected && result.continued_case_id !== selected)
    throw new Error('本次识别未能接续，请重试登录或重新上传照片')
  save(result, remember)
  return { ...result.user, continuedCaseId: result.continued_case_id }
}
export const auth: AuthGateway = {
  expire: clear,
  async login(raw, password, remember, continueCaseId) {
    const username = raw.trim().toLowerCase()
    if (!username || !password) throw new Error('请填写账号和密码')
    requireService()
    const result = await serverRequest<AuthResponse>(
      '/api/auth/login',
      'POST',
      {
        username,
        password,
        remember,
        ...(continueCaseId ? { continue_case_id: continueCaseId } : {}),
      },
      { token: '' },
    )
    return finish(result, remember, continueCaseId)
  },
  async register() {
    throw new Error('当前仅开放管理员登录，暂不开放注册')
  },
  async previewLogin(continueCaseId) {
    if (dataMode() !== 'preview') throw new Error('演示账号仅用于离线预览')
    const result = beginPreviewAccount(continueCaseId)
    clear()
    user.value = result.user
    return { ...result.user, continuedCaseId: result.continued_case_id }
  },
  async logout() {
    const token = accessToken()
    clear()
    endPreviewAccount()
    if (dataMode() === 'live' && token)
      try {
        await serverRequest('/api/auth/logout', 'POST', undefined, { token })
      } catch {}
  },
  async restore() {
    if (dataMode() !== 'live') {
      clear()
      user.value = currentPreviewUser()
      return
    }
    endPreviewAccount()
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
