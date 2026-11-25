<script setup lang="ts">
import AppIcon from './AppIcon.vue'
import AppearanceSwitch from './AppearanceSwitch.vue'
import ChatTitle from './ChatTitle.vue'

defineProps<{
  title: string
  chat: boolean
  backLabel: string
  optionsOpen: boolean
  accountName?: string
}>()

const emit = defineEmits<{ back: []; options: []; login: []; profile: [] }>()
</script>

<template>
  <view class="web-workspace-header">
    <view class="web-header-leading">
      <template v-if="chat">
        <button
          class="web-header-button web-header-back"
          :aria-label="backLabel"
          @click="emit('back')"
        >
          <AppIcon name="back" :size="18" />
          <text>{{ backLabel }}</text>
        </button>
        <ChatTitle :title="title" :expanded="optionsOpen" @open="emit('options')" />
      </template>
      <text v-else role="heading" aria-level="1" class="web-workspace-title">{{ title }}</text>
    </view>
    <view class="web-header-actions">
      <AppearanceSwitch />
      <button v-if="!accountName" class="web-header-button" @click="emit('login')">登录</button>
      <button
        v-else
        class="web-header-button web-header-account"
        aria-label="我的账户"
        @click="emit('profile')"
      >
        <text class="web-header-avatar">{{ accountName.slice(0, 1).toUpperCase() }}</text>
        <text class="web-header-account-name">{{ accountName }}</text>
      </button>
    </view>
  </view>
</template>

<style scoped>
.web-workspace-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex: 0 0 auto;
  min-height: 62px;
  padding: 7px clamp(16px, 2.6vw, 36px);
  gap: 16px;
  background: var(--bg);
  border-bottom: 1px solid var(--line);
}
.web-header-leading,
.web-header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.web-header-leading {
  min-width: 0;
}
.web-header-actions {
  flex-shrink: 0;
}
.web-workspace-title {
  color: var(--ink);
  font-size: 17px;
  font-weight: 650;
}
.web-header-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 40px;
  padding: 0 12px;
  gap: 7px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 11px;
  color: var(--ink);
  font-size: 13px;
  font-weight: 550;
  white-space: nowrap;
}
.web-header-back {
  flex-shrink: 0;
  background: var(--subtle);
  border-color: transparent;
}
.web-header-account {
  padding-left: 6px;
}
.web-header-avatar {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  background: var(--accent-soft);
  color: var(--accent);
  border-radius: 50%;
}
.web-header-account-name {
  max-width: 9em;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
