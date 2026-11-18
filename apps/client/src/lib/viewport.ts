import { viewportFrame } from './mobileChrome'
/** Keep the app canvas stable while the keyboard occludes it; move only input surfaces. */
export function installViewportMetrics() {
  let base = window.innerHeight,
    width = window.innerWidth
  const update = () => {
    const visual = window.visualViewport
    const visible = visual?.height || window.innerHeight,
      top = visual?.offsetTop || 0
    const focused = !!document.activeElement?.matches('input,textarea')
    const mobile = window.innerWidth <= 760
    if (width !== window.innerWidth) {
      width = window.innerWidth
      base = visible + top
    }
    if (!focused && base - visible - top < 110) base = visible + top
    base = Math.max(base, visible + top)
    const frame = viewportFrame(
      base,
      visible,
      top,
      focused || document.documentElement.classList.contains('keyboard-open'),
      mobile,
    )
    const style = document.documentElement.style
    style.setProperty('--app-height', frame.height + 'px')
    style.setProperty('--visual-height', frame.visual + 'px')
    style.setProperty('--keyboard-inset', frame.inset + 'px')
    style.setProperty('--visual-top', frame.top + 'px')
    style.setProperty('--viewport-top', '0px')
    document.documentElement.classList.toggle('keyboard-open', frame.inset > 0)
  }
  window.addEventListener('resize', update)
  window.addEventListener('focusin', update)
  window.addEventListener('focusout', update)
  window.visualViewport?.addEventListener('resize', update)
  window.visualViewport?.addEventListener('scroll', update)
  update()
}
