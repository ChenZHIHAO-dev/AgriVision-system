import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'
import { build } from 'esbuild'
import { parse, compileScript } from '@vue/compiler-sfc'
import { Window } from 'happy-dom'

function browserSource(source) {
  const enabled = [true]
  return source
    .split('\n')
    .filter((line) => {
      const directive = line.match(/(?:\/\/|<!--|\/\*)\s*#(ifdef|ifndef|endif)\s*([^*>\r]*)/)
      if (!directive) return enabled.at(-1)
      if (directive[1] === 'endif') enabled.pop()
      else {
        const h5 = directive[2].includes('H5')
        enabled.push(enabled.at(-1) && (directive[1] === 'ifdef' ? h5 : !h5))
      }
      return false
    })
    .join('\n')
}
const compiled = await build({
  stdin: {
    contents:
      "export {default as AuthDialog} from './apps/client/src/components/AuthDialog.vue'; export {default as ContentReference} from './apps/client/src/components/ContentReference.vue'; export {useWorkspaceViewport} from './apps/client/src/lib/viewport.ts'; export {createBrowserViewportTracker,createDialogViewportTracker} from './apps/client/src/lib/mobileChrome.ts'; export {createApp,h,nextTick} from 'vue'",
    resolveDir: process.cwd(),
  },
  bundle: true,
  write: false,
  platform: 'node',
  format: 'cjs',
  define: { 'process.env.NODE_ENV': '"test"' },
  plugins: [
    {
      name: 'browser-dialog',
      setup(builder) {
        builder.onLoad({ filter: /[\\/]lib[\\/]viewport\.ts$/ }, async ({ path }) => ({
          contents: browserSource(await readFile(path, 'utf8')),
          loader: 'ts',
        }))
        builder.onLoad({ filter: /[\\/]lib[\\/]auth\.ts$/ }, () => ({
          contents: 'export const auth={login:async()=>{throw new Error("test must not submit")}}',
          loader: 'js',
        }))
        builder.onLoad({ filter: /[\\/]lib[\\/]api\.ts$/ }, () => ({
          contents: 'export const dataMode=()=>"live"',
          loader: 'js',
        }))
        builder.onLoad({ filter: /\.vue$/ }, async ({ path: filename }) => {
          if (filename.endsWith('AppIcon.vue'))
            return { contents: 'export default {render:()=>null}', loader: 'js' }
          const { descriptor } = parse(
            browserSource(await readFile(filename, 'utf8')).replaceAll(
              ':focus=',
              ':data-native-focus=',
            ),
          )
          return {
            contents: compileScript(descriptor, {
              id: 'browser-dialog',
              inlineTemplate: true,
              templateOptions: {
                compilerOptions: { isCustomElement: (tag) => ['view', 'text'].includes(tag) },
              },
            }).content,
            loader: 'ts',
            resolveDir: path.dirname(filename),
          }
        })
      },
    },
  ],
})
function load() {
  const module = { exports: {} }
  new Function('module', 'exports', 'require', compiled.outputFiles[0].text)(
    module,
    module.exports,
    createRequire(import.meta.url),
  )
  return module.exports
}
test('browser keyboard preserves its canvas through focus switches and the dismissal tail', () => {
  const { createBrowserViewportTracker } = load()
  for (const [width, height] of [
    [320, 568],
    [375, 812],
  ]) {
    const frame = createBrowserViewportTracker()
    assert.equal(frame(width, height, 0, false, true).height, height)
    for (const visible of [height - 40, height - 100, height - 160, height - 280]) {
      const value = frame(width, visible, 0, true, true)
      assert.equal(value.height, height)
      assert.equal(value.visual, visible)
    }
    // 模拟账号 blur → 密码 focus，以及收起键盘时输入框已不聚焦。
    assert.equal(frame(width, height - 280, 0, false, true).height, height)
    assert.equal(frame(width, height - 260, 0, true, true).height, height)
    for (const visible of [height - 160, height - 105, height - 60, height - 20, height]) {
      assert.equal(frame(width, visible, 0, false, true).height, height)
    }
    assert.equal(frame(width, height, 0, false, true).inset, 0)
    assert.equal(frame(1440, 900, 0, false, false).height, 900)
    assert.equal(frame(1440, 800, 0, false, false).height, 800)
  }
})
test('iOS viewport pan is consumed once without subtracting the keyboard twice', () => {
  const { createBrowserViewportTracker } = load()
  const frame = createBrowserViewportTracker()
  frame(375, 812, 0, false, true)
  assert.deepEqual(frame(375, 440, 60, true, true), {
    height: 812,
    visual: 440,
    top: 60,
    inset: 312,
  })
  assert.equal(frame(375, 720, 0, false, true).height, 812)
  assert.equal(frame(375, 812, 0, false, true).inset, 0)
})

async function mounted(run) {
  const window = new Window(),
    originals = new Map()
  for (const name of [
    'window',
    'document',
    'Element',
    'HTMLElement',
    'HTMLInputElement',
    'SVGElement',
    'Node',
    'uni',
  ]) {
    originals.set(name, Object.getOwnPropertyDescriptor(globalThis, name))
    Object.defineProperty(globalThis, name, {
      value:
        name === 'uni'
          ? { getSystemInfoSync: () => ({ windowWidth: 375, windowHeight: 812 }) }
          : name === 'window'
            ? window
            : window[name],
      configurable: true,
    })
  }
  window.innerWidth = 375
  window.innerHeight = 812
  const visual = new window.EventTarget()
  Object.assign(visual, { height: 812, offsetTop: 0 })
  Object.defineProperty(window, 'visualViewport', { value: visual, configurable: true })
  const api = load()
  const host = document.createElement('div')
  host.className = 'av-app'
  document.body.append(host)
  let viewport
  const app = api.createApp({
    setup() {
      viewport = api.useWorkspaceViewport()
      return () => api.h(api.AuthDialog)
    },
  })
  try {
    app.mount(host)
    await api.nextTick()
    await run({ ...api, window, host, visual, viewport })
  } finally {
    app.unmount()
    await api.nextTick()
    await window.happyDOM.close()
    for (const [name, value] of originals)
      value ? Object.defineProperty(globalThis, name, value) : delete globalThis[name]
  }
}
test('account switching only scrolls modal contents and does not refocus after blur', async () => {
  await mounted(async ({ window, host, visual, nextTick }) => {
    const body = host.querySelector('.dialog-body')
    const username = host.querySelector('#auth-username'),
      password = host.querySelector('#auth-password')
    let pageScrolls = 0
    window.HTMLElement.prototype.scrollIntoView = () => {
      pageScrolls++
    }
    window.scrollTo = () => {
      pageScrolls++
    }
    Object.defineProperty(body, 'clientHeight', { value: 200, writable: true })
    Object.defineProperty(body, 'scrollHeight', { value: 600 })
    body.getBoundingClientRect = () => ({ top: 100, bottom: 300 })
    username.getBoundingClientRect = () => ({
      top: 160 - body.scrollTop,
      bottom: 204 - body.scrollTop,
    })
    password.getBoundingClientRect = () => ({
      top: 420 - body.scrollTop,
      bottom: 464 - body.scrollTop,
    })
    for (let i = 0; i < 3; i++) {
      username.focus()
      await nextTick()
      await nextTick()
      assert.equal(document.activeElement, username)
      password.focus()
      await nextTick()
      await nextTick()
      for (let n = 0; n < 6; n++) {
        visual.dispatchEvent(new window.Event('resize'))
        await nextTick()
        await nextTick()
      }
      assert.equal(document.activeElement, password)
      assert.equal(body.scrollTop, 176)
      assert.equal(password.getAttribute('data-native-focus'), 'false')
    }
    password.blur()
    await nextTick()
    const scroll = body.scrollTop
    visual.dispatchEvent(new window.Event('resize'))
    await nextTick()
    await nextTick()
    assert.notEqual(document.activeElement, password)
    assert.equal(body.scrollTop, scroll)
    body.clientHeight = 40
    password.focus()
    await nextTick()
    await nextTick()
    const clippedScroll = body.scrollTop
    for (let n = 0; n < 4; n++) {
      visual.dispatchEvent(new window.Event('resize'))
      await nextTick()
      await nextTick()
      assert.equal(body.scrollTop, clippedScroll)
    }
    assert.equal(pageScrolls, 0)
    assert.ok(host.querySelector('.dialog-close'))
    assert.ok(host.querySelector('.dialog-footer .auth-submit'))
  })
})
test('answer notices identify AI, recognition and offline reference content honestly', async () => {
  await mounted(async ({ ContentReference, createApp, h, nextTick, host }) => {
    for (const [kind, text] of [
      ['ai', 'AI 生成内容，仅供参考，请结合实际情况判断。'],
      ['recognition', '识别结果仅供参考，请结合实际情况判断。'],
      ['reference', '资料与建议仅供参考，请结合实际情况判断。'],
    ]) {
      const target = document.createElement('div')
      host.append(target)
      const app = createApp({ render: () => h(ContentReference, { kind }) })
      app.mount(target)
      await nextTick()
      assert.equal(target.querySelector('[role="note"]').textContent, text)
      app.unmount()
    }
  })
})

test('modal keyboard and native pan leave the workspace canvas and keyboard state unchanged', async () => {
  await mounted(async ({ window, visual, viewport }) => {
    const settle = () => new Promise((resolve) => setTimeout(resolve, 30))
    await settle()
    const style = document.documentElement.style
    assert.equal(style.getPropertyValue('--app-height'), '812px')
    assert.ok(document.documentElement.classList.contains('dialog-viewport-locked'))
    for (const [height, top] of [
      [700, 0],
      [500, 0],
      [440, 60],
      [430, 72],
      [600, 20],
      [812, 0],
    ]) {
      visual.height = height
      visual.offsetTop = top
      visual.dispatchEvent(new window.Event('resize'))
      visual.dispatchEvent(new window.Event('scroll'))
      await settle()
      assert.equal(style.getPropertyValue('--app-height'), '812px')
      assert.equal(style.getPropertyValue('--visual-height'), height + 'px')
      assert.equal(style.getPropertyValue('--viewport-top'), top + 'px')
      assert.equal(style.getPropertyValue('--keyboard-inset'), '0px')
      assert.equal(viewport.keyboardHeight.value, 0)
    }
  })
})

test('modal background isolation holds through close animation and supports orientation changes', () => {
  const { createDialogViewportTracker } = load()
  for (const [width, height] of [
    [320, 568],
    [375, 812],
  ]) {
    const isolate = createDialogViewportTracker()
    const frame = (visible, top = 0) => ({
      height,
      visual: visible,
      top,
      inset: height - visible - top,
    })
    isolate(frame(height), width, false, true)
    isolate(frame(height), width, true, true)
    const panned = isolate(frame(300, 50), width, true, true)
    assert.equal(panned.height, height)
    assert.equal(panned.backgroundTop, 50)
    assert.equal(panned.inset, 0)
    assert.equal(isolate(frame(height - 40), width, false, true).height, height)
    assert.equal(isolate(frame(height), width, false, true).backgroundTop, 0)
    const rotated = isolate({ height: 375, visual: 375, top: 0, inset: 0 }, 812, true, false)
    assert.equal(rotated.height, 375)
  }
})
