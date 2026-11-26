import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { build } from 'esbuild'
import { compileScript, parse } from '@vue/compiler-sfc'
import { Window } from 'happy-dom'

const compiled = await build({
  stdin: {
    resolveDir: process.cwd(),
    contents: `
    export {default as MobileHeader} from './apps/client/src/components/MobileHeader.vue';
    export {default as WeChatHeader} from './apps/client/src/components/WeChatHeader.vue';
    export {default as WebHeader} from './apps/client/src/components/WebWorkspaceHeader.vue';
    export {default as Settings} from './apps/client/src/components/UserSettings.vue';
    export {default as UserCenter} from './apps/client/src/components/UserCenter.vue';
    export {themeChoice, resolvedTheme} from './apps/client/src/lib/theme';
    export {createApp, h, ref, nextTick} from 'vue';`,
  },
  bundle: true,
  write: false,
  platform: 'node',
  format: 'cjs',
  plugins: [
    {
      name: 'appearance-components',
      setup(builder) {
        builder.onLoad({ filter: /[\\/]lib[\\/]api\.ts$/ }, () => ({
          contents: "export const dataMode=()=> 'preview'",
          loader: 'js',
        }))
        builder.onLoad({ filter: /\.vue$/ }, async ({ path: filename }) => {
          if (/AppIcon|ChatTitle/.test(path.basename(filename)))
            return { contents: 'export default {render:()=>null}', loader: 'js' }
          const source = (await readFile(filename, 'utf8')).replace(
            /<!-- #ifdef MP-WEIXIN -->[\s\S]*?<!-- #endif -->/g,
            '',
          )
          const { descriptor } = parse(source, { filename })
          return {
            contents: compileScript(descriptor, {
              id: 'appearance-test',
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

test('home shortcuts toggle the resolved mode and settings retain system selection', async () => {
  const window = new Window(),
    previous = new Map(),
    stored = []
  const globals = {
    window,
    document: window.document,
    Node: window.Node,
    Element: window.Element,
    SVGElement: window.SVGElement,
    uni: {
      getStorageSync: () => 'system',
      setStorageSync: (key, value) => stored.push([key, value]),
    },
  }
  for (const [key, value] of Object.entries(globals)) {
    previous.set(key, Object.getOwnPropertyDescriptor(globalThis, key))
    Object.defineProperty(globalThis, key, { value, configurable: true })
  }
  let app
  try {
    const module = { exports: {} }
    new Function('module', 'exports', compiled.outputFiles[0].text)(module, module.exports)
    const {
      createApp,
      h,
      ref,
      nextTick,
      themeChoice,
      resolvedTheme,
      MobileHeader,
      WeChatHeader,
      WebHeader,
      Settings,
      UserCenter,
    } = module.exports
    const home = ref(true),
      host = document.createElement('div')
    document.body.append(host)
    app = createApp({
      render: () =>
        h('div', [
          h(MobileHeader, {
            title: '首页',
            page: 'home',
            compact: true,
            chat: false,
            backLabel: '返回',
            safeTop: 0,
            chatOptionsOpen: false,
            historyOpen: false,
            showAppearance: home.value,
          }),
          h(WeChatHeader, {
            title: '首页',
            compact: true,
            chat: false,
            backLabel: '返回',
            showBack: false,
            showHistory: true,
            historyOpen: false,
            optionsOpen: false,
            nativeTitle: false,
            frame: { top: 24, row: 44, side: 96 },
            showAppearance: home.value,
          }),
          h(WebHeader, {
            title: '首页',
            chat: false,
            backLabel: '返回',
            optionsOpen: false,
            showAppearance: home.value,
          }),
          h(Settings),
          h(UserCenter, { user: null, admin: false }),
        ]),
    })
    app.mount(host)
    const switches = () => [...host.querySelectorAll('.appearance-switch')]
    assert.equal(switches().length, 3)
    assert.ok(switches().every((x) => x.textContent.includes('浅色')))
    switches()[0].click()
    await nextTick()
    assert.equal(themeChoice.value, 'dark')
    assert.equal(resolvedTheme.value, 'dark')
    assert.ok(switches().every((x) => x.textContent.includes('深色')))
    assert.equal(host.querySelector('.user-center .appearance-options'), null)
    const modes = [...host.querySelectorAll('.user-settings .appearance-options button')]
    assert.equal(modes.length, 3)
    assert.equal(modes[1].getAttribute('aria-pressed'), 'true')
    modes[2].click()
    await nextTick()
    assert.equal(themeChoice.value, 'system')
    assert.equal(resolvedTheme.value, 'light')
    switches()[1].click()
    await nextTick()
    assert.equal(themeChoice.value, 'dark')
    switches()[2].click()
    await nextTick()
    assert.equal(themeChoice.value, 'light')
    assert.deepEqual(stored.at(-1), ['agrivision.theme', 'light'])
    home.value = false
    await nextTick()
    assert.equal(switches().length, 0)
  } finally {
    app?.unmount()
    await window.happyDOM.close()
    for (const [key, value] of previous)
      value ? Object.defineProperty(globalThis, key, value) : delete globalThis[key]
  }
})
