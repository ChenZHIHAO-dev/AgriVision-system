import { test } from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const bundle = (mode) =>
  build({
    stdin: {
      contents:
        "export * from './apps/client/src/lib/auth.ts'; export * from './apps/client/src/lib/preview.ts'; export * from './apps/client/src/lib/assets.ts'; export * from './apps/client/src/lib/theme.ts'; export * from './apps/client/src/lib/conversationTitle.ts'",
      resolveDir: root,
      loader: 'ts',
    },
    bundle: true,
    write: false,
    platform: 'node',
    format: 'cjs',
    define: {
      'import.meta.env': JSON.stringify({ BASE_URL: '/AgriVision-system/', VITE_DATA_MODE: mode }),
      'process.env.NODE_ENV': '"test"',
    },
  })
const [live, preview] = await Promise.all([bundle('live'), bundle('preview')])
const previewPhoto = 'data:image/jpeg;base64,cGhvdG8='
class TestImage {
  width = 320
  height = 320
  get src() {
    return this.url
  }
  set src(value) {
    this.url = value
    this.onload()
  }
}
const document = {
  createElement: () => ({
    getContext: () => ({ fillRect() {}, drawImage() {} }),
    toDataURL: () => previewPhoto,
  }),
}
function fresh(mode = 'live') {
  const storage = new Map(),
    temporary = new Map(),
    module = { exports: {} }
  const backendAccounts = new Map([
    [
      'admin',
      { id: 'dev-admin', name: 'Admin', username: 'admin', role: 'admin', password: 'admin123' },
    ],
  ])
  const tokens = new Map(),
    requests = []
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
      requests.push(action)
      if (action === '/api/auth/login') {
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
    'Image',
    'document',
    (mode === 'preview' ? preview : live).outputFiles[0].text,
  )(
    module,
    module.exports,
    createRequire(import.meta.url),
    uni,
    session,
    { matchMedia: () => media },
    TestImage,
    mode === 'preview' ? document : undefined,
  )
  return {
    ...module.exports,
    storage,
    requests,
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
test('unremembered sign-in works without persisting the account token', async () => {
  const app = fresh()
  await app.auth.login('admin', 'admin123', false)
  assert.equal(app.storage.has('agrivision.session.v2'), false)
  await app.auth.restore()
  assert.equal(app.user.value?.role, 'admin')
  await app.auth.logout()
  await app.auth.restore()
  assert.equal(app.user.value, null)
})

test('live registration is disabled before a request is sent', async () => {
  const app = fresh()
  await assert.rejects(app.auth.register('测试用户', 'grower', 'test1234'), /暂不开放注册/)
  assert.equal(app.user.value, null)
  assert.deepEqual(app.requests, [])
  assert.equal(JSON.stringify([...app.storage.values()]).includes('test1234'), false)
})
test('guests can preview recognition but cannot submit a consultation', async () => {
  const app = fresh('preview')
  const record = await app.previewRequest('/api/cases/demo', 'POST', { crop: 'wheat' })
  const casePath = '/api/cases/' + record.id
  await assert.rejects(app.previewRequest('/api/consultations', 'POST', {}), /登录/)
  await assert.rejects(
    app.previewRequest(casePath + '/messages', 'POST', { text: '还需要补充什么信息？' }),
    /登录/,
  )
  await assert.rejects(
    app.previewRequest(casePath + '/resume', 'POST', { question_id: 'old' }),
    /登录/,
  )
  assert.equal((await app.previewRequest(casePath, 'GET')).messages.length, record.messages.length)
  assert.equal((await app.previewRequest('/api/cases', 'GET')).items.length, 0)
  await app.auth.previewLogin()
  assert.equal((await app.previewRequest('/api/cases', 'GET')).items.length, 0)
  await assert.rejects(app.previewRequest(casePath, 'GET'), /已不存在/)
})

test('demo login opens the selected photo case without simulating a new question', async () => {
  const app = fresh('preview')
  const record = await app.previewUpload('/api/cases', previewPhoto, { crop: 'wheat' })
  const account = await app.auth.previewLogin(record.id)
  assert.equal(account.continuedCaseId, record.id)
  assert.equal(app.user.value.preview, true)
  assert.equal(app.user.value.role, 'member')
  const path = '/api/cases/' + record.id
  const retained = await app.previewRequest(path, 'GET')
  assert.deepEqual(retained.images, record.images)
  assert.deepEqual(retained.advice, record.advice)
  assert.deepEqual(retained.messages, record.messages)
  const updated = await app.previewRequest(path + '/messages', 'POST', {
    text: '如何拍清楚症状？',
  })
  assert.equal(updated.messages.at(-1).provider, 'preview')
  await app.auth.logout()
  assert.equal(app.user.value, null)
  await assert.rejects(app.previewRequest(path, 'GET'), /已不存在/)
})

async function demoMember() {
  const app = fresh('preview')
  await app.auth.previewLogin()
  return app
}

test('medication questions do not invent a product or dose in the local fallback', async () => {
  const app = await demoMember(),
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
test('general questions can be sent from an empty consultation without crop intake', async () => {
  const app = await demoMember()
  const record = await app.previewRequest('/api/consultations', 'POST', {})
  for (const text of ['如何拍清楚症状？', '怎么看农药标签？', '生育期是什么意思？']) {
    const updated = await app.previewRequest('/api/cases/' + record.id + '/messages', 'POST', {
      text,
    })
    assert.equal(updated.crop, null)
    assert.equal(updated.messages.at(-1).provider, 'preview')
    assert.equal(updated.messages.at(-1).follow_up, undefined)
    assert.equal(updated.pending_question, undefined)
  }
})
test('field questions answer first and offer optional information without a pending task', async () => {
  const app = await demoMember()
  let record = await app.previewRequest('/api/consultations', 'POST', {})
  record = await app.previewRequest('/api/cases/' + record.id + '/messages', 'POST', {
    text: '叶片有斑点，先观察什么？',
  })
  assert.equal(record.messages.at(-1).context_suggestion.field, 'crop')
  assert.equal(record.messages.at(-1).provider, 'preview')
  assert.ok(record.messages.at(-1).photo_suggestion)
  assert.equal(record.pending_question, undefined)
  record = await app.previewRequest('/api/cases/' + record.id + '/messages', 'POST', {
    text: '这次咨询小麦，目前处于苗期。',
  })
  assert.equal(record.crop, 'wheat')
  assert.equal(record.stage, '苗期')
  assert.equal(record.messages.at(-1).follow_up, undefined)
})
test('unconnected document preview does not pretend to have parsed the file', async () => {
  const app = await demoMember()
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

test('conversation title is independent of the case label and persists during preview', async () => {
  const app = await demoMember()
  const record = await app.previewRequest('/api/consultations', 'POST', {})
  const path = '/api/cases/' + record.id
  assert.equal(app.conversationTitle(record), '新对话')
  const updated = await app.previewRequest(path + '/messages', 'POST', {
    text: '怎么看农药标签？',
  })
  assert.equal(app.conversationTitle(updated), '怎么看农药标签？')
  await app.previewRequest(path + '/context', 'POST', { conversation_title: '  查标签  ' })
  const renamed = await app.previewRequest(path, 'GET')
  assert.equal(app.conversationTitle(renamed), '查标签')
  assert.equal(renamed.title, record.title)
  assert.equal(renamed.messages.length, updated.messages.length)
})

test('optional fields can be skipped or filled without creating messages or blocking later answers', async () => {
  const app = await demoMember()
  const record = await app.previewRequest('/api/consultations', 'POST', {})
  const path = '/api/cases/' + record.id
  let updated = await app.previewRequest(path + '/messages', 'POST', {
    text: '小麦叶片白斑如何观察？',
  })
  assert.equal(updated.messages.at(-1).provider, 'preview')
  assert.equal(updated.messages.at(-1).context_suggestion.field, 'stage')
  assert.equal(updated.pending_question, undefined)
  const count = updated.messages.length
  updated = await app.previewRequest(path + '/context', 'POST', {
    skip_context_fields: ['stage', 'location'],
  })
  assert.equal(updated.messages.length, count)
  updated = await app.previewRequest(path + '/messages', 'POST', { text: '叶片还应该怎么看？' })
  assert.equal(updated.messages.at(-1).provider, 'preview')
  assert.equal(updated.messages.at(-1).context_suggestion, undefined)
  assert.equal(updated.messages.at(-1).photo_suggestion, undefined)
  updated = await app.previewRequest(path + '/context', 'POST', { stage: '苗期', location: '河南' })
  assert.equal(updated.messages.length, count + 2)
  assert.deepEqual(updated.skipped_context_fields, [])
  assert.equal(updated.pending_question, undefined)
})


test('declining photos does not answer with another photography tutorial', async () => {
  const app = await demoMember()
  const record = await app.previewRequest('/api/consultations', 'POST', {})
  const updated = await app.previewRequest('/api/cases/' + record.id + '/messages', 'POST', {
    text: '暂时不提供照片，可以先看看可能的原因吗？',
  })
  const answer = updated.messages.at(-1)
  assert.equal(answer.photo_suggestion, undefined)
  assert.doesNotMatch(answer.text, /先拍一张|补一张|怎样拍清/)
})
