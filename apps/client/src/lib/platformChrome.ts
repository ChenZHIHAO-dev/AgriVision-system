/** 平台安全区只在这里换算；页面组件负责内容，不再各自叠加导航留白。 */
import { computed, type Ref } from 'vue'
import type { MainPage } from './navigation'
import { wechatHeaderFrame } from './mobileChrome'

export function compactPageHeader(page: MainPage, chat: boolean) {
  return !chat && (page === 'home' || page === 'identify')
}

export function usePlatformChrome(
  nativeWindow: Readonly<Ref<ReturnType<typeof uni.getSystemInfoSync>>>,
  isMobile: Readonly<Ref<boolean>>,
  page: Readonly<Ref<MainPage>>,
  chat: Readonly<Ref<boolean>>,
) {
  const mobileSafeTop = computed(() => {
    // #ifdef APP-PLUS
    return nativeWindow.value.statusBarHeight || 0
    // #endif
    return 0
  })
  const nativeBottomInset = computed(() => {
    const system = nativeWindow.value
    if (system.platform === 'windows') return 0
    return Math.max(
      0,
      system.safeAreaInsets?.bottom ??
        (system.safeArea ? system.screenHeight - system.safeArea.bottom : 0),
    )
  })
  const nativeWeChatTitle = computed(() => {
    // #ifdef MP-WEIXIN
    return nativeWindow.value.platform === 'windows'
    // #endif
    return false
  })
  const wechatFrame = computed(() => {
    // #ifdef MP-WEIXIN
    const { windowWidth, statusBarHeight } = nativeWindow.value
    return nativeWeChatTitle.value
      ? wechatHeaderFrame(windowWidth, 0)
      : wechatHeaderFrame(
          windowWidth,
          statusBarHeight || 0,
          uni.getMenuButtonBoundingClientRect?.(),
        )
    // #endif
    return { top: 0, row: 0, side: 0 }
  })
  const wechatCapsuleInset = computed(() => {
    // #ifdef MP-WEIXIN
    return nativeWeChatTitle.value ? 0 : Math.max(0, wechatFrame.value.side - 16)
    // #endif
    return 0
  })
  const profilePageStyle = computed(() => {
    if (chat.value || page.value !== 'profile') return undefined
    // #ifdef MP-WEIXIN
    return { paddingTop: wechatFrame.value.top + 4 + 'px' }
    // #endif
    // #ifndef MP-WEIXIN
    if (isMobile.value) return { paddingTop: 'calc(16px + var(--mobile-safe-top, 0px))' }
    // #endif
    return undefined
  })
  const drawerSafeTop = computed(() => {
    // #ifdef MP-WEIXIN
    return nativeWeChatTitle.value ? 0 : wechatFrame.value.top + wechatFrame.value.row
    // #endif
    return mobileSafeTop.value
  })
  const desktopCapture = computed(() => {
    // #ifdef H5
    return !isMobile.value
    // #endif
    return false
  })
  const compactHeader = computed(() => compactPageHeader(page.value, chat.value))
  return {
    mobileSafeTop,
    nativeBottomInset,
    nativeWeChatTitle,
    wechatFrame,
    wechatCapsuleInset,
    profilePageStyle,
    drawerSafeTop,
    desktopCapture,
    compactHeader,
  }
}
