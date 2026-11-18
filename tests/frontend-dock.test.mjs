import { test } from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const compiled = await build({
  entryPoints: [path.join(root, 'apps/client/src/lib/dockGesture.ts')],
  bundle: true,
  write: false,
  platform: 'node',
  format: 'cjs',
})
const module = { exports: {} }
new Function('module', 'exports', compiled.outputFiles[0].text)(module, module.exports)
const { DockGesture, DOCK_HOLD_MS } = module.exports
const bounds = { left: 12, top: 770, width: 366, height: 58 }

test('a regular tap leaves navigation to the single native click', () => {
  const gesture = new DockGesture()
  gesture.start(0, 70, 790, bounds, 0)
  const result = gesture.finish(70, 790, 80)
  assert.deepEqual(result, { target: null, suppressClick: false, dragged: false })
  assert.equal(gesture.phase, 'idle')
})

test('long press previews a drag but only release chooses its destination once', () => {
  const gesture = new DockGesture()
  gesture.start(0, 73, 795, bounds, 0)
  assert.equal(gesture.activate(DOCK_HOLD_MS - 1), false)
  assert.equal(gesture.activate(DOCK_HOLD_MS), true)
  gesture.move(195, 795, 340)
  assert.equal(gesture.preview, 1)
  gesture.move(317, 795, 400)
  assert.equal(gesture.preview, 2)
  const release = gesture.finish(317, 795, 450)
  assert.deepEqual(release, { target: 2, suppressClick: true, dragged: true })
  assert.deepEqual(gesture.finish(317, 795, 460), {
    target: null,
    suppressClick: false,
    dragged: false,
  })
})

test('moving before the hold threshold cancels rather than accidentally changing pages', () => {
  const gesture = new DockGesture()
  gesture.start(0, 73, 795, bounds, 0)
  gesture.move(120, 795, 100)
  assert.equal(gesture.phase, 'cancelled')
  assert.equal(gesture.activate(500), false)
  assert.deepEqual(gesture.finish(317, 795, 600), {
    target: null,
    suppressClick: true,
    dragged: false,
  })
})

test('dragging off the navigation bar cancels the selection and suppresses its click', () => {
  const gesture = new DockGesture()
  gesture.start(1, 195, 795, bounds, 0)
  gesture.activate(300)
  assert.deepEqual(gesture.finish(317, 600, 400), {
    target: null,
    suppressClick: true,
    dragged: true,
  })
})

test('pointer cancellation cannot commit after a delayed hold callback', () => {
  const gesture = new DockGesture()
  gesture.start(1, 195, 795, bounds, 0)
  assert.equal(gesture.cancel(), true)
  assert.equal(gesture.activate(400), false)
  assert.equal(gesture.finish(317, 795, 450).target, null)
})

test('small finger jitter preserves a hold, and the glass remains inside the three equal slots', () => {
  const gesture = new DockGesture()
  gesture.start(1, 195, 795, bounds, 0)
  gesture.move(199, 797, 100)
  assert.equal(gesture.activate(280), true)
  assert.equal(gesture.preview, 1)
  gesture.move(-100, 795, 400)
  assert.equal(gesture.offset, 0)
  assert.equal(gesture.preview, 0)
  gesture.move(1000, 795, 450)
  assert.equal(gesture.offset, 244)
  assert.equal(gesture.preview, 2)
})

test('a delayed timer still recognizes a held release, and invalid geometry does not start', () => {
  const gesture = new DockGesture()
  assert.equal(gesture.start(0, 70, 790, { ...bounds, width: 0 }, 0), false)
  gesture.start(2, 317, 795, bounds, 0)
  assert.deepEqual(gesture.finish(317, 795, 350), { target: 2, suppressClick: true, dragged: true })
})
