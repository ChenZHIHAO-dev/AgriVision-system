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
