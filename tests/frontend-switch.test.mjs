import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { build } from 'esbuild'
import { compileScript, parse } from '@vue/compiler-sfc'
import { Window } from 'happy-dom'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const compiled = await build({
  stdin: {
    contents:
      "export {default as Picker} from './apps/client/src/components/ModelPicker.vue'; export {createApp,h,ref,nextTick} from 'vue'",
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
      name: 'vue-model-picker',
      setup(builder) {
        builder.onLoad({ filter: /\.vue$/ }, async ({ path: name }) => {
          if (path.basename(name) === 'ChoicePicker.vue')
            return {
              contents:
                "import {h} from 'vue'; export default { setup(_props, {slots}) { return () => h('section', slots.footer?.()) } }",
              loader: 'js',
            }
          const source = await readFile(name, 'utf8')
          const { descriptor } = parse(source, { filename: name })
          const script = compileScript(descriptor, {
            id: 'model-picker-test',
            inlineTemplate: true,
          })
          return { contents: script.content, loader: 'ts', resolveDir: path.dirname(name) }
        })
      },
    },
  ],
})

async function mounted(run) {
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
  const { Picker, createApp, h, ref, nextTick } = module.exports
  const model = ref('deepseek-flash'),
    enabled = ref(false),
    changes = []
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp({
    render: () =>
      h(Picker, {
        modelValue: model.value,
        webSearch: enabled.value,
        'onUpdate:webSearch': (value) => {
          enabled.value = value
          changes.push(value)
        },
      }),
  })
  try {
    app.mount(host)
    await run({ window, host, model, enabled, changes, tick: nextTick })
  } finally {
    app.unmount()
    await window.happyDOM.close()
    for (const [name, descriptor] of previous) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor)
      else delete globalThis[name]
    }
  }
}

test('web search changes only through its right-hand switch, not the description row', () =>
  mounted(async ({ window, host, changes, tick }) => {
    const row = host.querySelector('.model-web-option')
    const toggle = host.querySelector('[role="switch"]')
    assert.equal(row.tagName, 'VIEW')
    assert.equal(row.getAttribute('role'), null)
    row.dispatchEvent(new window.MouseEvent('click', { bubbles: true }))
    host
      .querySelector('.web-caption')
      .dispatchEvent(new window.MouseEvent('click', { bubbles: true }))
    assert.deepEqual(changes, [])
    assert.equal(toggle.getAttribute('aria-checked'), 'false')
    toggle.click()
    await tick()
    assert.deepEqual(changes, [true])
    assert.equal(toggle.getAttribute('aria-checked'), 'true')
    toggle.click()
    await tick()
    assert.deepEqual(changes, [true, false])
  }))

test('Pro exposes a disabled, explained web-search switch and cannot change it', () =>
  mounted(async ({ host, model, changes, tick }) => {
    model.value = 'deepseek-v4-pro'
    await tick()
    const toggle = host.querySelector('[role="switch"]')
    assert.equal(toggle.disabled, true)
    assert.equal(toggle.getAttribute('aria-checked'), 'false')
    assert.equal(toggle.getAttribute('aria-label'), '联网检索')
    const description = host.querySelector('#' + toggle.getAttribute('aria-describedby'))
    assert.match(description.textContent, /支持 DeepSeek Flash/)
    toggle.click()
    await tick()
    assert.deepEqual(changes, [])
  }))
