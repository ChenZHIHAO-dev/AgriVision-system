<script setup lang="ts">
import { nextTick, onMounted, onUnmounted } from 'vue'
import ConversationHistory from './ConversationHistory.vue'
import type { CaseRecord } from '../lib/api'
import type { User } from '../lib/auth'
defineProps<{ records: CaseRecord[]; user: User | null; selected?: string }>()
const emit = defineEmits<{
  close: []
  open: [id: string]
  new: []
  login: []
  navigate: [value: 'identify' | 'knowledge' | 'profile']
}>()
let previous: HTMLElement | null = null
function key(event: KeyboardEvent) {
  // #ifdef H5
  if (document.querySelector('[data-modal-id],[data-choice-layer]')) return
  if (event.key === 'Escape') {
    event.preventDefault()
    emit('close')
    return
  }
  if (event.key !== 'Tab') return
  const root = document.querySelector<HTMLElement>('.conversation-drawer')
  const targets = Array.from(
    root?.querySelectorAll<HTMLElement>('[tabindex="0"],button,a[href]') || [],
  ).filter((item) => item.getClientRects().length)
  const first = targets[0],
    last = targets[targets.length - 1]
  if (!first) return
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
  document.addEventListener('keydown', key)
  await nextTick()
  document.querySelector<HTMLElement>('.drawer-close')?.focus()
  // #endif
})
onUnmounted(() => {
  // #ifdef H5
  document.removeEventListener('keydown', key)
  if (previous?.isConnected) previous.focus()
  // #endif
})
</script>
<template>
  <view class="conversation-drawer-backdrop" @click.self="emit('close')"
    ><view class="conversation-drawer" role="dialog" aria-modal="true" aria-label="咨询侧栏"
      ><view class="drawer-heading"
        ><view><text>AgriVision</text><text>接着上次的咨询</text></view
        ><button class="icon-button drawer-close" aria-label="关闭咨询侧栏" @click="emit('close')">
          ×
        </button></view
      ><view class="drawer-navigation"
        ><button @click="emit('navigate', 'identify')">首页</button
        ><button @click="emit('navigate', 'profile')">我的</button></view
      ><ConversationHistory
        :records="records"
        :user="user"
        :selected="selected"
        @new="emit('new')"
        @open="emit('open', $event)"
        @login="emit('login')"
      /><text v-if="!user" class="drawer-footer">访客内容不会保存到咨询历史。</text></view
    ></view
  >
</template>
<style scoped>
.drawer-navigation {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
  padding: 18px 4px 0;
}
.drawer-navigation > button {
  padding: 8px 11px;
  border-radius: 9px;
  background: var(--subtle);
  color: var(--ink);
  font-size: 11px;
}

.conversation-drawer-backdrop {
  position: fixed;
  inset: 0;
  z-index: 180;
  background: #0005;
  animation: drawer-fade 0.16s ease;
}
.conversation-drawer {
  display: flex;
  flex-direction: column;
  height: 100%;
  height: var(--app-height, 100dvh);
  width: 300px;
  max-width: 86vw;
  padding: 22px 18px calc(17px + env(safe-area-inset-bottom));
  background: var(--surface);
  color: var(--ink);
  border-right: 1px solid var(--line);
  box-shadow: 15px 0 40px #0002;
  animation: drawer-slide 0.18s ease;
  box-sizing: border-box;
}
.drawer-heading {
  display: flex;
  justify-content: space-between;
  gap: 15px;
  align-items: center;
  padding-left: 7px;
}
.drawer-heading > view > text:first-child {
  display: block;
  font-size: 18px;
  font-weight: 650;
}
.drawer-heading > view > text:last-child {
  display: block;
  color: var(--muted);
  font-size: 10px;
  margin-top: 4px;
}
.drawer-close {
  font-size: 24px;
}
.drawer-footer {
  font-size: 10px;
  color: var(--muted);
  line-height: 1.8;
  margin: 15px 8px 0;
}
@keyframes drawer-slide {
  from {
    transform: translateX(-28px);
    opacity: 0.4;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}
@keyframes drawer-fade {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}
</style>
