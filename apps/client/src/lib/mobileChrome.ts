export function wechatHeaderFrame(
  width: number,
  statusHeight: number,
  capsule?: { left: number; top: number; width: number; height: number },
) {
  const top = Math.max(0, statusHeight || 0)
  const valid =
    !!capsule &&
    capsule.width > 0 &&
    capsule.height > 0 &&
    capsule.left > width / 2 &&
    capsule.left + capsule.width <= width &&
    capsule.top >= top &&
    capsule.top <= top + 24
  if (!valid) return { top, row: 44, side: 96 }

  const gap = capsule.top - top
  return {
    top,
    row: Math.max(44, capsule.height + gap * 2),
    side: Math.max(92, width - capsule.left + 8),
  }
}
export function viewportFrame(
  base: number,
  visible: number,
  top: number,
  editing: boolean,
  mobile: boolean,
) {
  const inset = Math.max(0, base - visible - top)
  const keyboard = mobile && editing && inset > 110
  return {
    height: keyboard ? base : visible + top,
    inset: keyboard ? inset : 0,
    visual: visible,
    top,
  }
}

export interface NativeKeyboardEvent {
  height: number
  /** WeChat reports native keyboard animation time in seconds. */
  duration?: number
}

const KEYBOARD_FALLBACK_MS = 180
const KEYBOARD_FRAME_MS = 16
const KEYBOARD_CLOSE_GRACE_MS = 48

export function createKeyboardHeightTracker(update: (height: number, durationMs: number) => void) {
  let height = 0
  let pending: { height: number; durationMs?: number } | undefined
  let timer: ReturnType<typeof setTimeout> | undefined
  let disposed = false

  function clearPending() {
    clearTimeout(timer)
    pending = undefined
    timer = undefined
  }

  function commit(next: number, durationMs: number) {
    clearPending()
    height = next
    update(next, durationMs)
  }

  return {
    receive(event: NativeKeyboardEvent) {
      const next = event.height
      if (disposed || !Number.isFinite(next) || next < 0) return
      const milliseconds = typeof event.duration === 'number' ? event.duration * 1000 : NaN
      const durationMs =
        Number.isFinite(milliseconds) && milliseconds >= 0 ? Math.round(milliseconds) : undefined

      if (next === height) {
        clearPending()
        return
      }
      if (next > 0 && durationMs !== undefined) {
        commit(next, durationMs)
        return
      }
      // A height-only focus or global event can precede the timed native event.
      if (
        pending?.height === next &&
        (pending.durationMs !== undefined || durationMs === undefined)
      )
        return

      clearPending()
      pending = { height: next, durationMs }
      const wait =
        next === 0 && durationMs === undefined ? KEYBOARD_CLOSE_GRACE_MS : KEYBOARD_FRAME_MS
      const transitionMs =
        durationMs === undefined ? KEYBOARD_FALLBACK_MS : Math.max(0, durationMs - wait)
      timer = setTimeout(() => commit(next, transitionMs), wait)
    },
    dispose() {
      disposed = true
      clearPending()
    },
  }
}
