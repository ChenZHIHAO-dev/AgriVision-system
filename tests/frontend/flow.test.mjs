import { test } from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const result = await build({
  stdin: {
    contents:
      "export * from './apps/client/src/lib/drafts.ts'; export * from './apps/client/src/lib/markdown.ts'; export * from './apps/client/src/lib/bootstrap.ts'; export * from './apps/client/src/lib/recognition.ts'; export * from './apps/client/src/lib/navigation.ts'; export * from './apps/client/src/lib/chatActions.ts'",
    resolveDir: root,
    loader: 'ts',
  },
  bundle: true,
  write: false,
  platform: 'node',
  format: 'cjs',
})
const module = { exports: {} }
new Function('module', 'exports', 'require', result.outputFiles[0].text)(
  module,
  module.exports,
  createRequire(import.meta.url),
)
const {
  renderMarkdown,
  resolveConnection,
  imageQuestion,
  createDraftStore,
  questionForAnswer,
  suggestedQuestions,
  answerShareText,
  answerCopyText,
} = module.exports

test('assistant Markdown renders headings, emphasis, lists, tables and code', () => {
  const html = renderMarkdown(
    '# 检查建议\n\n**先观察**\n\n- 叶片正面\n- 叶片背面\n\n| 部位 | 情况 |\n| --- | --- |\n| 叶片 | 黄化 |\n\n``\n\n~~~txt\n记录日期\n~~~',
  )
  for (const tag of ['h1', 'strong', 'ul', 'li', 'table', 'pre', 'code'])
    assert.match(html, new RegExp('<' + tag + '(?:\\s|>)'))
  assert.doesNotMatch(html, /\*\*先观察\*\*/)
})

test('model Markdown cannot execute HTML, javascript links or load remote images', () => {
  const html = renderMarkdown(
    '<script>alert(1)</script>\n\n[运行](javascript:alert(1))\n\n![叶片](https://example.com/tracker.jpg)\n\n[来源](https://example.com/source)',
  )
  assert.doesNotMatch(html, /<script|<img|href="javascript:/i)
  assert.match(html, /&lt;script&gt;/)
  assert.match(html, /rel="noopener noreferrer"/)
})

test('local backend page opens live while Pages remains preview by default', () => {
  assert.deepEqual(resolveConnection({ href: 'http://127.0.0.1:8000/' }), {
    mode: 'live',
    base: 'http://127.0.0.1:8000',
    explicit: false,
  })
  assert.equal(
    resolveConnection({
      href: 'https://chenzhihao-dev.github.io/AgriVision-system/',
      environmentMode: 'preview',
    }).mode,
    'preview',
  )
  assert.equal(resolveConnection({ href: 'http://127.0.0.1:5173/' }).mode, 'preview')
  assert.equal(
    resolveConnection({ href: 'http://127.0.0.1:8000/', savedMode: 'preview' }).mode,
    'preview',
  )
})

test('explicit localhost test entry selects the same-origin backend without accepting arbitrary remote targets', () => {
  assert.deepEqual(
    resolveConnection({
      href: 'http://localhost:8100/?mode=live',
      savedMode: 'preview',
      savedBase: 'http://old.example',
    }),
    { mode: 'live', base: 'http://localhost:8100', explicit: true },
  )
  assert.equal(resolveConnection({ href: 'https://example.com/?mode=live' }).explicit, false)
})

test('automatic image question distinguishes quality failures and conflicting evidence', () => {
  const base = {
    images: [{ id: 'test' }],
    recognition: { outcome: 'quality_check_failed', status: 'needs_retake' },
  }
  assert.match(imageQuestion(base), /画质检查/)
  assert.match(
    imageQuestion({
      ...base,
      recognition: { outcome: 'different_hypotheses', status: 'uncertain' },
    }),
    /分别解释/,
  )
})

test('case drafts stay separate in RAM and clear at the account boundary', () => {
  const drafts = createDraftStore()
  const value = { text: '还没发送的问题', documents: ['doc'], images: ['photo'] }
  drafts.save('case-one', value)
  value.images.push('outside')
  assert.deepEqual(drafts.get('case-two'), { text: '', documents: [], images: [] })
  assert.deepEqual(drafts.get('case-one').images, ['photo'])
  drafts.clear()
  assert.equal(drafts.get('case-one').text, '')
})

test('photo result, chat and inspector pop back one level at a time', () => {
  const { initialPath, showResult, showChat, showInspector, popView } = module.exports
  let path = showResult(initialPath(), 'photo-one')
  path = showChat(path, 'photo-one')
  path = showInspector(path)
  assert.deepEqual(path.layers, ['result', 'chat', 'inspector'])
  path = popView(path)
  assert.deepEqual(path.layers, ['result', 'chat'])
  path = popView(path)
  assert.deepEqual(path.layers, ['result'])
  path = popView(path)
  assert.equal(path.page, 'identify')
  assert.equal(path.caseId, 'photo-one')
  assert.deepEqual(path.layers, [])
})

test('same main tab is a no-op and switching pages keeps the case identity', () => {
  const { initialPath, showResult, selectPage } = module.exports
  const path = showResult(initialPath(), 'photo-one')
  assert.equal(selectPage(path, 'identify'), path)
  const home = selectPage(path, 'home')
  assert.equal(home.caseId, 'photo-one')
  assert.deepEqual(home.layers, [])
})

test('new or historical consultation never inherits another result parent', () => {
  const { initialPath, showResult, showChat, openHistory, popView } = module.exports
  const result = showResult(initialPath(), 'old-photo')
  const next = openHistory(result, 'new-thread')
  assert.deepEqual(next.layers, ['chat'])
  assert.deepEqual(popView(next).layers, [])
  assert.deepEqual(showChat(result, 'different-thread').layers, ['chat'])
  const chat = showChat(result, 'old-photo')
  assert.equal(showChat(chat, 'old-photo'), chat)
})

const assistant = (text, extra = {}) => ({
  role: 'assistant',
  text,
  sources: [],
  products: [],
  provider: 'knowledge',
  ...extra,
})

test('ask-again restores the associated question without issuing or constructing a new request', () => {
  const record = {
    images: [],
    messages: [
      { role: 'user', text: '  小麦叶片发黄怎么办？  ' },
      assistant('建议检查叶背'),
      { role: 'user', text: '接着说说检查方法。' },
      assistant('下一步检查'),
    ],
  }
  assert.equal(questionForAnswer(record, 1), '小麦叶片发黄怎么办？')
  assert.equal(questionForAnswer(record, 3), '接着说说检查方法。')
  assert.equal(questionForAnswer(record, 0), '')
  assert.equal(questionForAnswer(record, 99), '')
})
test('photo responses propose a report question rather than resending upload narration', () => {
  const record = {
    status: 'uncertain',
    images: [{ id: 'photo' }],
    messages: [
      { role: 'user', provider: 'photo', text: '上传了一张小麦照片' },
      assistant('当前线索不确定', { provider: 'recognition' }),
    ],
  }
  assert.match(questionForAnswer(record, 1), /逐张处理回执/)
  assert.deepEqual(suggestedQuestions(record, record.messages[1]), [
    '如何拍清楚症状？',
    '需要补充什么信息？',
  ])
})
test('suggestions respect clarification and medication context', () => {
  const record = { images: [], messages: [] }
  assert.deepEqual(
    suggestedQuestions(record, assistant('请先选择作物', { provider: 'clarification' })),
    [],
  )
  assert.deepEqual(suggestedQuestions(record, assistant('用药请核对标签')), [
    '怎么看农药标签？',
    '用药前需要核对什么？',
  ])
})
test('copied sharing content contains actual answer and public sources without private record links', () => {
  const text = answerShareText(
    assistant('先检查叶片两面。', {
      sources: [
        { title: '公开资料', url: 'https://example.org/agri' },
        { title: '私有图片', url: '/api/images/private-token' },
      ],
    }),
  )
  assert.match(text, /先检查叶片两面/)
  assert.match(text, /https:\/\/example.org\/agri/)
  assert.doesNotMatch(text, /private-token|continued_case_id/)
  assert.doesNotMatch(text, /AI 生成/)
  const generated = assistant('先检查叶片两面。', { provider: 'deepseek' })
  assert.equal(answerCopyText(generated), 'AI 生成\n先检查叶片两面。')
  assert.match(answerShareText(generated), /AI 生成/)
})
