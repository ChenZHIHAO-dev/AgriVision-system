import { ref } from 'vue'
import { sha256 } from '@noble/hashes/sha2.js'
import { bytesToHex, utf8ToBytes } from '@noble/hashes/utils.js'

export interface User { id: string; username: string; name: string; role: 'tester' | 'member' }
interface Account extends User { salt: string; digest: string }
interface Session { user: User; expires: number }
export interface AuthGateway {
  login(username: string, password: string, remember: boolean): Promise<User>
  register(name: string, username: string, password: string): Promise<User>
  logout(): void
}
const ACCOUNTS = 'agrivision.dev.accounts.v1'
const SESSION = 'agrivision.dev.session.v1'
export const TEST_ACCOUNT = { username: 'admin', password: 'admin123' } as const
const admin: User = { id: 'dev-admin', username: 'admin', name: 'Admin', role: 'tester' }

function readSession(): User | null {
  try {
    let session = uni.getStorageSync(SESSION) as Session | undefined
    // #ifdef H5
    session = session || JSON.parse(sessionStorage.getItem(SESSION) || 'null')
    // #endif
    return session?.expires && session.expires > Date.now() ? session.user : null
  } catch { return null }
}
export const user = ref<User | null>(readSession())
function saveSession(value: User, remember: boolean) {
  const session: Session = { user: value, expires: Date.now() + (remember ? 7 * 86400000 : 8 * 3600000) }
  uni.removeStorageSync(SESSION)
  // #ifdef H5
  sessionStorage.removeItem(SESSION)
  if (!remember) sessionStorage.setItem(SESSION, JSON.stringify(session))
  // #endif
  // #ifndef H5
  uni.setStorageSync(SESSION, session)
  // #endif
  if (remember) uni.setStorageSync(SESSION, session)
  user.value = value
}
function accounts(): Account[] { return uni.getStorageSync(ACCOUNTS) || [] }
function digest(password: string, salt: string) { return bytesToHex(sha256(utf8ToBytes(`${salt}:${password}`))) }
function validateUsername(username: string) {
  if (!/^[a-zA-Z][a-zA-Z0-9_]{2,23}$/.test(username)) throw new Error('账号需为 3–24 位字母、数字或下划线，以字母开头')
}

// Development-only adapter. This is local UI state, never a security boundary.
// Replace with server-issued sessions when the account service is implemented.
export const auth: AuthGateway = {
  async login(raw, password, remember) {
    const username = raw.trim().toLowerCase()
    if (!username || !password) throw new Error('请填写账号和密码')
    let result: User | undefined
    if (username === TEST_ACCOUNT.username && password === TEST_ACCOUNT.password) result = admin
    else {
      const account = accounts().find(item => item.username === username)
      if (account && digest(password, account.salt) === account.digest) {
        const { salt: _salt, digest: _digest, ...profile } = account
        result = profile
      }
    }
    if (!result) throw new Error('账号或密码不正确，请重新输入')
    saveSession(result, remember)
    return result
  },
  async register(name, raw, password) {
    const username = raw.trim().toLowerCase()
    validateUsername(username)
    if (!name.trim() || name.trim().length > 20) throw new Error('请填写 1–20 字的称呼')
    if (password.length < 6 || password.length > 64) throw new Error('密码长度需为 6–64 位')
    if (username === 'admin' || accounts().some(item => item.username === username)) throw new Error('这个账号已被使用，换一个试试')
    const salt = `${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}`
    const profile: User = { id: `local-${username}`, username, name: name.trim(), role: 'member' }
    try { uni.setStorageSync(ACCOUNTS, [...accounts(), { ...profile, salt, digest: digest(password, salt) }]) }
    catch { throw new Error('此设备暂时无法保存测试账号，请检查浏览器存储设置') }
    saveSession(profile, false)
    return profile
  },
  logout() {
    uni.removeStorageSync(SESSION)
    // #ifdef H5
    sessionStorage.removeItem(SESSION)
    // #endif
    user.value = null
  },
}
