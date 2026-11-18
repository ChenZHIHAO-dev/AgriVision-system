/** Gesture state only; page navigation occurs once, after a held drag is released. */
export interface DockBounds {
  left: number
  top: number
  width: number
  height: number
}
export type DockGesturePhase = 'idle' | 'pressing' | 'dragging' | 'cancelled'
export const DOCK_HOLD_MS = 280
export class DockGesture {
  phase: DockGesturePhase = 'idle'
  preview = 0
  offset = 0
  slotWidth = 0
  private bounds: DockBounds | null = null
  private startedAt = 0
  private startX = 0
  private startY = 0
  private latestX = 0
  private origin = 0

  start(index: number, x: number, y: number, bounds: DockBounds, now: number) {
    if (this.phase !== 'idle' || bounds.width <= 0 || index < 0 || index > 2) return false
    this.bounds = { ...bounds }
    this.slotWidth = bounds.width / 3
    this.phase = 'pressing'
    this.preview = this.origin = index
    this.startX = this.latestX = x
    this.startY = y
    this.startedAt = now
    this.offset = this.slotWidth * index
    return true
  }
  activate(now: number) {
    if (this.phase !== 'pressing' || now - this.startedAt < DOCK_HOLD_MS) return false
    this.phase = 'dragging'
    this.position(this.latestX)
    return true
  }
  move(x: number, y: number, now: number) {
    if (this.phase === 'idle' || this.phase === 'cancelled') return
    this.latestX = x
    this.activate(now)
    if (this.phase === 'pressing' && Math.hypot(x - this.startX, y - this.startY) > 12) {
      this.phase = 'cancelled'
      return
    }
    if (this.phase === 'dragging') this.position(x)
  }
  private position(x: number) {
    this.offset = Math.max(
      0,
      Math.min(this.slotWidth * 2, this.origin * this.slotWidth + x - this.startX),
    )
    this.preview = Math.max(0, Math.min(2, Math.round(this.offset / this.slotWidth)))
  }
  finish(x: number, y: number, now: number) {
    this.move(x, y, now)
    const dragged = this.phase === 'dragging'
    const suppressClick = dragged || this.phase === 'cancelled'
    const bounds = this.bounds
    const inside =
      bounds &&
      x >= bounds.left - 16 &&
      x <= bounds.left + bounds.width + 16 &&
      y >= bounds.top - 30 &&
      y <= bounds.top + bounds.height + 30
    const target = dragged && inside ? this.preview : null
    this.phase = 'idle'
    return { target, suppressClick, dragged }
  }
  cancel() {
    const suppressClick = this.phase !== 'idle'
    this.phase = 'idle'
    return suppressClick
  }
}
