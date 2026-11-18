import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { build } from 'esbuild'
import { compileScript, parse } from '@vue/compiler-sfc'
import { Window } from 'happy-dom'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const compiled = await build({
  stdin: {
    contents:
      "export { default as Library } from './apps/client/src/components/KnowledgeLibrary.vue'; export { createApp, h, nextTick } from 'vue'",
    resolveDir: repo,
    loader: 'ts',
  },
  bundle: true,
  write: false,
  platform: 'node',
  format: 'cjs',
  define: { 'process.env.NODE_ENV': '"production"' },
  plugins: [
    {
      name: 'library-sfc',
      setup(builder) {
        builder.onLoad({ filter: /\.vue$/ }, async ({ path: name }) => {
          if (path.basename(name) === 'AppIcon.vue')
            return { contents: 'export default { render: () => null }', loader: 'js' }
          const { descriptor } = parse(await readFile(name, 'utf8'), { filename: name })
          const script = compileScript(descriptor, {
            id: 'library-component-test',
            inlineTemplate: true,
            templateOptions: {
              compilerOptions: {
                isCustomElement: (tag) => ['view', 'text', 'scroll-view'].includes(tag),
              },
            },
          })
          return { contents: script.content, loader: 'ts', resolveDir: path.dirname(name) }
        })
      },
    },
  ],
})

test('reading filters remain reachable after scrolling and restart at the first matching card', async () => {
  const window = new Window()
  const previous = new Map()
  for (const name of ['window', 'document', 'Element', 'SVGElement', 'HTMLElement', 'Node']) {
    previous.set(name, Object.getOwnPropertyDescriptor(globalThis, name))
    Object.defineProperty(globalThis, name, {
      value: name === 'window' ? window : window[name],
      configurable: true,
    })
  }

  let settle
  const module = { exports: {} }
  new Function(
    'module',
    'exports',
    'require',
    'uni',
    'setTimeout',
    'clearTimeout',
    compiled.outputFiles[0].text,
  )(
    module,
    module.exports,
    createRequire(import.meta.url),
    { getStorageSync: () => 'grid' },
    (callback, delay) => {
      assert.equal(delay, 1200)
      settle = callback
    },
    () => (settle = undefined),
  )

  const { createApp, h, nextTick, Library } = module.exports
  const host = document.createElement('div')
  document.body.append(host)
  const cards = [
    { id: 'w1', title: '小麦条锈病', crop: 'wheat' },
    { id: 'p1', title: '花生褐斑病', crop: 'peanut' },
    { id: 'm1', title: '玉米大斑病', crop: 'maize' },
  ].map((card) => ({ ...card, summary: '', sources: [], keywords: [] }))
  const app = createApp({ render: () => h(Library, { cards, reading: true }) })
  try {
    app.mount(host)
    const scroller = host.querySelector('scroll-view')
    const controls = host.querySelector('.library-controls')
    const scroll = async (scrollTop) => {
      scroller.dispatchEvent(new window.CustomEvent('scroll', { detail: { scrollTop } }))
      await nextTick()
    }
    const search = host.querySelector('[aria-label="搜索知识与资讯"]')
    assert.ok(search)
    assert.equal(scroller.contains(controls), false)
    assert.equal(controls.getAttribute('aria-hidden'), 'false')

    await scroll(280)
    assert.equal(controls.getAttribute('aria-hidden'), 'true')
    assert.equal(search.isConnected, true)
    await scroll(180)
    assert.equal(controls.getAttribute('aria-hidden'), 'false')
    settle()
    await nextTick()
    assert.equal(controls.getAttribute('aria-hidden'), 'true')

    host.querySelector('.reading-toggle').click()
    await nextTick()
    assert.equal(controls.getAttribute('aria-hidden'), 'false')
    assert.equal(settle, undefined)

    const targets = []
    const observer = new window.MutationObserver((items) => {
      targets.push(...items.map((mutation) => mutation.oldValue))
    })
    observer.observe(scroller, { attributeFilter: ['scroll-top'], attributeOldValue: true })
    const peanut = [...controls.querySelectorAll('.library-filters button')].find((button) =>
      button.textContent.includes('花生'),
    )
    peanut.click()
    await nextTick()
    await nextTick()
    await window.happyDOM.whenAsyncComplete()
    observer.disconnect()
    assert.deepEqual(targets, ['0', '180'])
    assert.equal(scroller.getAttribute('scroll-top'), '0')
    assert.equal(controls.getAttribute('aria-hidden'), 'false')
    assert.equal(peanut.getAttribute('aria-pressed'), 'true')
    assert.deepEqual(
      [...host.querySelectorAll('.library-card-title')].map((title) => title.textContent),
      ['花生褐斑病'],
    )
  } finally {
    app.unmount()
    await window.happyDOM.close()
    for (const [name, descriptor] of previous) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor)
      else delete globalThis[name]
    }
  }
})
