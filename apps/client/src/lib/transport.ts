import { resolveConnection } from './bootstrap'
export type DataMode = 'preview' | 'live'
export const SESSION = 'agrivision.session.v2'
let href = ''
// #ifdef H5
href = typeof window !== 'undefined' ? window.location?.href || '' : ''
// #endif
const initial = resolveConnection({
  href,
  savedMode: uni.getStorageSync('agrivision.connection.mode.v2'),
  savedBase: uni.getStorageSync('agrivision.connection.api.v2'),
  environmentMode: import.meta.env.VITE_DATA_MODE,
  environmentBase: import.meta.env.VITE_API_BASE_URL,
})
if (initial.explicit) {
  uni.setStorageSync('agrivision.connection.mode.v2', initial.mode)
  uni.setStorageSync('agrivision.connection.api.v2', initial.base)
}
const temporaryClient =
  'av_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 16)
export function clientId() {
  return temporaryClient
}
export function dataMode(): DataMode {
  return uni.getStorageSync('agrivision.connection.mode.v2') || initial.mode
}
export function setDataMode(mode: DataMode) {
  uni.setStorageSync('agrivision.connection.mode.v2', mode)
}
export function apiBase() {
  return String(uni.getStorageSync('agrivision.connection.api.v2') || initial.base).replace(
    /\/$/,
    '',
  )
}
export function setApiBase(url: string) {
  if (!/^https?:\/\/[^\s/?#]+(?::\d+)?(?:\/[^?#]*)?$/.test(url))
    throw new Error('请输入有效的 http 或 https 服务地址')
  uni.setStorageSync('agrivision.connection.api.v2', url.replace(/\/$/, ''))
}
export function storedSession(): { user: unknown; expires: number; accessToken?: string } | null {
  try {
    let value = uni.getStorageSync(SESSION)
    // #ifdef H5
    value = value || JSON.parse(sessionStorage.getItem(SESSION) || 'null')
    // #endif
    return value?.expires > Date.now() ? value : null
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
export function serverRequest<T>(
  path: string,
  method: 'GET' | 'POST',
  data?: unknown,
  token = accessToken(),
): Promise<T> {
  return new Promise((resolve, reject) =>
    uni.request({
      url: apiBase() + path,
      method,
      data: data as Record<string, unknown>,
      header: { ...sessionHeaders(token), 'Content-Type': 'application/json' },
      timeout: 20000,
      success: (response) => {
        if (response.statusCode >= 200 && response.statusCode < 300) {
          resolve(response.data as T)
          return
        }
        const result = response.data as { detail?: unknown }
        reject(
          new Error(
            typeof result?.detail === 'string' ? result.detail : '服务暂不可用，请稍后重试',
          ),
        )
      },
      fail: () => reject(new Error('暂时无法连接账户服务，请稍后重试')),
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
