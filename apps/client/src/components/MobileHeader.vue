<script setup lang="ts">
import AppIcon from './AppIcon.vue'
import AppearanceSwitch from './AppearanceSwitch.vue'
import ChatTitle from './ChatTitle.vue'
defineProps<{
  title: string
  page: string
  chat: boolean
  backLabel: string
  userName?: string
  safeTop: number
  chatOptionsOpen: boolean
  historyOpen: boolean
}>()
const emit = defineEmits<{
  back: []
  history: []
  login: []
  profile: []
  options: []
}>()
</script>
<template>
  <view class="mobile-header" :style="{ paddingTop: safeTop ? safeTop + 'px' : undefined }">
    <view class="mobile-primary">
      <button
        v-if="chat || page === 'settings' || page === 'history'"
        class="mobile-back"
        :aria-label="chat ? '退出咨询，' + backLabel : page === 'history' ? '返回首页' : '返回我的'"
        @click="emit('back')"
      >
        <AppIcon name="back" :size="20" /><text>{{ chat ? '退出' : '返回' }}</text>
      </button>
      <button
        v-else
        class="mobile-menu"
        aria-label="打开问诊历史"
        :aria-expanded="historyOpen"
        @click="emit('history')"
      >
        <AppIcon name="menu" :size="23" />
      </button>
      <view v-if="chat" class="mobile-chat-title">
        <ChatTitle :title="title" :expanded="chatOptionsOpen" @open="emit('options')" />
      </view>
      <text v-else :key="title" class="mobile-title">{{ title }}</text>
      <view class="mobile-actions">
        <button
          v-if="chat"
          class="mobile-menu"
          aria-label="打开问诊历史"
          :aria-expanded="historyOpen"
          @click="emit('history')"
        >
          <AppIcon name="history" :size="21" />
        </button>
        <AppearanceSwitch v-if="page === 'profile' && !chat" />
        <button v-if="!chat && !userName" class="mobile-login" @click="emit('login')">登录</button>
        <button
          v-else-if="!chat && userName"
          class="mobile-account"
          aria-label="用户中心"
          @click="emit('profile')"
        >
          {{ userName.slice(0, 1).toUpperCase() }}
        </button>
      </view>
    </view>
  </view>
</template>
<style scoped>
.mobile-header {
  display: none;
}
@media (max-width: 760px) {
  .mobile-header {
    display: block;
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    z-index: 45;
    background: var(--glass);
    padding-top: env(safe-area-inset-top);
  }
  .mobile-primary {
    height: 54px;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 0 14px;
    background: var(--glass);
    position: relative;
    z-index: 2;
    border-bottom: 1px solid var(--line);
  }
  .mobile-menu,
  .mobile-back {
    height: 40px;
    min-width: 40px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 3px;
  }
  .mobile-back {
    padding: 0 7px;
    background: var(--subtle);
    font-size: 11px;
  }
  .mobile-title {
    flex: 1;
    min-width: 0;
    font-size: 15px;
    font-weight: 650;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
    animation: header-title 0.16s ease;
  }
  .mobile-chat-title {
    flex: 1;
    min-width: 0;
    display: flex;
    justify-content: center;
  }
  .mobile-actions {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
  }
  .mobile-account {
    width: 36px;
    height: 36px;
    border-radius: 12px;
    background: var(--accent-soft);
    color: var(--accent);
    font-size: 13px;
    font-weight: 650;
  }
  .mobile-login {
    min-height: 36px;
    padding: 6px 12px;
    border-radius: 11px;
    background: var(--subtle);
    font-size: 12px;
    font-weight: 550;
  }
}
@keyframes header-title {
  from {
    opacity: 0.4;
    transform: translateY(3px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
@media (prefers-reduced-motion: reduce) {
  .mobile-title {
    animation: none;
  }
}
</style>
