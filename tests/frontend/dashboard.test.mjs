import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import { compileScript, compileStyle, parse } from '@vue/compiler-sfc'
import { Window } from 'happy-dom'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const compiled = await build({
  stdin: {
    contents:
      "export { default as Dashboard } from './apps/client/src/components/DashboardHome.vue'; export { createApp, h, nextTick, ref } from 'vue'",
    resolveDir: root,
  },
  bundle: true,
  write: false,
  format: 'cjs',
  platform: 'node',
  define: { 'process.env.NODE_ENV': '"production"' },
  plugins: [
    {
      name: 'dashboard-test-components',
      setup(builder) {
        builder.onLoad({ filter: /[\\/]lib[\\/]api\.ts$/ }, () => ({
          contents: 'export const imageUrl = () => ""',
          loader: 'js',
        }))
        builder.onLoad({ filter: /\.vue$/ }, async ({ path: filename }) => {
          const name = path.basename(filename)
          if (name === 'AppIcon.vue')
            return { contents: 'export default { render: () => null }', loader: 'js' }
          if (name === 'KnowledgeLibrary.vue') {
            return {
              contents:
                "import { h } from 'vue'; export default { props: ['section'], render() { return h('section', {'data-library-section': this.section}) } }",
              loader: 'js',
            }
          }
          const { descriptor } = parse(await readFile(filename, 'utf8'), { filename })
          return {
            contents: compileScript(descriptor, {
              id: 'dashboard-record-test',
              inlineTemplate: true,
              templateOptions: {
                compilerOptions: {
                  isCustomElement: (tag) => ['view', 'text', 'scroll-view', 'image'].includes(tag),
                },
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

test('mobile dashboard searches recent records without exposing guest history', async () => {
  const window = new Window()
  window.happyDOM.setWindowSize({ width: 320, height: 640 })
  const environment = new Map()
  for (const name of ['window', 'document', 'Element', 'SVGElement', 'HTMLElement', 'Node']) {
    environment.set(name, Object.getOwnPropertyDescriptor(globalThis, name))
    Object.defineProperty(globalThis, name, {
      value: name === 'window' ? window : window[name],
      configurable: true,
    })
  }

  const proxyQuery = {
    in() {
      return this
    },
    select() {
      return this
    },
    boundingClientRect() {
      return this
    },
    exec(callback) {
      callback([{ height: 540, top: 0 }, { top: 244 }])
    },
  }
  const uni = { getStorageSync: () => '', createSelectorQuery: () => proxyQuery }
  const module = { exports: {} }
  new Function('module', 'exports', 'require', 'uni', compiled.outputFiles[0].text)(
    module,
    module.exports,
    createRequire(import.meta.url),
    uni,
  )
  const { createApp, Dashboard, h, nextTick, ref } = module.exports
  const host = document.createElement('div')
  document.body.append(host)
  const loggedIn = ref(true)
  const section = ref('recent')
  const opened = []
  const records = Array.from({ length: 6 }, (_, index) => ({
    id: String(index),
    title: '叶片识别记录 ' + index,
    conversation_title: index === 5 ? '长期田间观察' : '田间记录 ' + index,
    crop_name: index === 5 ? '花生' : '小麦',
    note: index === 5 ? '北侧试验地' : '',
    updated_at: '2026-11-18T07:00:00Z',
    status: 'identified',
    messages: [],
    images: [],
  }))
  const app = createApp({
    render: () =>
      h(Dashboard, {
        records,
        cards: [],
        loggedIn: loggedIn.value,
        section: section.value,
        mobile: true,
        'onUpdate:section': (value) => (section.value = value),
        onOpen: (id) => opened.push(id),
      }),
  })
  const input = () => host.querySelector('input[aria-label="搜索最近记录"]')
  const rowTitles = () =>
    [...host.querySelectorAll('.dashboard-record-title')].map((el) => el.textContent)
  const search = async (value) => {
    input().value = value
    input().dispatchEvent(new window.Event('input', { bubbles: true }))
    await nextTick()
  }

  try {
    app.mount(host)
    assert.equal(rowTitles().length, 5)
    assert.match(host.textContent, /拍照识别/)
    assert.match(host.textContent, /询问 AI/)
    for (const term of ['花生', '长期田间观察', '北侧试验地']) {
      await search(term)
      assert.deepEqual(rowTitles(), ['长期田间观察'])
    }
    host.querySelector('.dashboard-record').click()
    assert.deepEqual(opened, ['5'])
    window.happyDOM.setWindowSize({ width: 430, height: 820 })
    host.querySelectorAll('[role="tab"]')[1].click()
    await nextTick()
    assert.equal(input(), null)
    assert.equal(
      host.querySelector('[data-library-section]').getAttribute('data-library-section'),
      'library',
    )
    host.querySelectorAll('[role="tab"]')[0].click()
    await nextTick()
    assert.deepEqual(rowTitles(), ['长期田间观察'])

    await search('不存在')
    assert.match(host.querySelector('.dashboard-empty').textContent, /没有匹配记录/)
    loggedIn.value = false
    await nextTick()
    assert.deepEqual(rowTitles(), [])
    assert.equal(input(), null)
    assert.match(host.querySelector('.dashboard-empty').textContent, /登录后查看记录/)
    loggedIn.value = true
    await nextTick()
    assert.equal(input().value, '')
    assert.equal(rowTitles().length, 5)
  } finally {
    app.unmount()
    await window.happyDOM.close()
    for (const [name, descriptor] of environment) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor)
      else delete globalThis[name]
    }
  }
})

test('WeChat dashboard gives the component host a full-width box before laying out its contents', async () => {
  const filename = path.join(root, 'apps/client/src/components/DashboardHome.vue')
  const { descriptor } = parse(await readFile(filename, 'utf8'), { filename })
  const wechatStyle = descriptor.styles.find((style) => style.content.includes('#ifdef MP-WEIXIN'))
  assert.ok(wechatStyle)
  const { code, errors } = compileStyle({
    source: wechatStyle.content,
    filename,
    id: 'dashboard-layout-test',
    scoped: wechatStyle.scoped,
  })
  assert.deepEqual(errors, [])
  const hostRule = code.match(/:host\s*\{([^}]+)\}/)?.[1]
  assert.ok(hostRule, 'the rule must target the native host without a Vue scope qualifier')
  assert.match(hostRule, /(^|;)\s*width:\s*100%;/)
  assert.match(hostRule, /(^|;)\s*min-width:\s*0;/)
})
