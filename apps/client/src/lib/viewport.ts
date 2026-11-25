import { computed, onMounted, onUnmounted, ref, shallowRef } from 'vue'
import {
  createKeyboardHeightTracker,
  viewportFrame,
  type NativeKeyboardEvent,
} from './mobileChrome'

const MOBILE_WIDTH = 760

export function useWorkspaceViewport() {
  const nativeWindow = shallowRef(uni.getSystemInfoSync())
  const width = ref(nativeWindow.value.windowWidth)
  const keyboardHeight = ref(0)
  const keyboardDuration = ref(0)
  const isMobile = computed(() => {
    // #ifdef APP-PLUS
    return true
    // #endif
    return width.value <= MOBILE_WIDTH
  })
  const keyboard = createKeyboardHeightTracker((height, duration) => {
    keyboardHeight.value = height
    keyboardDuration.value = duration
  })
  const receiveNativeKeyboard = (event: NativeKeyboardEvent) => keyboard.receive(event)

  // #ifdef H5
  let baseline = 0
  function syncBrowserViewport() {
    const visual = window.visualViewport
    const visible = visual?.height ?? window.innerHeight
    const top = visual?.offsetTop ?? 0
    const extent = visible + top
    const editing = !!document.activeElement?.matches('input,textarea')
    if (width.value !== window.innerWidth || (!editing && !keyboardHeight.value)) {
      baseline = extent
    }
    width.value = window.innerWidth
    baseline = Math.max(baseline, extent)
    const frame = viewportFrame(
      baseline,
      visible,
      top,
      editing || keyboardHeight.value > 0,
      isMobile.value,
    )
    keyboardHeight.value = frame.inset
    const style = document.documentElement.style
    style.setProperty('--app-height', frame.height + 'px')
    style.setProperty('--visual-height', frame.visual + 'px')
    style.setProperty('--keyboard-inset', frame.inset + 'px')
    style.setProperty('--visual-top', frame.top + 'px')
  }
  // #endif

  // #ifndef H5
  function syncNativeViewport() {
    const system = uni.getSystemInfoSync()
    if (!keyboardHeight.value || width.value !== system.windowWidth) {
      nativeWindow.value = system
    }
    width.value = system.windowWidth
  }
  // #endif

  onMounted(() => {
    // #ifdef H5
    window.addEventListener('resize', syncBrowserViewport)
    window.addEventListener('focusin', syncBrowserViewport)
    window.addEventListener('focusout', syncBrowserViewport)
    window.visualViewport?.addEventListener('resize', syncBrowserViewport)
    window.visualViewport?.addEventListener('scroll', syncBrowserViewport)
    syncBrowserViewport()
    // #endif
    // #ifndef H5
    syncNativeViewport()
    uni.onWindowResize?.(syncNativeViewport)
    uni.onKeyboardHeightChange?.(receiveNativeKeyboard)
    // #endif
  })

  onUnmounted(() => {
    keyboard.dispose()
    // #ifdef H5
    window.removeEventListener('resize', syncBrowserViewport)
    window.removeEventListener('focusin', syncBrowserViewport)
    window.removeEventListener('focusout', syncBrowserViewport)
    window.visualViewport?.removeEventListener('resize', syncBrowserViewport)
    window.visualViewport?.removeEventListener('scroll', syncBrowserViewport)
    // #endif
    // #ifndef H5
    uni.offWindowResize?.(syncNativeViewport)
    uni.offKeyboardHeightChange?.(receiveNativeKeyboard)
    // #endif
  })

  return { isMobile, nativeWindow, keyboardHeight, keyboardDuration, receiveNativeKeyboard }
}
