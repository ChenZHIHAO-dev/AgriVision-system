import { test } from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const bundled = await build({
  stdin: {
    contents:
      "export * from './apps/client/src/lib/auth.ts'; export * from './apps/client/src/lib/preview.ts'; export * from './apps/client/src/lib/assets.ts'; export * from './apps/client/src/lib/theme.ts'",
    resolveDir: root,
    loader: 'ts',
  },
  bundle: true,
  write: false,
  platform: 'node',
  format: 'cjs',
  define: {
    'import.meta.env': '{"BASE_URL":"/AgriVision-system/","VITE_DATA_MODE":"live"}',
    'process.env.NODE_ENV': '"test"',
  },
})
function fresh() {
  const storage = new Map(),
    temporary = new Map(),
    module = { exports: {} }
  const backendAccounts = new Map([
    [
      'admin',
      { id: 'dev-admin', name: 'Admin', username: 'admin', role: 'admin', password: 'admin123' },
    ],
  ])
  const tokens = new Map()
  function response(options, statusCode, data) {
    options.success({ statusCode, data })
  }
  const uni = {
    getStorageSync: (key) => structuredClone(storage.get(key)),
    setStorageSync: (key, value) => storage.set(key, structuredClone(value)),
    removeStorageSync: (key) => storage.delete(key),
    request: (options) => {
      const action = new URL(options.url).pathname,
        data = options.data || {}
      if (action === '/api/auth/register') {
        if (backendAccounts.has(data.username))
          return response(options, 422, { detail: '这个账号已被使用，换一个试试' })
        backendAccounts.set(data.username, {
          id: 'account-' + data.username,
          name: data.name,
          username: data.username,
          role: 'member',
          password: data.password,
        })
      }
      if (['/api/auth/login', '/api/auth/register'].includes(action)) {
        const account = backendAccounts.get(data.username)
        if (!account || account.password !== data.password)
          return response(options, 401, { detail: '账号或密码不正确，请重新输入' })
        const { password: _password, ...user } = account,
          token = 'fake-server-session-' + Math.random().toString(36).slice(2)
        tokens.set(token, user)
        return response(options, 200, {
          user,
          access_token: token,
          expires_at: Date.now() / 1000 + 3600,
        })
      }
      const token = String(options.header.Authorization || '').replace('Bearer ', '')
      if (action === '/api/auth/logout') {
        tokens.delete(token)
        return response(options, 204, null)
      }
      if (action === '/api/auth/me' && tokens.has(token))
        return response(options, 200, { user: tokens.get(token) })
      response(options, 401, { detail: '登录已过期，请重新登录' })
    },
  }
  const session = {
    getItem: (key) => temporary.get(key),
    setItem: (key, value) => temporary.set(key, value),
    removeItem: (key) => temporary.delete(key),
  }
  const listeners = new Set(),
    media = {
      matches: false,
      addEventListener: (_event, listener) => listeners.add(listener),
      removeEventListener: (_event, listener) => listeners.delete(listener),
    }
  new Function(
    'module',
    'exports',
    'require',
    'uni',
    'sessionStorage',
    'window',
    bundled.outputFiles[0].text,
  )(module, module.exports, createRequire(import.meta.url), uni, session, {
    matchMedia: () => media,
  })
  return {
    ...module.exports,
    storage,
    listeners,
    changeSystemTheme: (dark) => {
      media.matches = dark
      for (const listener of listeners) listener()
    },
  }
}
test('login uses the account service and logout clears the server-issued session', async () => {
  const app = fresh()
  await assert.rejects(app.auth.login('admin', 'wrong123', true), /账号或密码/)
  assert.equal(app.user.value, null)
  await app.auth.login(' ADMIN ', 'admin123', true)
  assert.equal(app.user.value.id, 'dev-admin')
  assert.equal(app.user.value.role, 'admin')
  await app.auth.logout()
  assert.equal(app.user.value, null)
})
test('registration validates fields and never stores a password on the client', async () => {
  const app = fresh()
  await assert.rejects(app.auth.register('测试', '1bad', 'test1234'), /账号需/)
  await assert.rejects(app.auth.register('测试', 'grower', '123'), /密码长度/)
  await app.auth.register('测试用户', 'Grower', 'test1234')
  await assert.rejects(app.auth.register('另一人', 'grower', 'test5678'), /已被使用/)
  assert.equal(JSON.stringify([...app.storage.values()]).includes('test1234'), false)
  await app.auth.logout()
  await app.auth.login('grower', 'test1234', false)
  assert.equal(app.user.value.name, '测试用户')
})
test('guest consultations stay temporary and are not migrated into account history', async () => {
  const app = fresh()
  const record = await app.previewRequest('/api/cases/demo', 'POST', { crop: 'wheat' })
  await app.previewRequest('/api/cases/' + record.id + '/messages', 'POST', {
    text: '还需要补充什么信息？',
  })
  assert.equal((await app.previewRequest('/api/cases/' + record.id, 'GET')).messages.length, 2)
  assert.equal(
    [...app.storage.keys()].some((key) => key.includes('.records.')),
    false,
  )
  await app.auth.login('admin', 'admin123', true)
  app.clearGuestRecords()
  assert.equal((await app.previewRequest('/api/cases', 'GET')).items.length, 0)
  await assert.rejects(app.previewRequest('/api/cases/' + record.id, 'GET'), /已不存在/)
  await app.auth.logout()
  assert.equal((await app.previewRequest('/api/cases', 'GET')).items.length, 0)
})
test('medication questions do not invent a product or dose in the local fallback', async () => {
  const app = fresh(),
    record = await app.previewRequest('/api/cases/demo', 'POST', { crop: 'wheat' })
  const updated = await app.previewRequest('/api/cases/' + record.id + '/messages', 'POST', {
    text: '请给我用药配方和剂量',
  })
  const reply = updated.messages.at(-1)
  assert.equal(reply.provider, 'preview')
  assert.match(reply.text, /产品标签/)
  assert.equal(reply.products.length, 0)
  assert.doesNotMatch(reply.text, /\d+\s*(毫升|克|倍)/)
})
test('asset URLs keep the GitHub Pages base path', () =>
  assert.equal(fresh().asset('crops/wheat.png'), '/AgriVision-system/static/crops/wheat.png'))
test('text consultation collects crop and growth stage without repeating a filled field', async () => {
  const app = fresh()
  let record = await app.previewRequest('/api/consultations', 'POST', {})
  record = await app.previewRequest('/api/cases/' + record.id + '/messages', 'POST', {
    text: '叶片有斑点，先观察什么？',
  })
  assert.equal(record.messages.at(-1).follow_up.field, 'crop')
  record = await app.previewRequest('/api/cases/' + record.id + '/messages', 'POST', {
    text: '这次咨询小麦，目前处于苗期。',
  })
  assert.equal(record.crop, 'wheat')
  assert.equal(record.stage, '苗期')
  assert.equal(record.messages.at(-1).follow_up, undefined)
})
test('unconnected document preview does not pretend to have parsed the file', async () => {
  const app = fresh()
  let record = await app.previewRequest('/api/consultations', 'POST', {
    crop: 'wheat',
    stage: '苗期',
  })
  record = await app.previewUpload(
    '/api/cases/' + record.id + '/attachments',
    'data:text/plain,local-test-note',
    { filename: '农事记录.txt' },
  )
  const file = record.documents[0]
  assert.equal(file.extraction, 'requires-backend')
  record = await app.previewRequest('/api/cases/' + record.id + '/messages', 'POST', {
    text: '请概括资料',
    attachment_ids: [file.id],
  })
  assert.match(record.messages.at(-1).text, /(?:暂不解析|无法读取)文件正文/)
  assert.doesNotMatch(JSON.stringify(record), /local-test-note/)
})
test('system theme updates and manual overrides preserve the selected mode', () => {
  const app = fresh(),
    dispose = app.observeSystemTheme()
  assert.equal(app.resolvedTheme.value, 'light')
  app.changeSystemTheme(true)
  assert.equal(app.resolvedTheme.value, 'dark')
  app.setTheme('light')
  app.changeSystemTheme(true)
  assert.equal(app.resolvedTheme.value, 'light')
  app.setTheme('system')
  assert.equal(app.resolvedTheme.value, 'dark')
  dispose()
  assert.equal(app.listeners.size, 0)
})
