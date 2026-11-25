<script setup lang="ts">
import {
  computed,
  getCurrentInstance,
  nextTick,
  onMounted,
  onUnmounted,
  onUpdated,
  ref,
  watch,
} from 'vue'
import AppIcon from './AppIcon.vue'
import { syncModalInert } from '../lib/modal'
const props = withDefaults(
  defineProps<{
    title: string
    subtitle?: string
    wide?: boolean
    floating?: boolean
    focusTarget?: string
  }>(),
  { subtitle: '', wide: false, floating: false, focusTarget: '' },
)
const emit = defineEmits<{ close: [] }>()
const id = 'dialog-' + Math.random().toString(36).slice(2, 9)
let previous: HTMLElement | null = null,
  revealing = false

// #ifndef H5
const component = getCurrentInstance()?.proxy
const nativeBodyHeight = ref<number>()
const nativeBodyStyle = computed(() =>
  nativeBodyHeight.value === undefined ? undefined : { height: nativeBodyHeight.value + 'px' },
)
const scrollTarget = ref('')
let disposed = false
let measureQueued = false
let remeasureTimer: ReturnType<typeof setTimeout> | undefined

function measureNativeBody() {
  if (!component || !uni.createSelectorQuery || disposed || measureQueued) return
  measureQueued = true
  nextTick(() => {
    if (disposed) return
    const query = uni.createSelectorQuery().in(component)
    query.select('.dialog-frame').boundingClientRect()
    query.select('.dialog-heading').boundingClientRect()
    query.select('.dialog-footer').boundingClientRect()
    query.select('.dialog-body-inner').boundingClientRect()
    query.exec(([frame, heading, footer, content]) => {
      measureQueued = false
      if (disposed || !frame || !heading || !content || frame.height <= 0) return
      // WeChat only needs a fixed scroll-view height while the content overflows.
      const available = Math.max(
        0,
        Math.floor(frame.height - heading.height - (footer?.height || 0) - 2),
      )
      const nextHeight = content.height > available ? available : undefined
      if (nextHeight !== nativeBodyHeight.value) {
        nativeBodyHeight.value = nextHeight
        if (nextHeight !== undefined && props.focusTarget) nativeReveal()
      }
    })
  })
}

function nativeReveal() {
  const target = props.focusTarget
  scrollTarget.value = ''
  nextTick(() => (scrollTarget.value = target))
}
function nativeResize() {
  measureNativeBody()
  if (props.focusTarget) nativeReveal()
  // The page's native keyboard inset settles after the first resize event.
  clearTimeout(remeasureTimer)
  remeasureTimer = setTimeout(measureNativeBody, 180)
}
onUpdated(measureNativeBody)
// #endif

function revealFocus() {
  // #ifdef H5
  if (revealing) return
  revealing = true
  nextTick(() => {
    const root = document.querySelector<HTMLElement>('[data-modal-id="' + id + '"]')
    const target = props.focusTarget
      ? document.getElementById(props.focusTarget)
      : document.activeElement
    if (target && root?.contains(target))
      (target as HTMLElement).scrollIntoView({ block: 'nearest', behavior: 'auto' })
    revealing = false
  })
  // #endif
}
watch(
  () => props.focusTarget,
  () => {
    // #ifdef H5
    revealFocus()
    // #endif
    // #ifndef H5
    nativeResize()
    // #endif
  },
)
function keyboard(event: KeyboardEvent) {
  if (event.defaultPrevented) return
  // #ifdef H5
  if (document.querySelector('[data-choice-layer]')) return
  const dialogs = document.querySelectorAll('[data-modal-id]')
  if (dialogs[dialogs.length - 1]?.getAttribute('data-modal-id') !== id) return
  if (event.key === 'Escape') {
    event.preventDefault()
    emit('close')
    return
  }
  if (event.key !== 'Tab') return
  const root = document.querySelector<HTMLElement>('[data-modal-id="' + id + '"]')
  const targets = Array.from(
    root?.querySelectorAll<HTMLElement>(
      'button:not([disabled]),[tabindex="0"],input,textarea,select,a[href]',
    ) || [],
  ).filter((item) => item.getClientRects().length)
  const first = targets[0],
    last = targets[targets.length - 1]
  if (!first) {
    event.preventDefault()
    root?.focus()
    return
  }
  if (
    event.shiftKey &&
    (document.activeElement === first || !root?.contains(document.activeElement))
  ) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
  // #endif
}
onMounted(async () => {
  // #ifdef H5
  previous = document.activeElement as HTMLElement
  document.addEventListener('keydown', keyboard)
  window.visualViewport?.addEventListener('resize', revealFocus)
  await nextTick()
  syncModalInert()
  document.querySelector<HTMLElement>('[data-modal-id="' + id + '"] .dialog-close')?.focus()
  // #endif
  // #ifndef H5
  nativeResize()
  uni.onKeyboardHeightChange(nativeResize)
  uni.onWindowResize(nativeResize)
  // #endif
})
onUnmounted(() => {
  // #ifdef H5
  document.removeEventListener('keydown', keyboard)
  window.visualViewport?.removeEventListener('resize', revealFocus)
  nextTick(() => {
    syncModalInert()
    if (previous?.isConnected) previous.focus()
  })
  // #endif
  // #ifndef H5
  disposed = true
  clearTimeout(remeasureTimer)
  uni.offKeyboardHeightChange(nativeResize)
  uni.offWindowResize(nativeResize)
  // #endif
})
</script>
<template>
  <view class="dialog-backdrop" :class="{ 'floating-backdrop': floating }">
    <view class="dialog-scrim" aria-hidden="true" @click="emit('close')" />
    <view class="dialog-frame">
      <view
        class="dialog-card"
        :class="{ 'dialog-wide': wide, 'dialog-floating': floating }"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="id"
        :data-modal-id="id"
        tabindex="-1"
      >
        <view class="dialog-heading">
          <view>
            <text :id="id" class="dialog-title">{{ title }}</text>
            <text v-if="subtitle" class="dialog-subtitle">{{ subtitle }}</text>
          </view>
          <button
            class="icon-button dialog-close"
            :aria-label="'关闭' + title"
            @click="emit('close')"
          >
            <AppIcon name="close" :size="19" />
          </button>
        </view>
        <!-- #ifdef H5 -->
        <view class="dialog-body">
          <view class="dialog-body-inner"><slot /></view>
        </view>
        <!-- #endif -->
        <!-- #ifndef H5 -->
        <scroll-view
          :scroll-y="nativeBodyHeight !== undefined"
          class="dialog-body"
          :style="nativeBodyStyle"
          :scroll-into-view="scrollTarget"
        >
          <view class="dialog-body-inner"><slot /></view>
        </scroll-view>
        <!-- #endif -->
        <view v-if="$slots.footer" class="dialog-footer"><slot name="footer" /></view>
      </view>
    </view>
  </view>
</template>

<style scoped>
/* #ifdef MP-WEIXIN || APP-PLUS */
.dialog-backdrop {
  padding-top: calc(var(--dialog-safe-top, 0px) + 8px);
  padding-bottom: calc(var(--dialog-safe-bottom, 0px) + 8px);
  padding-right: 12px;
  padding-left: 12px;
}
.dialog-backdrop .dialog-card {
  border-radius: 22px;
  border-bottom: 1px solid var(--line);
}
.dialog-card .dialog-heading {
  align-items: center;
  justify-content: flex-start;
  gap: 9px;
  padding-top: 14px;
  padding-bottom: 10px;
}
.dialog-heading .dialog-close {
  order: -1;
  min-width: 44px;
  min-height: 44px;
  margin: 0;
}
.dialog-card .dialog-footer {
  padding-top: 10px;
  padding-bottom: 12px;
}
.keyboard-open .dialog-card .dialog-heading {
  padding-top: 4px;
  padding-bottom: 4px;
}
.keyboard-open .dialog-card .dialog-subtitle,
.keyboard-open .dialog-card .dialog-footer :deep(.guest-link) {
  display: none;
}
.keyboard-open .dialog-card .dialog-footer {
  padding-top: 6px;
  padding-bottom: 6px;
}
/* #endif */
/* #ifdef H5 */
@media (max-width: 760px) {
  .dialog-backdrop {
    padding: 10px 12px calc(env(safe-area-inset-bottom, 0px) + 8px);
  }
  .dialog-card {
    border: 1px solid var(--line);
    border-radius: 22px;
  }
}
/* #endif */
</style>
