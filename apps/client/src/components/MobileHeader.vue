<script setup lang="ts">
import AppIcon from './AppIcon.vue'
import AppearanceSwitch from './AppearanceSwitch.vue'
defineProps<{
  title: string
  page: string
  chat: boolean
  backLabel: string
  userName?: string
  offset: number
  safeTop: number
  resources: boolean
  settling: boolean
}>()
const emit = defineEmits<{
  back: []
  history: []
  login: []
  profile: []
  consult: []
  capture: []
  resources: []
  recent: []
  settings: []
}>()
</script>
<template>
  <view class="mobile-header" :style="{ paddingTop: safeTop ? safeTop + 'px' : undefined }">
    <view class="mobile-primary">
      <button
        v-if="chat || page === 'settings' || page === 'history' || (page === 'home' && resources)"
        class="mobile-back"
        :aria-label="
          chat
            ? backLabel
            : page === 'home'
              ? '返回工作台'
              : page === 'history'
                ? '返回首页'
                : '返回我的'
        "
        @click="emit('back')"
      >
        <AppIcon name="back" :size="21" /><text>返回</text>
      </button>
      <button v-else class="mobile-menu" aria-label="打开问诊历史" @click="emit('history')">
        <AppIcon name="menu" :size="23" />
      </button>
      <text :key="title" class="mobile-title">{{ title }}</text>
      <view class="mobile-actions">
        <AppearanceSwitch v-if="page === 'profile' && !chat" />
        <button v-if="!userName" class="mobile-login" @click="emit('login')">登录</button>
        <button v-else class="mobile-account" aria-label="用户中心" @click="emit('profile')">
          {{ userName.slice(0, 1).toUpperCase() }}
        </button>
      </view>
    </view>
    <view
      v-if="!chat && page !== 'settings' && page !== 'history' && !(page === 'home' && resources)"
      class="mobile-toolbar-clip"
    >
      <view
        class="mobile-toolbar"
        :class="{ settling }"
        :style="{ transform: 'translateY(-' + offset + 'px)', opacity: 1 - offset / 46 }"
        :inert="offset >= 44 || undefined"
        :aria-hidden="offset >= 44"
      >
        <template v-if="page === 'home'">
          <button v-if="resources" @click="emit('recent')">
            <AppIcon name="history" :size="18" /><text>最近问诊</text>
          </button>
          <button v-else @click="emit('resources')">
            <AppIcon name="book" :size="18" /><text>参考资料</text>
          </button>
          <button @click="emit('consult')">
            <AppIcon name="chat" :size="18" /><text>文字咨询</text>
          </button>
          <button @click="emit('capture')">
            <AppIcon name="camera" :size="18" /><text>拍照</text>
          </button>
        </template>
        <template v-else-if="page === 'identify'">
          <text class="toolbar-hint">拍照识别，也可直接提问</text
          ><button @click="emit('consult')">
            <AppIcon name="chat" :size="18" /><text>文字咨询</text>
          </button>
        </template>
        <template v-else
          ><text class="toolbar-hint">账户与使用偏好</text
          ><button @click="emit('settings')">
            <AppIcon name="settings" :size="18" /><text>设置</text>
          </button></template
        >
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
  .mobile-toolbar-clip {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    height: 46px;
    overflow: hidden;
    pointer-events: none;
  }
  .mobile-toolbar {
    height: 46px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 5px;
    padding: 4px 14px;
    background: var(--glass);
    backdrop-filter: blur(16px);
    border-bottom: 1px solid var(--line);
    will-change: transform;
  }
  .mobile-toolbar > button {
    pointer-events: auto;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    border-radius: 10px;
    padding: 7px 9px;
    min-height: 36px;
    font-size: 11px;
  }
  .mobile-toolbar[aria-hidden='true'] > button {
    pointer-events: none;
  }
  .mobile-toolbar.settling {
    transition:
      transform 0.22s ease,
      opacity 0.22s ease;
  }
  .toolbar-hint {
    font-size: 11px;
    color: var(--muted);
    overflow: hidden;
    white-space: nowrap;
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
@media (prefers-reduced-motion: reduce) {
  .mobile-toolbar.settling {
    transition: none;
  }
}
</style>
