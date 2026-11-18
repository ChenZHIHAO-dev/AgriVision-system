<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'
import { syncModalInert } from '../lib/modal'
import ConversationHistory from './ConversationHistory.vue'
import type { CaseRecord } from '../lib/api'
import type { User } from '../lib/auth'

const props = withDefaults(
  defineProps<{ records: CaseRecord[]; user: User | null; selected?: string; safeTop?: number }>(),
  { safeTop: 0 },
)
const emit = defineEmits<{
  close: []
  open: [id: string]
  new: []
  login: []
  navigate: [value: 'home' | 'identify' | 'profile']
  keyboard: [height: number]
}>()

const searchOpen = ref(false)
const query = ref('')
let previous: HTMLElement | null = null

function closeSearch() {
  searchOpen.value = false
  query.value = ''
}

async function toggleSearch() {
  if (!props.user) {
    emit('login')
    return
  }
  if (searchOpen.value) {
    closeSearch()
    return
  }
  searchOpen.value = true
  await nextTick()
  // #ifdef H5
  document.querySelector<HTMLInputElement>('.drawer-search input')?.focus({ preventScroll: true })
  // #endif
}

watch(() => props.user?.id, closeSearch)

function key(event: KeyboardEvent) {
  if (event.defaultPrevented) return
  // #ifdef H5
  if (document.querySelector('[data-modal-id],[data-choice-layer]')) return
  if (event.key === 'Escape') {
    event.preventDefault()
    if (searchOpen.value) {
      closeSearch()
      nextTick(() => document.querySelector<HTMLElement>('.drawer-search-toggle')?.focus())
    } else {
      emit('close')
    }
    return
  }
  if (event.key !== 'Tab') return
  const root = document.querySelector<HTMLElement>('.conversation-drawer')
  const targets = Array.from(
    root?.querySelectorAll<HTMLElement>('[tabindex="0"],button,input,a[href]') || [],
  ).filter(
    (item) => item.tabIndex >= 0 && !item.hasAttribute('disabled') && item.getClientRects().length,
  )
  const first = targets[0]
  const last = targets[targets.length - 1]
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
  syncModalInert()
  document.querySelector<HTMLElement>('.drawer-close')?.focus()
  // #endif
})
onUnmounted(() => {
  // #ifdef H5
  document.removeEventListener('keydown', key)
  nextTick(() => {
    syncModalInert()
    if (previous?.isConnected) previous.focus()
  })
  // #endif
})
</script>

<template>
  <view class="conversation-drawer-backdrop" @click.self="emit('close')">
    <view
      class="conversation-drawer"
      :style="{ '--drawer-safe-top': safeTop ? safeTop + 'px' : undefined }"
      role="dialog"
      aria-modal="true"
      aria-label="咨询侧栏"
    >
      <view class="drawer-heading">
        <button
          class="drawer-brand"
          aria-label="返回宛农植保首页"
          @click="emit('navigate', 'home')"
        >
          <view class="drawer-mark"><AppIcon name="leaf" tone="white" :size="20" /></view>
          <text>宛农植保</text>
        </button>
        <view class="drawer-heading-actions">
          <button
            class="drawer-icon-button drawer-search-toggle"
            :aria-label="user ? '搜索历史问诊' : '登录后搜索历史问诊'"
            :aria-expanded="searchOpen"
            @click="toggleSearch"
          >
            <AppIcon name="search" :size="20" />
          </button>
          <button
            class="drawer-icon-button drawer-close"
            aria-label="关闭咨询侧栏"
            @click="emit('close')"
          >
            <AppIcon name="close" :size="21" />
          </button>
        </view>
      </view>

      <view v-if="searchOpen" class="drawer-search">
        <input
          v-model="query"
          :focus="searchOpen"
          :adjust-position="false"
          :maxlength="80"
          confirm-type="search"
          aria-label="搜索历史问诊"
          placeholder="搜标题、作物或对话"
          placeholder-class="drawer-search-placeholder"
          @keyboardheightchange="emit('keyboard', $event.detail.height)"
        />
        <button v-if="query" class="drawer-icon-button" aria-label="清空搜索" @click="query = ''">
          <AppIcon name="close" :size="16" />
        </button>
      </view>

      <view class="drawer-navigation">
        <button @click="emit('navigate', 'identify')">
          <AppIcon name="camera" :size="18" /><text>拍照问诊</text>
        </button>
      </view>

      <ConversationHistory
        :records="records"
        :user="user"
        :selected="selected"
        :query="query"
        drawer
        @open="emit('open', $event)"
      />

      <view class="drawer-footer">
        <button class="drawer-new" @click="emit('new')">
          <AppIcon name="new" :size="18" /><text>新建咨询</text>
        </button>
        <button
          class="drawer-account"
          :aria-label="user ? '打开我的账户' : '登录后保存问诊'"
          @click="user ? emit('navigate', 'profile') : emit('login')"
        >
          <view class="drawer-avatar">
            <text v-if="user">{{ user.name.slice(0, 1).toUpperCase() }}</text>
            <AppIcon v-else name="user" :size="17" />
          </view>
          <view class="drawer-account-copy">
            <text>{{ user ? user.name : '访客' }}</text>
            <text>{{ user ? '我的账户' : '登录后保存问诊' }}</text>
          </view>
          <AppIcon name="right" :size="15" />
        </button>
      </view>
    </view>
  </view>
</template>

<style scoped>
.conversation-drawer-backdrop {
  position: fixed;
  inset: 0;
  z-index: 180;
  background: #0005;
  animation: drawer-fade 0.18s ease;
}
.conversation-drawer {
  display: flex;
  flex-direction: column;
  width: 300px;
  max-width: 86vw;
  height: 100%;
  height: var(--visual-height, var(--app-height, 100dvh));
  padding: 14px 14px 12px;
  padding-top: calc(14px + var(--drawer-safe-top, env(safe-area-inset-top, 0px)));
  padding-bottom: calc(12px + env(safe-area-inset-bottom, 0px));
  background: var(--surface);
  color: var(--ink);
  border-right: 1px solid var(--line);
  box-shadow: 12px 0 32px #0002;
  animation: drawer-slide 0.18s ease-out;
  box-sizing: border-box;
}
.drawer-heading,
.drawer-heading-actions,
.drawer-brand {
  display: flex;
  align-items: center;
}
.drawer-heading {
  justify-content: space-between;
  gap: 6px;
  flex-shrink: 0;
}
.drawer-heading-actions {
  gap: 1px;
  flex-shrink: 0;
}
.drawer-brand {
  min-width: 0;
  gap: 8px;
  color: var(--ink);
  font-size: 14px;
  font-weight: 650;
  padding: 4px;
  border-radius: 11px;
  min-height: 44px;
}
.drawer-brand > text {
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.drawer-mark,
.drawer-avatar {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  border-radius: 10px;
}
.drawer-mark {
  background: var(--brand-fill);
}
.drawer-icon-button {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  color: var(--ink);
  border-radius: 10px;
  flex-shrink: 0;
}
.drawer-search-toggle[aria-expanded='true'],
.drawer-close {
  background: var(--subtle);
}
.drawer-search {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  margin-top: 9px;
  background: var(--subtle);
  border: 1px solid var(--line);
  border-radius: 11px;
  min-height: 44px;
}
.drawer-search input {
  flex: 1;
  width: 0;
  min-height: 42px;
  padding: 0 10px;
  color: var(--ink);
  font-size: 14px;
}
.drawer-search-placeholder {
  color: var(--muted);
}
.drawer-navigation {
  margin: 12px 0 7px;
  flex-shrink: 0;
}
.drawer-navigation > button,
.drawer-new,
.drawer-account {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  min-height: 44px;
  padding: 7px 10px;
  border-radius: 10px;
  color: var(--ink);
  text-align: left;
  font-size: 13px;
}
.drawer-footer {
  display: flex;
  flex-direction: column;
  gap: 7px;
  border-top: 1px solid var(--line);
  padding-top: 9px;
  margin-top: 5px;
  flex-shrink: 0;
}
.drawer-new {
  font-weight: 600;
  background: var(--subtle);
}
.drawer-account {
  padding-inline: 5px;
}
.drawer-avatar {
  background: var(--accent-soft);
  border-radius: 50%;
  color: var(--accent);
  font-weight: 650;
}
.drawer-account-copy {
  min-width: 0;
  flex: 1;
}
.drawer-account-copy > text {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.drawer-account-copy > text + text {
  color: var(--muted);
  font-size: 11px;
}
.keyboard-open .drawer-navigation,
.keyboard-open .drawer-footer {
  display: none;
}
@keyframes drawer-slide {
  from {
    transform: translateX(-100%);
  }
  to {
    transform: translateX(0);
  }
}
@keyframes drawer-fade {
  from {
    background-color: transparent;
  }
  to {
    background-color: #0005;
  }
}
@media (prefers-reduced-motion: reduce) {
  .conversation-drawer-backdrop,
  .conversation-drawer {
    animation: none;
  }
}
</style>
