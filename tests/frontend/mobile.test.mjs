import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { build } from 'esbuild'
import { compileStyle, parse } from '@vue/compiler-sfc'
const output = await build({
  entryPoints: ['apps/client/src/lib/mobileChrome.ts'],
  bundle: true,
  write: false,
  platform: 'node',
  format: 'cjs',
})
const module = { exports: {} }
new Function('module', 'exports', output.outputFiles[0].text)(module, module.exports)
const { viewportFrame, wechatHeaderFrame } = module.exports
test('WeChat header leaves room for two left controls and centers titles clear of the capsule', () => {
  for (const [width, status, capsule] of [
    [430, 54, { left: 337, top: 60, width: 86, height: 32 }],
    [320, 24, { left: 224, top: 31, width: 88, height: 30 }],
  ]) {
    const { top, row, side } = wechatHeaderFrame(width, status, capsule)
    assert.equal(top, status)
    assert.equal(top + row / 2, capsule.top + capsule.height / 2)
    assert.ok(side >= 4 + 2 * 44)
    assert.ok(width - side <= capsule.left - 8)
    assert.ok(width - 2 * side >= 112)
  }
  assert.deepEqual(wechatHeaderFrame(320, 24), { top: 24, row: 44, side: 96 })
  assert.deepEqual(wechatHeaderFrame(320, 24, { left: 0, top: 0, width: 0, height: 0 }), {
    top: 24,
    row: 44,
    side: 96,
  })
})
test('keyboard moves input surfaces without reducing the phone app canvas', () => {
  assert.deepEqual(viewportFrame(844, 480, 0, true, true), {
    height: 844,
    inset: 364,
    visual: 480,
    top: 0,
  })
  assert.deepEqual(viewportFrame(844, 480, 80, true, true), {
    height: 844,
    inset: 284,
    visual: 480,
    top: 80,
  })
  assert.equal(viewportFrame(844, 844, 0, false, true).inset, 0)
  assert.equal(viewportFrame(844, 600, 0, true, false).height, 600)
})

test('WeChat long-dialog scroll area stays between a left-side close control and the footer', async () => {
  const source = await readFile(
    new URL('../../apps/client/src/components/UiDialog.vue', import.meta.url),
    'utf8',
  )
  const { descriptor } = parse(source)
  const { code, errors } = compileStyle({
    id: 'native-dialog-layout',
    filename: 'UiDialog.vue',
    source: descriptor.styles[0].content,
    scoped: descriptor.styles[0].scoped,
  })
  assert.deepEqual(errors, [])
  assert.match(code, /padding-top: calc\(var\(--dialog-safe-top, 0px\) \+ 8px\)/)
  assert.match(code, /padding-bottom: calc\(var\(--dialog-safe-bottom, 0px\) \+ 8px\)/)
  const close = code.match(/\.dialog-close[^{}]*\{([^}]+)\}/)?.[1]
  assert.match(close || '', /order: -1;/)
  assert.match(close || '', /min-height: 44px;/)
  const { content } = descriptor.template
  const body = content.match(/<scroll-view[\s\S]*?<\/scroll-view>/g)
  assert.equal(body?.length, 1)
  assert.match(body[0], /:scroll-y="nativeBodyHeight !== undefined"/)
  assert.match(body[0], /:style="nativeBodyStyle"/)
  assert.doesNotMatch(body[0], /dialog-close|dialog-footer/)
  const closeMarkup = content.match(/<button\s+class="[^"]*dialog-close"[\s\S]+?<\/button>/)?.[0]
  assert.match(closeMarkup || '', /:aria-label="'关闭' \+ title"/)
  assert.match(closeMarkup || '', /<AppIcon name="close"/)
  assert.doesNotMatch(closeMarkup || '', /<text>关闭<\/text>/)
})
