import { test } from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
const output = await build({
  entryPoints: ['apps/client/src/lib/mobileChrome.ts'],
  bundle: true,
  write: false,
  platform: 'node',
  format: 'cjs',
})
const module = { exports: {} }
new Function('module', 'exports', output.outputFiles[0].text)(module, module.exports)
const { scrollChrome, safeHeaderTop, viewportFrame, idleChrome } = module.exports
test('top and shallow scroll retain tools; only deeper scrolling tucks by distance', () => {
  assert.equal(scrollChrome(46, 200, 0).offset, 0)
  assert.equal(scrollChrome(0, 0, 40).offset, 0)
  assert.equal(idleChrome(0), 0)
  assert.equal(idleChrome(80), 0)
  assert.equal(idleChrome(120), 46)
  let state = scrollChrome(0, 0, 100)
  assert.equal(state.offset, 20)
  state = scrollChrome(state.offset, state.top, 200)
  assert.equal(state.offset, 46)
  state = scrollChrome(state.offset, state.top, 180)
  assert.equal(state.offset, 26)
})
test('WeChat capsule and status bar cannot overlap the app header', () => {
  assert.equal(safeHeaderTop(44, 76), 82)
  assert.equal(safeHeaderTop(24), 24)
  assert.equal(safeHeaderTop(0), 0)
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
