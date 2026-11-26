<script setup lang="ts">
import AppIcon from './AppIcon.vue'
import ChatTitle from './ChatTitle.vue'

defineProps<{
  title: string
  compact?: boolean
  backLabel: string
  chat: boolean
  showBack: boolean
  showHistory: boolean
  historyOpen: boolean
  optionsOpen: boolean
  nativeTitle: boolean
  search?: string
  frame: { top: number; row: number; side: number }
}>()

const emit = defineEmits<{
  home: []
  back: []
  history: []
  options: []
  search: [value: string]
}>()

function updateSearch(event: unknown) {
  const { detail } = event as { detail?: { value?: string } }
  emit('search', detail?.value ?? '')
}
</script>

<template>
  <view class="wechat-header" :style="{ paddingTop: frame.top + 'px' }">
    <view
      class="wechat-header-row"
      :class="{ 'compact-row': compact }"
      :style="{ height: frame.row + 'px' }"
    >
      <view
        class="wechat-header-leading"
        :style="{ width: (search === undefined && !compact ? frame.side : 48) + 'px' }"
      >
        <button
          v-if="showBack"
          class="wechat-header-button"
          :aria-label="backLabel"
          @click="emit('back')"
        >
          <AppIcon name="back" :size="21" />
        </button>
        <button
          v-if="showHistory"
          class="wechat-header-button"
          aria-label="打开历史记录"
          :aria-expanded="historyOpen"
          @click="emit('history')"
        >
          <AppIcon :name="chat ? 'history' : 'menu'" :size="21" />
        </button>
      </view>
      <view class="wechat-header-center">
        <view v-if="search !== undefined" class="wechat-header-search">
          <AppIcon name="search" :size="16" />
          <input
            :value="search"
            :adjust-position="false"
            aria-label="搜索历史记录"
            placeholder="搜索作物、问题或备注"
            confirm-type="search"
            @input="updateSearch"
          />
        </view>
        <ChatTitle
          v-else-if="chat"
          :title="title"
          :expanded="optionsOpen"
          @open="emit('options')"
        />
        <button
          v-else-if="compact"
          class="header-brand-mark"
          aria-label="宛田观叶，返回首页"
          @click="emit('home')"
        >
          <AppIcon name="leaf" :size="23" />
        </button>
        <text v-else-if="!nativeTitle" class="wechat-header-title">{{ title }}</text>
      </view>
      <view
        aria-hidden="true"
        :style="{ width: frame.side + 'px' }"
        class="wechat-header-capsule"
      />
    </view>
  </view>
</template>

<style scoped>
.header-brand-mark {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 11px;
  background: var(--accent-soft);
}
.wechat-header {
  flex-shrink: 0;
  width: 100%;
  background: var(--bg);
}
.wechat-header-row {
  display: flex;
  align-items: center;
  border-bottom: 1px solid var(--line);
}
.compact-row {
  border-bottom: 0;
}
.compact-row .wechat-header-center {
  justify-content: flex-start;
  padding-left: 4px;
}
.wechat-header-leading,
.wechat-header-capsule {
  flex-shrink: 0;
}
.wechat-header-leading {
  display: flex;
  align-items: center;
  padding-left: 4px;
}
.wechat-header-button {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  flex-shrink: 0;
  border-radius: 12px;
  color: var(--ink);
}
.wechat-header-button:active,
.wechat-header-button[aria-expanded='true'] {
  background: var(--pressed);
}
.wechat-header-center {
  display: flex;
  justify-content: center;
  flex: 1;
  min-width: 0;
}
.wechat-header-search {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
  gap: 7px;
  height: 36px;
  padding: 0 9px;
  border-radius: 11px;
  background: var(--subtle);
  color: var(--muted);
}
.wechat-header-search input {
  flex: 1;
  min-width: 0;
  height: 100%;
  color: var(--ink);
  font-size: 13px;
}
.wechat-header-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 16px;
  font-weight: 650;
  color: var(--ink);
}
</style>
