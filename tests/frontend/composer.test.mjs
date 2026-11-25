import { test } from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { readFileSync } from 'node:fs'
import { parse, compileScript } from '@vue/compiler-sfc'
import { Window } from 'happy-dom'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const compiled = await build({
  stdin: {
    contents:
      "export { default as Composer } from './apps/client/src/components/NativeChatInput.ts'; export { createKeyboardHeightTracker } from './apps/client/src/lib/mobileChrome.ts'; export {createApp,h,ref,nextTick} from 'vue'",
    resolveDir: root,
    loader: 'ts',
  },
  bundle: true,
  write: false,
  platform: 'node',
  format: 'cjs',
  define: { 'process.env.NODE_ENV': '"test"' },
})

function nativeSource(source) {
  const enabled = [true]
  return source
    .split('\n')
    .filter((line) => {
      const directive = line.match(/(?:\/\/|<!--|\/\*)\s*#(ifdef|ifndef|endif)\s*(H5)?/)
      if (!directive) return enabled[enabled.length - 1]
      if (directive[1] === 'endif') enabled.pop()
      else enabled.push(enabled[enabled.length - 1] && directive[1] === 'ifndef')
      return false
    })
    .join('\n')
}
const nativeCompiled = await build({
  stdin: {
    contents:
      "export {default as Composer} from './apps/client/src/components/ChatComposer.vue'; export {createApp,h,ref,nextTick} from 'vue'",
    resolveDir: root,
    loader: 'ts',
  },
  bundle: true,
  write: false,
  platform: 'node',
  format: 'cjs',
  define: { 'process.env.NODE_ENV': '"test"' },
  plugins: [
    {
      name: 'native-composer-test',
      setup(build) {
        build.onLoad({ filter: /\.vue$/ }, ({ path: filename }) => {
          if (!filename.endsWith('ChatComposer.vue'))
            return { contents: 'export default {render:()=>null}', loader: 'js' }
          const { descriptor } = parse(nativeSource(readFileSync(filename, 'utf8')))
          const script = compileScript(descriptor, {
            id: 'native-composer-test',
            inlineTemplate: true,
            templateOptions: {
              compilerOptions: {
                isCustomElement: (tag) => ['view', 'text', 'image'].includes(tag),
              },
            },
          })
          return { contents: script.content, loader: 'ts' }
        })
      },
    },
  ],
})

async function mounted(run, native = false) {
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
  new Function(
    'module',
    'exports',
    'require',
    (native ? nativeCompiled : compiled).outputFiles[0].text,
  )(module, module.exports, createRequire(import.meta.url))
  const { Composer, createApp, h, ref, nextTick } = module.exports
  const value = ref(''),
    dark = ref(false),
    events = { sends: 0, limits: 0, keyboards: [] }
  const component = ref(null)
  const host = window.document.createElement('div')
  window.document.body.append(host)
  const app = createApp({
    render: () =>
      h(Composer, {
        ref: component,
        ...(native
          ? {
              model: 'deepseek-flash',
              thinking: false,
              webSearch: false,
              attachments: [],
              images: [],
              dark: dark.value,
            }
          : {}),
        modelValue: value.value,
        'onUpdate:modelValue': (next) => {
          value.value = next
        },
        onSend: () => events.sends++,
        onLimit: () => events.limits++,
        ...(native ? { onKeyboardHeight: (event) => events.keyboards.push(event) } : {}),
      }),
  })
  try {
    app.mount(host)
    await run({
      window,
      host,
      component,
      input: host.querySelector('textarea'),
      value,
      dark,
      events,
      tick: nextTick,
    })
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

test('native textarea owns direct focus without wrapper commands or keyboard-event refocusing', () =>
  mounted(async ({ window, host, input, component, value, events, tick }) => {
    assert.equal(input.hasAttribute('focus'), false)
    assert.equal(typeof input.focus, 'function')
    assert.equal(input.getAttribute('adjust-position'), 'false')
    host
      .querySelector('.composer-writing-area')
      .dispatchEvent(new window.Event('tap', { bubbles: true }))
    component.value.focus()
    await tick()
    await tick()
    assert.notEqual(window.document.activeElement, input)
    // The component reports geometry without writing focus after the native tap.
    input.focus()
    input.dispatchEvent(new window.CustomEvent('focus', { detail: { height: 312 } }))
    for (const detail of [
      { height: 0, duration: 0.19 },
      { height: 312, duration: 0.27 },
      { height: 355, duration: 0.21 },
      { height: 0, duration: 0.26 },
      { height: 312, duration: 0.3 },
    ]) {
      input.dispatchEvent(new window.CustomEvent('keyboardheightchange', { detail }))
    }
    await tick()
    assert.deepEqual(events.keyboards, [
      { height: 312, duration: undefined },
      { height: 0, duration: 0.19 },
      { height: 312, duration: 0.27 },
      { height: 355, duration: 0.21 },
      { height: 0, duration: 0.26 },
      { height: 312, duration: 0.3 },
    ])
    assert.equal(window.document.activeElement, input)
    input.dispatchEvent(new window.CustomEvent('input', { detail: { value: '叶片有斑点' } }))
    await tick()
    assert.equal(value.value, '叶片有斑点')
    input.blur()
    await tick()
    await tick()
    assert.notEqual(window.document.activeElement, input)
    input.focus()
    await tick()
    assert.equal(window.document.activeElement, input)
    assert.equal(input.value, '叶片有斑点')
    assert.equal(events.sends, 0)
  }, true))

test('native multiline editing grows to eight lines and remains editable after keyboard changes', () =>
  mounted(async ({ window, input, value, events, tick }) => {
    input.dispatchEvent(
      new window.CustomEvent('input', { detail: { value: '第一行\n第二行\n第三行' } }),
    )
    input.dispatchEvent(
      new window.CustomEvent('linechange', { detail: { height: 72, lineCount: 3 } }),
    )
    await tick()
    assert.equal(value.value, '第一行\n第二行\n第三行')
    assert.equal(input.style.height, '72px')
    input.dispatchEvent(new window.CustomEvent('keyboardheightchange', { detail: { height: 320 } }))
    assert.equal(input.style.height, '72px')
    input.dispatchEvent(
      new window.CustomEvent('linechange', { detail: { height: 720, lineCount: 30 } }),
    )
    await tick()
    assert.equal(input.style.height, '192px')
    value.value = ''
    await tick()
    await tick()
    assert.equal(input.style.height, '44px')
    assert.equal(events.sends, 0)
  }, true))

function heightTracker(update) {
  const module = { exports: {} }
  new Function('module', 'exports', 'require', compiled.outputFiles[0].text)(
    module,
    module.exports,
    createRequire(import.meta.url),
  )
  return module.exports.createKeyboardHeightTracker(update)
}

test('native keyboard duration wins if reported after a height-only focus event', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const updates = []
  const tracker = heightTracker((height, duration) => updates.push([height, duration]))

  tracker.receive({ height: 312 })
  t.mock.timers.tick(8)
  assert.deepEqual(updates, [])
  tracker.receive({ height: 312, duration: 0.273 })
  assert.deepEqual(updates, [[312, 273]])
  tracker.receive({ height: 312 })
  t.mock.timers.tick(20)
  assert.deepEqual(updates, [[312, 273]])

  tracker.receive({ height: 0 })
  t.mock.timers.tick(10)
  tracker.receive({ height: 0, duration: 0.192 })
  t.mock.timers.tick(15)
  assert.deepEqual(updates, [[312, 273]])
  t.mock.timers.tick(1)
  assert.deepEqual(updates, [
    [312, 273],
    [0, 176],
  ])

  tracker.receive({ height: 312, duration: 0 })
  assert.deepEqual(updates.at(-1), [312, 0])
  tracker.dispose()
})

test('height-only reports use fallback timing and coalesce duplicate dismissal events', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const updates = []
  const tracker = heightTracker((height, duration) => updates.push([height, duration]))

  tracker.receive({ height: 312, duration: -0.1 })
  t.mock.timers.tick(16)
  assert.deepEqual(updates, [[312, 180]])
  tracker.receive({ height: 0 })
  t.mock.timers.tick(32)
  tracker.receive({ height: 0 })
  t.mock.timers.tick(15)
  assert.deepEqual(updates, [[312, 180]])
  t.mock.timers.tick(1)
  assert.deepEqual(updates, [
    [312, 180],
    [0, 180],
  ])
  tracker.dispose()
})

test('fast native dismissal and re-tap do not bounce the composer or resurrect focus', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const updates = []
  const tracker = heightTracker((height, duration) => updates.push([height, duration]))

  tracker.receive({ height: 320, duration: 0.25 })
  tracker.receive({ height: 0, duration: 0.2 })
  t.mock.timers.tick(10)
  tracker.receive({ height: 308, duration: 0.18 })
  t.mock.timers.tick(200)
  assert.deepEqual(updates, [
    [320, 250],
    [308, 180],
  ])
  tracker.receive({ height: Number.NaN })
  tracker.receive({ height: -1 })
  tracker.receive({ height: 0 })
  tracker.dispose()
  t.mock.timers.tick(200)
  tracker.receive({ height: 320 })
  assert.deepEqual(updates, [
    [320, 250],
    [308, 180],
  ])
})

test('native placeholder stays readable when appearance switches', () =>
  mounted(async ({ input, dark, tick }) => {
    const placeholder = input.getAttribute('placeholder')
    assert.ok(placeholder)
    assert.equal(input.getAttribute('placeholder-style'), 'color:#4d5b53;opacity:1')

    dark.value = true
    await tick()
    assert.equal(input.getAttribute('placeholder-style'), 'color:#b4b4b4;opacity:1')
    assert.equal(input.getAttribute('placeholder'), placeholder)

    dark.value = false
    await tick()
    assert.equal(input.getAttribute('placeholder-style'), 'color:#4d5b53;opacity:1')
  }, true))
