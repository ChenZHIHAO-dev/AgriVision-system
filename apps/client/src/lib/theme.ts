import { computed, ref, watch } from 'vue'
export type ThemeChoice = 'system' | 'light' | 'dark'
export const themeChoice = ref<ThemeChoice>(
  (uni.getStorageSync('agrivision.theme') as ThemeChoice) || 'system',
)
const systemDark = ref(false)
export const resolvedTheme = computed(() =>
  themeChoice.value === 'system' ? (systemDark.value ? 'dark' : 'light') : themeChoice.value,
)
export function setTheme(value: ThemeChoice) {
  themeChoice.value = value
  uni.setStorageSync('agrivision.theme', value)
}
export function observeSystemTheme() {
  // #ifdef H5
  const media = window.matchMedia('(prefers-color-scheme: dark)')
  const update = () => {
    systemDark.value = media.matches
  }
  update()
  media.addEventListener('change', update)
  const stop = watch(
    resolvedTheme,
    (value) => {
      if (typeof document === 'undefined') return
      document.documentElement.style.colorScheme = value
      document
        .querySelector('meta[name="theme-color"]')
        ?.setAttribute('content', value === 'dark' ? '#151917' : '#e9edeb')
    },
    { immediate: true, flush: 'sync' },
  )
  return () => {
    media.removeEventListener('change', update)
    stop()
  }
  // #endif
  // #ifndef H5
  systemDark.value = uni.getSystemInfoSync().theme === 'dark'
  const updateNative = (event: { theme: string }) => {
    systemDark.value = event.theme === 'dark'
  }
  uni.onThemeChange(updateNative)
  return () => uni.offThemeChange(updateNative)
  // #endif
}
