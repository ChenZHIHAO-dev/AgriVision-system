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
    height: mobile && editing ? base : visible + top,
    inset: keyboard ? inset : 0,
    visual: visible,
    top,
  }
}

/** 跟踪一次浏览器键盘会话：账号切到密码、blur 以及收键盘尾段都保留原画布。 */
export function createBrowserViewportTracker() {
  let baseline = 0
  let previousWidth = 0
  let keyboardSession = false
  return (width: number, visible: number, top: number, editing: boolean, mobile: boolean) => {
    const extent = visible + top
    if (width !== previousWidth) {
      baseline = extent
      keyboardSession = false
    } else if (!editing && !keyboardSession) {
      baseline = extent
    }
    previousWidth = width
    baseline = Math.max(baseline, extent)
    if (mobile && editing && baseline - extent > 110) keyboardSession = true
    if (!mobile || extent >= baseline - 1) keyboardSession = false
    return viewportFrame(baseline, visible, top, editing || keyboardSession, mobile)
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

/** 弹窗只缩放自身。背景沿用打开前的画布，补偿 iOS 原生视口平移而不缩放内容。 */
export function createDialogViewportTracker() {
  let lockedHeight = 0
  let lockedWidth = 0
  let lastHeight = 0
  let active = false
  return (
    frame: ReturnType<typeof viewportFrame>,
    width: number,
    modal: boolean,
    mobile: boolean,
  ) => {
    if (mobile && modal && (!active || width !== lockedWidth)) {
      lockedHeight = width === lockedWidth && lastHeight ? lastHeight : frame.height
      lockedWidth = width
      active = true
    }
    // 关闭弹窗时，键盘动画可能尚未结束；到视口恢复后才释放背景。
    if (active && (!mobile || (!modal && frame.visual + frame.top >= lockedHeight - 1)))
      active = false
    const value = active
      ? { ...frame, height: lockedHeight, inset: 0, backgroundTop: frame.top }
      : { ...frame, backgroundTop: 0 }
    lastHeight = value.height
    lockedWidth = width
    return value
  }
}
