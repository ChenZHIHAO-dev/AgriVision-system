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
const { safeHeaderTop, viewportFrame } = module.exports
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
