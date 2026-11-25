<script setup lang="ts">
import AppIcon from './AppIcon.vue'
import ChatTitle from './ChatTitle.vue'

defineProps<{
  title: string
  page: string
  chat: boolean
  backLabel: string
  safeTop: number
  chatOptionsOpen: boolean
  historyOpen: boolean
  search?: string
}>()
const emit = defineEmits<{
  back: []
  history: []
  options: []
  search: [value: string]
}>()

function updateSearch(event: unknown) {
  const value = event as { detail?: { value?: string }; target?: { value?: string } }
  emit('search', value.detail?.value ?? value.target?.value ?? '')
}
</script>

<template>
  <view class="mobile-header" :style="{ paddingTop: safeTop ? safeTop + 'px' : undefined }">
    <view class="mobile-primary" :class="{ 'has-search': search !== undefined }">
      <view class="mobile-leading">
        <button
          v-if="chat || page === 'settings' || page === 'history'"
          class="mobile-header-action"
          :aria-label="chat ? backLabel : page === 'history' ? '返回首页' : '返回我的'"
          @click="emit('back')"
        >
          <AppIcon name="back" :size="21" />
        </button>
        <button
          v-if="chat || page === 'identify'"
          class="mobile-header-action"
          aria-label="打开历史记录"
          :aria-expanded="historyOpen"
          @click="emit('history')"
        >
          <AppIcon :name="chat ? 'history' : 'menu'" :size="21" />
        </button>
      </view>
      <view v-if="search !== undefined" class="mobile-header-search">
        <AppIcon name="search" :size="17" />
        <input
          :value="search"
          :adjust-position="false"
          aria-label="搜索历史记录"
          inputmode="search"
          placeholder="搜索作物、问题或备注"
          confirm-type="search"
          @input="updateSearch"
        />
        <button
          v-if="search"
          class="mobile-header-action clear-search"
          aria-label="清除搜索"
          @click="emit('search', '')"
        >
          <AppIcon name="close" :size="16" />
        </button>
      </view>
      <view v-else class="mobile-center">
        <ChatTitle v-if="chat" :title="title" :expanded="chatOptionsOpen" @open="emit('options')" />
        <text v-else class="mobile-title" role="heading" aria-level="1">{{ title }}</text>
      </view>
      <view v-if="search === undefined" class="mobile-trailing" aria-hidden="true" />
    </view>
  </view>
</template>

<style scoped>
.mobile-header {
  display: block;
  flex: 0 0 auto;
  padding-top: env(safe-area-inset-top, 0px);
  background: var(--bg);
  position: relative;
  z-index: 45;
}
.mobile-primary {
  display: flex;
  align-items: center;
  min-height: 54px;
  padding: 0 8px;
  border-bottom: 1px solid var(--line);
}
.mobile-leading,
.mobile-trailing {
  display: flex;
  flex: 0 0 88px;
}
.has-search .mobile-leading {
  flex-basis: 44px;
}
.mobile-header-action {
  display: grid;
  place-items: center;
  flex: 0 0 44px;
  width: 44px;
  height: 44px;
  border-radius: 12px;
}
.mobile-header-action:hover {
  background: var(--hover);
}
.mobile-header-action:active,
.mobile-header-action[aria-expanded='true'] {
  background: var(--pressed);
}
.mobile-center {
  display: flex;
  justify-content: center;
  flex: 1;
  min-width: 0;
}
.mobile-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 16px;
  font-weight: 650;
}
.mobile-header-search {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
  height: 44px;
  gap: 8px;
  padding: 0 4px 0 11px;
  margin: 0 4px;
  border-radius: 12px;
  background: var(--subtle);
}
.mobile-header-search input {
  flex: 1;
  min-width: 0;
  min-height: 32px;
  font-size: 16px;
}
.clear-search {
  width: 44px;
}
</style>
