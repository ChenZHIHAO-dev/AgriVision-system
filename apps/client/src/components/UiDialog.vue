<script setup lang="ts">
import { nextTick, onMounted, onUnmounted } from 'vue'
import AppIcon from './AppIcon.vue'
withDefaults(defineProps<{ title: string; subtitle?: string; wide?: boolean }>(), { subtitle: '', wide: false })
const emit = defineEmits<{ close: [] }>()
const id = 'dialog-' + Math.random().toString(36).slice(2, 9)
// #ifdef H5
let previous: HTMLElement | null = null
function keyboard(event: KeyboardEvent) {
  if (event.key === 'Escape') { event.preventDefault(); emit('close'); return }
  if (event.key !== 'Tab') return
  const root = document.querySelector<HTMLElement>(`[data-modal-id="${id}"]`)
  const targets = Array.from(root?.querySelectorAll<HTMLElement>('button:not([disabled]), [tabindex="0"], input, textarea, select, a[href]') || []).filter(item => item.getClientRects().length)
  const first = targets[0]; const last = targets[targets.length - 1]
  if (!first) { event.preventDefault(); root?.focus(); return }
  if (event.shiftKey && (document.activeElement === first || !root?.contains(document.activeElement))) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
}
onMounted(async () => {
  previous = document.activeElement as HTMLElement
  document.addEventListener('keydown', keyboard)
  await nextTick()
  document.querySelector<HTMLElement>(`[data-modal-id="${id}"] .dialog-close`)?.focus()
})
onUnmounted(() => { document.removeEventListener('keydown', keyboard); if (previous?.isConnected) previous.focus() })
// #endif
</script>
<template>
  <view class="dialog-backdrop" @click.self="emit('close')">
    <view class="dialog-card" :class="{ 'dialog-wide': wide }" role="dialog" aria-modal="true" :aria-labelledby="id" :data-modal-id="id" tabindex="-1">
      <view class="dialog-heading"><view><text :id="id" class="dialog-title">{{ title }}</text><text v-if="subtitle" class="dialog-subtitle">{{ subtitle }}</text></view><button class="icon-button dialog-close" :aria-label="'关闭' + title" @click="emit('close')"><AppIcon name="close" :size="20" /></button></view>
      <scroll-view scroll-y class="dialog-body"><view class="dialog-body-inner"><slot /></view></scroll-view>
      <view v-if="$slots.footer" class="dialog-footer"><slot name="footer" /></view>
    </view>
  </view>
</template>
