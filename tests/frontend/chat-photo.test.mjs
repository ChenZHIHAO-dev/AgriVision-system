import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'
import { build } from 'esbuild'
import { compileScript, parse } from '@vue/compiler-sfc'
import { Window } from 'happy-dom'

const root = process.cwd()
const compiled = await build({
  stdin: {
    contents:
      "export { default as Dialog } from './apps/client/src/components/ChatPhotoDialog.vue'; export { chatPhotoContext } from './apps/client/src/lib/chatPhoto.ts'; export { default as CropIdentificationDialog } from './apps/client/src/components/CropIdentificationDialog.vue'; export { default as ScopeDialog } from './apps/client/src/components/RecognitionScopeDialog.vue'; export { default as PhotoCapture } from './apps/client/src/components/PhotoCapture.vue'; export { compactPageHeader, desktopPhotoUpload } from './apps/client/src/lib/platformChrome.ts'; export { createApp, h, ref, nextTick } from 'vue'",
    resolveDir: root,
  },
  bundle: true,
  write: false,
  platform: 'node',
  format: 'cjs',
  define: { 'process.env.NODE_ENV': '"test"' },
  plugins: [
    {
      name: 'photo-context-components',
      setup(builder) {
        builder.onLoad({ filter: /[\\/]lib[\\/]api\.ts$/ }, () => ({
          contents: 'export const imageUrl=()=>""',
          loader: 'js',
        }))
        builder.onLoad({ filter: /\.vue$/ }, async ({ path: filename }) => {
          if (filename.endsWith('AppIcon.vue'))
            return { contents: 'export default { render: () => null }', loader: 'js' }
          if (filename.endsWith('UiDialog.vue'))
            return {
              contents:
                "import {h} from 'vue'; export default {setup(_, {slots}) {return () => h('section', [...(slots.default?.() || []), ...(slots.footer?.() || [])])}}",
              loader: 'js',
            }
          const { descriptor } = parse(await readFile(filename, 'utf8'), { filename })
          return {
            contents: compileScript(descriptor, {
              id: 'chat-photo-test',
              inlineTemplate: true,
              templateOptions: {
                compilerOptions: {
                  isCustomElement: (tag) => ['view', 'text', 'image'].includes(tag),
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

function load() {
  const module = { exports: {} }
  new Function('module', 'exports', 'require', compiled.outputFiles[0].text)(
    module,
    module.exports,
    createRequire(import.meta.url),
  )
  return module.exports
}

test('a new chat photo has no implicit crop and only reuses its own record context', () => {
  const { chatPhotoContext } = load()
  assert.deepEqual(chatPhotoContext(null), { crop: null, stage: '不清楚', variety: '' })
  assert.equal(chatPhotoContext({ crop: null, stage: '苗期', variety: '' }).crop, null)
  assert.deepEqual(chatPhotoContext({ crop: 'maize', stage: '苗期', variety: '品种A' }), {
    crop: 'maize',
    stage: '苗期',
    variety: '品种A',
  })
})

test('compact headers apply only to entry pages, preserving conversation and history controls', () => {
  const { compactPageHeader } = load()
  assert.equal(compactPageHeader('home', false), true)
  assert.equal(compactPageHeader('identify', false), true)
  for (const page of ['home', 'identify', 'history', 'profile', 'knowledge'])
    assert.equal(compactPageHeader(page, true), false)
  assert.equal(compactPageHeader('history', false), false)
})

test('unknown crop dialog requires an explicit choice and offers a text-only exit', async () => {
  const window = new Window()
  const originals = new Map()
  for (const name of ['window', 'document', 'Element', 'SVGElement', 'HTMLElement', 'Node']) {
    originals.set(name, Object.getOwnPropertyDescriptor(globalThis, name))
    Object.defineProperty(globalThis, name, {
      configurable: true,
      value: name === 'window' ? window : window[name],
    })
  }
  const { createApp, h, nextTick, Dialog, ref } = load()
  const chosen = [],
    closed = []
  const visible = ref(true),
    photo = ref('first-photo'),
    busy = ref(false)
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp({
    setup: () => () =>
      visible.value
        ? h(Dialog, {
            photo: photo.value,
            busy: busy.value,
            onConfirm: (crop) => chosen.push(crop),
            onClose: () => closed.push(true),
          })
        : null,
  })
  try {
    app.mount(host)
    const confirm = () => host.querySelector('.button.primary')
    assert.equal(confirm().disabled, true)
    assert.equal(host.querySelectorAll('[aria-pressed="true"]').length, 0)
    assert.deepEqual(
      [...host.querySelectorAll('.photo-crop-choices button')].map((button) =>
        button.textContent.trim(),
      ),
      ['小麦', '玉米', '花生', '黄瓜', '番茄'],
    )
    confirm().click()
    assert.deepEqual(chosen, [])
    host.querySelectorAll('.photo-crop-choices button')[1].click()
    await nextTick()
    assert.equal(confirm().disabled, false)
    confirm().click()
    assert.deepEqual(chosen, ['maize'])
    for (const [index, crop] of [
      [3, 'cucumber'],
      [4, 'tomato'],
    ]) {
      host.querySelectorAll('.photo-crop-choices button')[index].click()
      await nextTick()
      confirm().click()
      assert.equal(chosen.at(-1), crop)
    }
    busy.value = true
    await nextTick()
    assert.equal(confirm().disabled, true)
    busy.value = false
    await nextTick()
    host.querySelector('.button.quiet').click()
    assert.equal(closed.length, 1)
    visible.value = false
    await nextTick()
    photo.value = 'second-photo'
    visible.value = true
    await nextTick()
    assert.equal(confirm().disabled, true)
    assert.equal(host.querySelectorAll('[aria-pressed="true"]').length, 0)
  } finally {
    app.unmount()
    await window.happyDOM.close()
    for (const [name, original] of originals) {
      if (original) Object.defineProperty(globalThis, name, original)
      else delete globalThis[name]
    }
  }
})

test('computer photo upload stays a file picker even when its window becomes narrow', () => {
  const { desktopPhotoUpload } = load()
  for (const platform of ['windows', 'mac', 'linux'])
    assert.equal(desktopPhotoUpload(platform), true)
  for (const platform of ['ios', 'android']) assert.equal(desktopPhotoUpload(platform), false)
})

test('the central photo area and icon activate upload; phone keeps camera and album choices', async () => {
  const window = new Window(),
    originals = new Map()
  for (const name of ['window', 'document', 'Element', 'SVGElement', 'HTMLElement', 'Node']) {
    originals.set(name, Object.getOwnPropertyDescriptor(globalThis, name))
    Object.defineProperty(globalThis, name, {
      configurable: true,
      value: name === 'window' ? window : window[name],
    })
  }
  const { createApp, h, ref, nextTick, PhotoCapture } = load()
  const desktop = ref(true),
    busy = ref(false),
    calls = [],
    scopes = []
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp({
    render: () =>
      h(PhotoCapture, {
        crop: 'wheat',
        models: [],
        busy: busy.value,
        loading: false,
        desktopWeb: desktop.value,
        onCapture: (x) => calls.push(x),
        onScope: (kind) => scopes.push(kind),
      }),
  })
  try {
    app.mount(host)
    const area = host.querySelector('.capture-upload-area')
    host.querySelector('[aria-label="查看小麦识别范围"]').click()
    host.querySelector('[aria-label="查看作物识别范围"]').click()
    assert.deepEqual(scopes, ['disease', 'crop'])
    assert.deepEqual(calls, [])
    assert.equal(area.tagName, 'BUTTON')
    assert.ok(area.getAttribute('aria-label').includes('电脑'))
    area.querySelector('.capture-guide-icon').click()
    area.querySelector('.camera-description').click()
    assert.deepEqual(calls, ['album', 'album'])
    assert.equal(host.querySelector('.album-button'), null)
    assert.equal(
      host.querySelector('.capture-main'),
      null,
      'the main upload action is not duplicated below its card',
    )
    assert.ok(area.textContent.includes('点击选择照片'))
    busy.value = true
    await nextTick()
    assert.equal(area.disabled, true)
    busy.value = false
    desktop.value = false
    await nextTick()
    area.click()
    host.querySelector('.album-button').click()
    assert.deepEqual(calls, ['album', 'album', 'camera', 'album'])
    assert.equal(area.querySelector('button'), null)
  } finally {
    app.unmount()
    await window.happyDOM.close()
    for (const [name, value] of originals)
      value ? Object.defineProperty(globalThis, name, value) : delete globalThis[name]
  }
})

test('confirmed tomato and cucumber enter disease flow only when their own model is ready', async () => {
  const window = new Window(),
    originals = new Map()
  for (const name of ['window', 'document', 'Element', 'SVGElement', 'HTMLElement', 'Node']) {
    originals.set(name, Object.getOwnPropertyDescriptor(globalThis, name))
    Object.defineProperty(globalThis, name, {
      configurable: true,
      value: name === 'window' ? window : window[name],
    })
  }
  const { createApp, h, ref, nextTick, CropIdentificationDialog } = load()
  const crop = ref('tomato'),
    modelReady = ref(false),
    calls = []
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp({
    render: () =>
      h(CropIdentificationDialog, {
        ready: true,
        diagnosisModels: [{ crop: crop.value, ready: modelReady.value }],
        desktopWeb: true,
        busy: false,
        photo: '',
        error: '',
        result: {
          status: 'recognized',
          crop_id: crop.value,
          candidates: [{ id: crop.value, name: crop.value, score: 0.98 }],
        },
        onSelect: (value) => calls.push(value),
      }),
  })
  try {
    app.mount(host)
    assert.equal(host.querySelector('.button.primary'), null)
    assert.equal(host.querySelectorAll('.crop-lookup-manual .button.quiet').length, 5)
    modelReady.value = true
    await nextTick()
    host.querySelector('.button.primary').click()
    assert.equal(calls.at(-1), 'tomato')
    crop.value = 'cucumber'
    await nextTick()
    host.querySelector('.button.primary').click()
    assert.equal(calls.at(-1), 'cucumber')
    crop.value = 'rice'
    await nextTick()
    assert.equal(host.querySelector('.button.primary'), null)
  } finally {
    app.unmount()
    await window.happyDOM.close()
    for (const [name, original] of originals)
      original ? Object.defineProperty(globalThis, name, original) : delete globalThis[name]
  }
})

test('range dialog shows only actual model labels, separates healthy, and explains unavailable scope', async () => {
  const window = new Window(),
    originals = new Map()
  for (const name of ['window', 'document', 'Element', 'SVGElement', 'HTMLElement', 'Node']) {
    originals.set(name, Object.getOwnPropertyDescriptor(globalThis, name))
    Object.defineProperty(globalThis, name, {
      configurable: true,
      value: name === 'window' ? window : window[name],
    })
  }
  const { createApp, h, ref, nextTick, ScopeDialog } = load()
  const kind = ref('disease'),
    model = ref({
      ready: true,
      version: 'fixture',
      experimental: true,
      labels: ['tomato_spot', 'healthy'],
      label_names: { tomato_spot: '测试番茄叶斑', healthy: '健康参考' },
    })
  const host = document.createElement('div')
  document.body.append(host)
  const app = createApp({
    render: () => h(ScopeDialog, { kind: kind.value, title: '范围', model: model.value }),
  })
  try {
    app.mount(host)
    assert.deepEqual(
      [...host.querySelectorAll('.scope-label-list .scope-label')].map((e) => e.textContent),
      ['测试番茄叶斑'],
    )
    assert.deepEqual(
      [...host.querySelectorAll('.scope-label')].map((e) => e.textContent),
      ['测试番茄叶斑', '健康参考'],
    )
    assert.ok(host.textContent.includes('超出范围的照片也可能被误判'))
    model.value = { ...model.value, ready: false }
    await nextTick()
    assert.equal(host.querySelector('.scope-label'), null)
    assert.ok(host.textContent.includes('暂未接入'))
    model.value = { ready: true, version: 'old-backend' }
    await nextTick()
    assert.ok(host.textContent.includes('尚未提供模型类别清单'))
    kind.value = 'crop'
    model.value = {
      ready: true,
      version: 'fixture',
      labels: ['rice', 'grape'],
      label_names: { rice: '水稻', grape: '葡萄' },
    }
    await nextTick()
    assert.deepEqual(
      [...host.querySelectorAll('.scope-label')].map((e) => e.textContent),
      ['水稻', '葡萄'],
    )
    assert.ok(!host.textContent.includes('小麦'))
  } finally {
    app.unmount()
    await window.happyDOM.close()
    for (const [name, original] of originals)
      original ? Object.defineProperty(globalThis, name, original) : delete globalThis[name]
  }
})
