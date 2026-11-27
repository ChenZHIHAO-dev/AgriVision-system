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
import { revealDialogInput } from '../lib/dialogFocus'
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
let bodyObserver: ResizeObserver | undefined
let previous: HTMLElement | null = null,
  revealing = false

// #ifndef H5
const component = getCurrentInstance()?.proxy
const nativeBodyHeight = ref<number>()
const nativeBodyStyle = computed(() =>
  nativeBodyHeight.value === undefined ? undefined : { height: nativeBodyHeight.value + 'px' },
)
const nativeScrollTop = ref(0)
let disposed = false
let measureQueued = false
let revealAfterMeasure = false

function measureNativeBody(reveal = false) {
  revealAfterMeasure ||= reveal
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
      const changed = nextHeight !== nativeBodyHeight.value
      const shouldReveal = revealAfterMeasure || changed
      revealAfterMeasure = false
      if (changed) {
        nativeBodyHeight.value = nextHeight
      }
      if (shouldReveal && nextHeight !== undefined && props.focusTarget) nextTick(nativeReveal)
    })
  })
}

function nativeReveal() {
  const target = props.focusTarget
  if (!component || !target || nativeBodyHeight.value === undefined) return
  const query = uni.createSelectorQuery().in(component)
  query.select('.dialog-body').boundingClientRect()
  query.select('#' + target).boundingClientRect()
  query.select('.dialog-body').scrollOffset(() => {})
  query.exec(([body, field, offset]) => {
    if (disposed || target !== props.focusTarget || !body || !field) return
    // 已可见的账号/密码切换不滚动；只有真正被正文裁切时才请求原生滚动。
    // 只补足被遮挡的距离，不把每个输入框强行对齐到正文顶端。
    const delta =
      field.top < body.top
        ? field.top - body.top
        : field.bottom > body.bottom
          ? field.bottom - body.bottom
          : 0
    if (delta && offset) nativeScrollTop.value = Math.max(0, offset.scrollTop + delta)
  })
}
function nativeResize() {
  measureNativeBody(true)
}
function nativeScroll(event: { detail: { scrollTop: number } }) {
  // 与原生真实位置同步；用户手动滚回后，同一个避让目标也能再次下发。
  // 单纯滚动不触发焦点避让，否则会把用户主动滚动又拉回去。
  nativeScrollTop.value = event.detail.scrollTop
}
onUpdated(() => measureNativeBody())
// #endif

function nativeTransitionFinished() {
  // #ifndef H5
  // CSS 使用系统键盘时长；动画结束后按最终正文高度检查输入框，不用固定延时猜测。
  nativeResize()
  // #endif
}
function revealFocus() {
  // #ifdef H5
  if (revealing) return
  revealing = true
  nextTick(() => {
    const root = document.querySelector<HTMLElement>('[data-modal-id="' + id + '"]')
    // 只监听正文实际尺寸变化，避免在 visualViewport 的 CSS 更新前滚一次、
    // ResizeObserver 更新后又滚一次。焦点切换只补足被裁切的正文。
    // 收键盘后不再按旧 focusTarget 把已经失焦的输入框滚回屏内。
    revealDialogInput(root, document.activeElement)
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
  await nextTick()
  syncModalInert()
  const body = document.querySelector<HTMLElement>('[data-modal-id="' + id + '"] .dialog-body')
  if (body && window.ResizeObserver) {
    bodyObserver = new window.ResizeObserver(revealFocus)
    bodyObserver.observe(body)
  }
  document
    .querySelector<HTMLElement>('[data-modal-id="' + id + '"] .dialog-close')
    ?.focus({ preventScroll: true })
  // #endif
  // #ifndef H5
  nativeResize()
  uni.onKeyboardHeightChange(nativeResize)
  uni.onWindowResize(nativeResize)
  // #endif
})
onUnmounted(() => {
  // #ifdef H5
  bodyObserver?.disconnect()
  document.removeEventListener('keydown', keyboard)
  nextTick(() => {
    syncModalInert()
    if (previous?.isConnected) previous.focus({ preventScroll: true })
  })
  // #endif
  // #ifndef H5
  disposed = true
  uni.offKeyboardHeightChange(nativeResize)
  uni.offWindowResize(nativeResize)
  // #endif
})
</script>
<template>
  <view
    class="dialog-backdrop"
    :class="{ 'floating-backdrop': floating }"
    @transitionend="nativeTransitionFinished"
  >
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
          :scroll-top="nativeScrollTop"
          @scroll="nativeScroll"
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
  transition: height var(--dialog-keyboard-duration, 0ms) ease-out;
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
