<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'
const props = withDefaults(
  defineProps<{ title: string; subtitle?: string; wide?: boolean; focusTarget?: string }>(),
  { subtitle: '', wide: false, focusTarget: '' },
)
const emit = defineEmits<{ close: [] }>()
const id = 'dialog-' + Math.random().toString(36).slice(2, 9),
  scrollTarget = ref('')
let previous: HTMLElement | null = null,
  revealing = false
function nativeReveal() {
  const target = props.focusTarget
  scrollTarget.value = ''
  nextTick(() => (scrollTarget.value = target))
}
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
    nativeReveal()
    revealFocus()
  },
)
function keyboard(event: KeyboardEvent) {
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
  document.querySelector<HTMLElement>('[data-modal-id="' + id + '"] .dialog-close')?.focus()
  // #endif
  // #ifndef H5
  uni.onKeyboardHeightChange(nativeReveal)
  // #endif
})
onUnmounted(() => {
  // #ifdef H5
  document.removeEventListener('keydown', keyboard)
  window.visualViewport?.removeEventListener('resize', revealFocus)
  if (previous?.isConnected) previous.focus()
  // #endif
  // #ifndef H5
  uni.offKeyboardHeightChange(nativeReveal)
  // #endif
})
</script>
<template>
  <view class="dialog-backdrop" @click.self="emit('close')"
    ><view
      class="dialog-card"
      :class="{ 'dialog-wide': wide }"
      role="dialog"
      aria-modal="true"
      :aria-labelledby="id"
      :data-modal-id="id"
      tabindex="-1"
      ><view class="dialog-heading"
        ><view
          ><text :id="id" class="dialog-title">{{ title }}</text
          ><text v-if="subtitle" class="dialog-subtitle">{{ subtitle }}</text></view
        ><button
          class="icon-button dialog-close"
          :aria-label="'关闭' + title"
          @click="emit('close')"
        >
          <AppIcon name="close" :size="20" /></button></view
      ><scroll-view scroll-y class="dialog-body" :scroll-into-view="scrollTarget"
        ><view class="dialog-body-inner"><slot /></view></scroll-view
      ><view v-if="$slots.footer" class="dialog-footer"><slot name="footer" /></view></view
  ></view>
</template>
