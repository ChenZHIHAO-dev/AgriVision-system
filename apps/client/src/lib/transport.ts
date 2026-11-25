import { resolveConnection } from './bootstrap'
export type DataMode = 'preview' | 'live'
const SESSION = 'agrivision.session.v2'
type StoredSession = { user: unknown; expires: number; accessToken: string }
let inMemorySession: StoredSession | null = null
let href = ''
// #ifdef H5
href = typeof window !== 'undefined' ? window.location?.href || '' : ''
// #endif
const initial = resolveConnection({
  href,
  // #ifndef MP-WEIXIN
  savedMode: uni.getStorageSync('agrivision.connection.mode.v2'),
  savedBase: uni.getStorageSync('agrivision.connection.api.v2'),
  // #endif
  environmentMode: import.meta.env.VITE_DATA_MODE,
  environmentBase: import.meta.env.VITE_API_BASE_URL,
})
// #ifndef MP-WEIXIN
if (initial.explicit) {
  uni.setStorageSync('agrivision.connection.mode.v2', initial.mode)
  uni.setStorageSync('agrivision.connection.api.v2', initial.base)
}
// #endif
// #ifdef MP-WEIXIN
if (import.meta.env.VITE_WECHAT_PACKAGE && initial.mode === 'live') {
  const sessionOriginKey = 'agrivision.session.origin.v1'
  if (uni.getStorageSync(sessionOriginKey) !== initial.base) {
    uni.removeStorageSync(SESSION)
    uni.setStorageSync(sessionOriginKey, initial.base)
  }
}
// #endif
const temporaryClient =
  'av_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 16)
export function clientId() {
  return temporaryClient
}
export function dataMode(): DataMode {
  // #ifndef MP-WEIXIN
  const saved = uni.getStorageSync('agrivision.connection.mode.v2')
  if (saved === 'preview' || saved === 'live') return saved
  // #endif
  return initial.mode
}
export function setDataMode(mode: DataMode) {
  // #ifdef MP-WEIXIN
  if (mode !== initial.mode) throw new Error('小程序的连接模式由打包配置指定')
  // #endif
  // #ifndef MP-WEIXIN
  uni.setStorageSync('agrivision.connection.mode.v2', mode)
  // #endif
}
export function apiBase() {
  // #ifndef MP-WEIXIN
  const saved = uni.getStorageSync('agrivision.connection.api.v2')
  if (typeof saved === 'string' && saved) return saved.replace(/\/$/, '')
  // #endif
  return initial.base.replace(/\/$/, '')
}
export function setApiBase(url: string) {
  // #ifdef MP-WEIXIN
  if (url.replace(/\/$/, '') !== apiBase()) throw new Error('小程序的服务器地址由打包配置指定')
  // #endif
  // #ifndef MP-WEIXIN
  if (!/^https?:\/\/[^\s/?#]+(?::\d+)?(?:\/[^?#]*)?$/.test(url))
    throw new Error('请输入有效的 http 或 https 服务地址')
  uni.setStorageSync('agrivision.connection.api.v2', url.replace(/\/$/, ''))
  // #endif
}
export function clearSession() {
  inMemorySession = null
  uni.removeStorageSync(SESSION)
  // #ifdef H5
  sessionStorage.removeItem(SESSION)
  // #endif
}
export function saveSession(session: StoredSession, remember: boolean) {
  clearSession()
  if (remember) {
    uni.setStorageSync(SESSION, session)
    return
  }
  // #ifdef H5
  sessionStorage.setItem(SESSION, JSON.stringify(session))
  // #endif
  // #ifndef H5
  inMemorySession = session
  // #endif
}
export function storedSession(): StoredSession | null {
  try {
    let value = inMemorySession || uni.getStorageSync(SESSION)
    // #ifdef H5
    value = value || JSON.parse(sessionStorage.getItem(SESSION) || 'null')
    // #endif
    return value && value.expires > Date.now() && typeof value.accessToken === 'string'
      ? value
      : null
  } catch {
    return null
  }
}
export function accessToken() {
  return storedSession()?.accessToken || ''
}
export function sessionHeaders(token = accessToken()): Record<string, string> {
  return { 'X-Client-ID': clientId(), ...(token ? { Authorization: 'Bearer ' + token } : {}) }
}
export function errorText(data: unknown, fallback: string) {
  return typeof data === 'object' && data && 'detail' in data && typeof data.detail === 'string'
    ? data.detail
    : fallback
}
export function serverRequest<T>(
  path: string,
  method: 'GET' | 'POST' | 'DELETE',
  data?: unknown,
  {
    token = accessToken(),
    timeout = 20000,
    fallback = '服务暂不可用，请稍后重试',
    networkError = '暂时无法连接账户服务，请稍后重试',
  }: { token?: string; timeout?: number; fallback?: string; networkError?: string } = {},
): Promise<T> {
  return new Promise((resolve, reject) =>
    uni.request({
      url: apiBase() + path,
      method,
      data: data as Record<string, unknown>,
      header: { ...sessionHeaders(token), 'Content-Type': 'application/json' },
      timeout,
      success: ({ statusCode, data }) =>
        statusCode >= 200 && statusCode < 300
          ? resolve(data as T)
          : reject(new Error(errorText(data, fallback))),
      fail: () => reject(new Error(networkError)),
    }),
  )
}
// #ifdef H5
if (typeof window !== 'undefined' && window.addEventListener)
  window.addEventListener('pagehide', () => {
    if (dataMode() === 'live' && !accessToken() && navigator.sendBeacon)
      navigator.sendBeacon(
        apiBase() + '/api/guest/end',
        new Blob([JSON.stringify({ client_id: clientId() })], { type: 'application/json' }),
      )
  })
// #endif
