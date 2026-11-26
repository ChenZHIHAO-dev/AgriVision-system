import { computed, onMounted, onUnmounted, ref, shallowRef } from 'vue'
import {
  createKeyboardHeightTracker,
  createBrowserViewportTracker,
  createDialogViewportTracker,
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
  const browserFrame = createBrowserViewportTracker()
  const dialogFrame = createDialogViewportTracker()
  let browserFrameRequest = 0
  function syncBrowserViewport() {
    browserFrameRequest = 0
    const visual = window.visualViewport
    width.value = window.innerWidth
    const browser = browserFrame(
      width.value,
      visual?.height ?? window.innerHeight,
      visual?.offsetTop ?? 0,
      !!document.activeElement?.matches('input,textarea'),
      isMobile.value,
    )
    const modal = !!document.querySelector(
      '[data-modal-id],[data-choice-layer],.conversation-drawer-backdrop',
    )
    const frame = dialogFrame(browser, width.value, modal, isMobile.value)
    keyboardHeight.value = frame.inset
    const style = document.documentElement.style
    style.setProperty('--app-height', frame.height + 'px')
    style.setProperty('--viewport-top', frame.backgroundTop + 'px')
    style.setProperty('--visual-height', frame.visual + 'px')
    style.setProperty('--keyboard-inset', frame.inset + 'px')
    style.setProperty('--visual-top', frame.top + 'px')
  }
  // 同一帧内的 blur/focus/resize 只计算一次，避免切换输入框时短暂回退布局。
  function queueBrowserViewport() {
    if (!browserFrameRequest)
      browserFrameRequest = window.requestAnimationFrame(syncBrowserViewport)
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
    window.addEventListener('resize', queueBrowserViewport)
    window.addEventListener('agrivision:modal-change', queueBrowserViewport)
    window.addEventListener('scroll', queueBrowserViewport)
    window.addEventListener('focusin', queueBrowserViewport)
    window.addEventListener('focusout', queueBrowserViewport)
    window.visualViewport?.addEventListener('resize', queueBrowserViewport)
    window.visualViewport?.addEventListener('scroll', queueBrowserViewport)
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
    window.cancelAnimationFrame(browserFrameRequest)
    window.removeEventListener('resize', queueBrowserViewport)
    window.removeEventListener('agrivision:modal-change', queueBrowserViewport)
    window.removeEventListener('scroll', queueBrowserViewport)
    window.removeEventListener('focusin', queueBrowserViewport)
    window.removeEventListener('focusout', queueBrowserViewport)
    window.visualViewport?.removeEventListener('resize', queueBrowserViewport)
    window.visualViewport?.removeEventListener('scroll', queueBrowserViewport)
    // #endif
    // #ifndef H5
    uni.offWindowResize?.(syncNativeViewport)
    uni.offKeyboardHeightChange?.(receiveNativeKeyboard)
    // #endif
  })

  return { isMobile, nativeWindow, keyboardHeight, keyboardDuration, receiveNativeKeyboard }
}
