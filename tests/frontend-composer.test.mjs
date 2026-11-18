import { test } from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { Window } from 'happy-dom'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const compiled = await build({
  stdin: {
    contents:
      "export {default as Composer} from './apps/client/src/components/NativeChatInput.ts'; export {createApp,h,ref,nextTick} from 'vue'",
    resolveDir: root,
    loader: 'ts',
  },
  bundle: true,
  write: false,
  platform: 'node',
  format: 'cjs',
  define: { 'process.env.NODE_ENV': '"test"' },
})

async function mounted(run) {
  // A local DOM for input-event regression; no browser or network is controlled.
  const window = new Window(),
    previous = new Map()
  for (const name of ['window', 'document', 'Element', 'SVGElement', 'HTMLElement', 'Node']) {
    previous.set(name, Object.getOwnPropertyDescriptor(globalThis, name))
    Object.defineProperty(globalThis, name, {
      value: name === 'window' ? window : window[name],
      configurable: true,
      writable: true,
    })
  }
  const module = { exports: {} }
  new Function('module', 'exports', 'require', compiled.outputFiles[0].text)(
    module,
    module.exports,
    createRequire(import.meta.url),
  )
  const { Composer, createApp, h, ref, nextTick } = module.exports
  const value = ref(''),
    events = { sends: 0, limits: 0 }
  const host = window.document.createElement('div')
  window.document.body.append(host)
  const app = createApp({
    render: () =>
      h(Composer, {
        modelValue: value.value,
        'onUpdate:modelValue': (next) => {
          value.value = next
        },
        onSend: () => events.sends++,
        onLimit: () => events.limits++,
      }),
  })
  try {
    app.mount(host)
    await run({ window, input: host.querySelector('textarea'), value, events, tick: nextTick })
  } finally {
    app.unmount()
    await window.happyDOM.close()
    for (const [name, descriptor] of previous) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor)
      else delete globalThis[name]
    }
  }
}

test('multiline pasted text stays in a native textarea and does not submit', () =>
  mounted(async ({ window, input, value, events, tick }) => {
    const text = '小麦叶片出现斑点，先记录情况。\n\n第二段：最近连续降雨。\n'.repeat(120)
    input.value = text
    input.dispatchEvent(new window.Event('input', { bubbles: true }))
    await tick()
    assert.equal(input.tagName, 'TEXTAREA')
    assert.equal(value.value, text)
    assert.equal(input.value, text)
    assert.equal(input.maxLength, 12000)
    assert.equal(events.sends, 0)
  }))

test('Enter sends once while Shift+Enter and Chinese composition preserve editing', () =>
  mounted(async ({ window, input, events }) => {
    const key = (options) =>
      input.dispatchEvent(
        new window.KeyboardEvent('keydown', {
          key: 'Enter',
          bubbles: true,
          cancelable: true,
          ...options,
        }),
      )
    assert.equal(key({ shiftKey: true }), true)
    key({ isComposing: true })
    input.dispatchEvent(new window.CompositionEvent('compositionstart'))
    key({})
    input.dispatchEvent(new window.CompositionEvent('compositionend'))
    assert.equal(events.sends, 0)
    assert.equal(key({}), false)
    assert.equal(events.sends, 1)
  }))

test('empty content stays one line even when a placeholder reports multiple lines', () =>
  mounted(async ({ window, input, events, tick }) => {
    Object.defineProperty(input, 'scrollHeight', { value: 96, configurable: true })
    window.dispatchEvent(new window.Event('resize'))
    await tick()
    assert.equal(input.style.height, '24px')
    assert.equal(input.style.overflowY, 'hidden')
    assert.equal(events.sends, 0)
  }))

test('actual text grows to eight lines, scrolls thereafter and does not resize for a keyboard', () =>
  mounted(async ({ window, input, tick }) => {
    Object.defineProperty(input, 'scrollHeight', { value: 72, configurable: true })
    input.value = '第一行\n第二行\n第三行'
    input.dispatchEvent(new window.Event('input', { bubbles: true }))
    await tick()
    assert.equal(input.style.height, '72px')
    Object.defineProperty(input, 'scrollHeight', { value: 900, configurable: true })
    input.value = '多行文字\n'.repeat(30)
    input.dispatchEvent(new window.Event('input', { bubbles: true }))
    await tick()
    assert.equal(input.style.height, '192px')
    assert.equal(input.style.overflowY, 'auto')
    window.innerHeight = 300
    window.dispatchEvent(new window.Event('resize'))
    assert.equal(input.style.height, '192px')
    assert.equal(input.style.overflowY, 'auto')
    input.value = ''
    input.dispatchEvent(new window.Event('input', { bubbles: true }))
    await tick()
    assert.equal(input.style.height, '24px')
    assert.equal(input.style.overflowY, 'hidden')
  }))

test('mobile Enter leaves room for a newline and does not submit', () =>
  mounted(async ({ window, input, events }) => {
    window.innerWidth = 390
    input.value = '第一行'
    const uncancelled = input.dispatchEvent(
      new window.KeyboardEvent('keydown', {
        key: 'Enter',
        bubbles: true,
        cancelable: true,
      }),
    )
    assert.equal(uncancelled, true)
    assert.equal(events.sends, 0)
  }))

test('paste warns when the remaining message capacity is exceeded', () =>
  mounted(async ({ window, input, value, events, tick }) => {
    value.value = 'a'.repeat(11995)
    await tick()
    input.setSelectionRange(11995, 11995)
    const clipboardData = new window.DataTransfer()
    clipboardData.setData('text/plain', '新增十个字符12345')
    input.dispatchEvent(new window.ClipboardEvent('paste', { clipboardData, bubbles: true }))
    assert.equal(events.limits, 1)
    assert.equal(events.sends, 0)
  }))
