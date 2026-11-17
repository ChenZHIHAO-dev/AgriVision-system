import { test } from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const bundled = await build({
  stdin: { contents: "export * from './apps/client/src/lib/auth.ts'; export * from './apps/client/src/lib/preview.ts'; export * from './apps/client/src/lib/assets.ts'; export * from './apps/client/src/lib/theme.ts'", resolveDir: root, loader: 'ts' },
  bundle: true, write: false, platform: 'node', format: 'cjs',
  define: { 'import.meta.env.BASE_URL': '"/AgriVision-system/"', 'process.env.NODE_ENV': '"test"' },
})
function fresh() {
  const storage = new Map(), temporary = new Map(), module = { exports: {} }
  const uni = { getStorageSync: key => structuredClone(storage.get(key)), setStorageSync: (key, value) => storage.set(key, structuredClone(value)), removeStorageSync: key => storage.delete(key) }
  const session = { getItem: key => temporary.get(key), setItem: (key, value) => temporary.set(key, value), removeItem: key => temporary.delete(key) }
  const listeners = new Set(), media = { matches: false, addEventListener: (_event, listener) => listeners.add(listener), removeEventListener: (_event, listener) => listeners.delete(listener) }
  new Function('module', 'exports', 'require', 'uni', 'sessionStorage', 'window', bundled.outputFiles[0].text)(module, module.exports, createRequire(import.meta.url), uni, session, { matchMedia: () => media })
  return { ...module.exports, storage, listeners, changeSystemTheme: dark => { media.matches = dark; for (const listener of listeners) listener() } }
}

test('admin login validates credentials and logout clears the session', async () => {
  const app = fresh()
  await assert.rejects(app.auth.login('admin', 'wrong123', true), /账号或密码/)
  assert.equal(app.user.value, null)
  await app.auth.login(' ADMIN ', 'admin123', true)
  assert.equal(app.user.value.id, 'dev-admin')
  app.auth.logout()
  assert.equal(app.user.value, null)
})
test('registration validates fields, normalizes account names and keeps passwords out of storage', async () => {
  const app = fresh()
  await assert.rejects(app.auth.register('测试', '1bad', 'test1234'), /账号需/)
  await assert.rejects(app.auth.register('测试', 'grower', '123'), /密码长度/)
  await app.auth.register('测试用户', 'Grower', 'test1234')
  await assert.rejects(app.auth.register('另一个用户', 'grower', 'test5678'), /已被使用/)
  assert.equal(JSON.stringify([...app.storage.values()]).includes('test1234'), false)
  app.auth.logout()
  await app.auth.login('grower', 'test1234', false)
  assert.equal(app.user.value.name, '测试用户')
})
test('guest consultation works without login, and login retains only that guest’s records', async () => {
  const app = fresh()
  const record = await app.previewRequest('/api/cases/demo', 'POST', { crop: 'wheat' })
  await app.previewRequest(`/api/cases/${record.id}/messages`, 'POST', { text: '还需要补充什么信息？' })
  assert.equal((await app.previewRequest(`/api/cases/${record.id}`, 'GET')).messages.length, 2)
  assert.equal([...app.storage.keys()].some(key => key.includes('.records.')), false)
  await app.auth.login('admin', 'admin123', true)
  app.claimGuestRecords()
  assert.equal((await app.previewRequest('/api/cases', 'GET')).items.length, 1)
  app.auth.logout()
  assert.equal((await app.previewRequest('/api/cases', 'GET')).items.length, 0)
  await app.auth.register('另一个测试用户', 'another_user', 'test5678')
  assert.equal((await app.previewRequest('/api/cases', 'GET')).items.length, 0)
  await assert.rejects(app.previewRequest(`/api/cases/${record.id}`, 'GET'), /已不存在/)
})
test('medication questions do not invent a product or dose in the frontend preview', async () => {
  const app = fresh()
  const record = await app.previewRequest('/api/cases/demo', 'POST', { crop: 'wheat' })
  const updated = await app.previewRequest(`/api/cases/${record.id}/messages`, 'POST', { text: '请给我用药配方和剂量' })
  const reply = updated.messages.at(-1)
  assert.equal(reply.provider, 'preview')
  assert.match(reply.text, /产品标签/)
  assert.equal(reply.products.length, 0)
  assert.doesNotMatch(reply.text, /\d+\s*(毫升|克|倍)/)
})
test('asset URLs retain the GitHub Pages repository base path', () => {
  assert.equal(fresh().asset('crops/wheat.png'), '/AgriVision-system/static/crops/wheat.png')
})

test('text consultation asks for crop, accepts a selected stage and stops repeating the question', async () => {
  const app = fresh()
  let record = await app.previewRequest('/api/consultations', 'POST', {})
  record = await app.previewRequest(`/api/cases/${record.id}/messages`, 'POST', { text: '叶片有斑点，先观察什么？' })
  assert.equal(record.crop, null)
  assert.equal(record.messages.at(-1).follow_up.field, 'crop')
  record = await app.previewRequest(`/api/cases/${record.id}/messages`, 'POST', { text: '这次咨询小麦，目前处于苗期。' })
  assert.equal(record.crop, 'wheat')
  assert.equal(record.stage, '苗期')
  assert.equal(record.messages.at(-1).follow_up, undefined)
})

test('frontend document preview records the file without pretending to have read its contents', async () => {
  const app = fresh()
  let record = await app.previewRequest('/api/consultations', 'POST', { crop: 'wheat', stage: '苗期' })
  record = await app.previewUpload(`/api/cases/${record.id}/attachments`, 'data:text/plain,local-test-note', { filename: '农事记录.txt' })
  const attachment = record.documents[0]
  assert.equal(attachment.extraction, 'requires-backend')
  assert.equal(attachment.characters, 0)
  record = await app.previewRequest(`/api/cases/${record.id}/messages`, 'POST', { text: '请概括资料', attachment_ids: [attachment.id] })
  assert.match(record.messages.at(-1).text, /暂不解析文件正文/)
  assert.doesNotMatch(JSON.stringify(record), /local-test-note/)
})
test('theme follows system changes and manual selection remains stable', () => {
  const app = fresh(), dispose = app.observeSystemTheme()
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
