import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { build } from 'esbuild'
import { compileScript, parse } from '@vue/compiler-sfc'
import { Window } from 'happy-dom'

const result = await build({
  stdin: {
    contents:
      "export {default as Icon} from './apps/client/src/components/AppIcon.vue'; export {setTheme} from './apps/client/src/lib/theme'; export {createApp,h,nextTick} from 'vue'",
    resolveDir: process.cwd(),
    loader: 'js',
  },
  bundle: true,
  platform: 'node',
  format: 'cjs',
  write: false,
  define: { 'import.meta.env.BASE_URL': '"/AgriVision-system/"' },
  plugins: [
    {
      name: 'app-icon-h5',
      setup(build) {
        build.onLoad({ filter: /AppIcon\.vue$/ }, async ({ path }) => {
          const source = (await readFile(path, 'utf8')).replace(
            /<!-- #ifndef H5 -->[\s\S]*?<!-- #endif -->/,
            '',
          )
          const { descriptor } = parse(source, { filename: path })
          const script = compileScript(descriptor, { id: 'app-icon-test', inlineTemplate: true })
          return { contents: script.content, loader: 'ts' }
        })
      },
    },
  ],
})

test('changing appearance replaces old bitmaps for ordinary and primary action icons', async () => {
  const window = new Window()
  const values = {
    window,
    document: window.document,
    Node: window.Node,
    Element: window.Element,
    SVGElement: window.SVGElement,
    uni: { getStorageSync: () => 'dark', setStorageSync() {} },
  }
  const previous = new Map()
  for (const [key, value] of Object.entries(values)) {
    previous.set(key, Object.getOwnPropertyDescriptor(globalThis, key))
    Object.defineProperty(globalThis, key, { value, configurable: true })
  }
  const mod = { exports: {} }
  let app
  try {
    new Function('module', 'exports', result.outputFiles[0].text)(mod, mod.exports)
    const { Icon, setTheme, createApp, h, nextTick } = mod.exports
    const container = window.document.createElement('div')
    window.document.body.append(container)
    app = createApp({
      render: () =>
        h('div', [
          h(Icon, { name: 'upload' }),
          h(Icon, { name: 'camera', white: true }),
          h(Icon, { name: 'leaf', tone: 'white' }),
        ]),
    })
    app.mount(container)
    const icons = () => [...container.querySelectorAll('img')]
    const names = () => icons().map((icon) => icon.src.split('/').pop())
    const [darkUpload, darkCamera, brand] = icons()
    assert.deepEqual(names(), ['upload-dark.png', 'camera-inverse.png', 'leaf-white.png'])

    setTheme('light')
    await nextTick()
    assert.deepEqual(names(), ['upload-light.png', 'camera-white.png', 'leaf-white.png'])
    assert.equal(darkUpload.isConnected, false)
    assert.equal(darkCamera.isConnected, false)
    assert.equal(icons()[2], brand)

    const [lightUpload, lightCamera] = icons()
    setTheme('dark')
    await nextTick()
    assert.deepEqual(names(), ['upload-dark.png', 'camera-inverse.png', 'leaf-white.png'])
    assert.equal(lightUpload.isConnected, false)
    assert.equal(lightCamera.isConnected, false)
  } finally {
    app?.unmount()
    await window.happyDOM.close()
    for (const [key, descriptor] of previous) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor)
      else delete globalThis[key]
    }
  }
})
