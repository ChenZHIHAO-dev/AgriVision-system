import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { build } from 'esbuild'
import { compileScript, parse } from '@vue/compiler-sfc'
import { Window } from 'happy-dom'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const compiled = await build({
  stdin: {
    contents:
      "export {default as Dock} from './apps/client/src/components/NavigationDock.vue'; export {createApp,h,ref,nextTick} from 'vue'",
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
      name: 'vue-dock-component',
      setup(builder) {
        builder.onLoad({ filter: /\.vue$/ }, async ({ path: name }) => {
          if (path.basename(name) === 'AppIcon.vue')
            return {
              contents:
                "import {h} from 'vue'; export default { props:['name'], setup(props) { return () => h('span',{'aria-hidden':'true'},props.name) } }",
              loader: 'js',
            }
          // This harness exercises the H5 event bindings, not the native selector API.
          const source = (await readFile(name, 'utf8')).replace(
            /\/\/ #ifndef H5[\s\S]*?\/\/ #endif/g,
            '',
          )
          const { descriptor } = parse(source, { filename: name })
          const script = compileScript(descriptor, {
            id: 'dock-component-test',
            inlineTemplate: true,
            templateOptions: {
              compilerOptions: { isCustomElement: (tag) => ['view', 'text'].includes(tag) },
            },
          })
          return { contents: script.content, loader: 'ts', resolveDir: path.dirname(name) }
        })
      },
    },
  ],
})

function timerClock() {
  let now = 10000,
    next = 0
  const tasks = new Map()
  return {
    Date: class extends Date {
      static now() {
        return now
      }
    },
    setTimeout(callback, delay = 0) {
      const id = ++next
      tasks.set(id, { at: now + delay, callback })
      return id
    },
    clearTimeout(id) {
      tasks.delete(id)
    },
    advance(ms) {
      const end = now + ms
      while (true) {
        const task = [...tasks]
          .filter(([, item]) => item.at <= end)
          .sort((a, b) => a[1].at - b[1].at)[0]
        if (!task) break
        now = task[1].at
        tasks.delete(task[0])
        task[1].callback()
      }
      now = end
    },
  }
}

async function mounted(run) {
  // Isolated unit DOM; no browser, user tab, network or native window is controlled.
  const window = new Window(),
    previous = new Map(),
    clock = timerClock()
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
    'setTimeout',
    'clearTimeout',
    'Date',
    'uni',
    compiled.outputFiles[0].text,
  )(
    module,
    module.exports,
    createRequire(import.meta.url),
    clock.setTimeout,
    clock.clearTimeout,
    clock.Date,
    { getStorageSync: () => 'light' },
  )
  const { Dock, createApp, h, ref, nextTick } = module.exports
  const active = ref('identify'),
    hidden = ref(false),
    changes = []
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp({
    render: () =>
      h(Dock, {
        active: active.value,
        keyboardOpen: hidden.value,
        onNavigate: (page) => {
          changes.push(page)
          active.value = page
        },
      }),
  })
  try {
    app.mount(host)
    const bar = host.querySelector('.av-dock')
    bar.querySelector('.dock-tabs').getBoundingClientRect = () => ({
      left: 12,
      top: 776,
      width: 366,
      height: 58,
      right: 378,
      bottom: 834,
      x: 12,
      y: 776,
      toJSON() {
        return {}
      },
    })
    const point = (target, type, x = 73, y = 795, pointerType = 'mouse', pointerId = 9) =>
      target.dispatchEvent(
        new window.PointerEvent('pointer' + type, {
          isPrimary: true,
          pointerId,
          pointerType,
          bubbles: true,
          cancelable: true,
          button: 0,
          clientX: x,
          clientY: y,
        }),
      )
    await run({
      window,
      host,
      bar,
      buttons: [...bar.querySelectorAll('button')],
      changes,
      clock,
      tick: nextTick,
      point,
      hidden,
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

test('actual dock renders held glass and commits one release destination, ignoring the trailing click', () =>
  mounted(async ({ window, host, bar, buttons, changes, clock, tick, point }) => {
    point(buttons[0], 'down')
    clock.advance(279)
    await tick()
    assert.equal(host.querySelector('.dock-glass'), null)
    clock.advance(1)
    await tick()
    assert.ok(host.querySelector('.dock-glass'))
    assert.equal(bar.classList.contains('is-dragging'), true)
    point(window, 'move', 317, 795)
    await tick()
    assert.equal(buttons[2].classList.contains('drag-preview'), true)
    assert.deepEqual(changes, [])
    point(window, 'up', 317, 795)
    await tick()
    assert.deepEqual(changes, ['profile'])
    assert.equal(buttons[2].getAttribute('aria-current'), 'page')
    assert.ok(host.querySelector('.dock-glass.settling'))
    buttons[0].click()
    await tick()
    assert.deepEqual(changes, ['profile'])
    clock.advance(460)
    await tick()
    assert.equal(host.querySelector('.dock-glass'), null)
  }))

test('actual dock cancels a vertical swipe or a held pointer leaving the page without navigation', () =>
  mounted(async ({ window, host, buttons, changes, clock, tick, point }) => {
    point(buttons[0], 'down')
    clock.advance(100)
    point(window, 'move', 74, 754)
    clock.advance(300)
    point(window, 'up', 195, 795)
    buttons[0].click()
    await tick()
    assert.deepEqual(changes, [])
    assert.equal(host.querySelector('.dock-glass'), null)
    // A genuinely new press must not inherit the previous click suppression.
    point(buttons[0], 'down')
    clock.advance(280)
    await tick()
    assert.ok(host.querySelector('.dock-glass'))
    document.dispatchEvent(new window.MouseEvent('mouseleave'))
    point(window, 'up', 317, 795)
    buttons[0].click()
    await tick()
    assert.deepEqual(changes, [])
    clock.advance(460)
    await tick()
    assert.equal(host.querySelector('.dock-glass'), null)
  }))

test('actual dock ordinary mouse tap still switches immediately once', () =>
  mounted(async ({ window, buttons, changes, clock, tick, point }) => {
    point(buttons[0], 'down')
    clock.advance(50)
    point(window, 'up')
    buttons[0].click()
    await tick()
    assert.deepEqual(changes, ['home'])
    assert.equal(buttons[0].getAttribute('aria-current'), 'page')
  }))

test('an intentional touch drag follows the finger across the three tabs before the hold timer', () =>
  mounted(async ({ window, host, buttons, changes, clock, tick, point }) => {
    point(buttons[1].querySelector('span'), 'down', 240, 795, 'touch')
    clock.advance(60)
    point(window, 'move', 260, 795, 'touch')
    await tick()
    assert.ok(host.querySelector('.dock-glass'))
    assert.equal(buttons[2].classList.contains('drag-preview'), true)
    assert.deepEqual(changes, [])
    point(window, 'move', 110, 795, 'touch')
    await tick()
    assert.equal(buttons[0].classList.contains('drag-preview'), true)
    point(window, 'up', 110, 795, 'touch')
    await tick()
    assert.deepEqual(changes, ['home'])
    assert.equal(buttons[0].getAttribute('aria-current'), 'page')
    clock.advance(320)
    await tick()
    assert.equal(host.querySelector('.dock-glass'), null)
  }))
