export const TOOLBAR_HEIGHT = 46
export const CHROME_SCROLL_THRESHOLD = 80
export function idleChrome(top: number) {
  return top <= CHROME_SCROLL_THRESHOLD ? 0 : TOOLBAR_HEIGHT
}
export function scrollChrome(offset: number, previousTop: number, nextTop: number) {
  const top = Math.max(0, nextTop)
  if (top <= CHROME_SCROLL_THRESHOLD) return { top, offset: 0 }
  const delta = top - Math.max(CHROME_SCROLL_THRESHOLD, previousTop)
  return { top, offset: Math.min(TOOLBAR_HEIGHT, Math.max(0, offset + delta)) }
}
export function safeHeaderTop(status: number, capsuleBottom = 0) {
  return Math.max(0, status, capsuleBottom ? capsuleBottom + 6 : 0)
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
