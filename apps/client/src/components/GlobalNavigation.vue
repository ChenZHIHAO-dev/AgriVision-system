<script setup lang="ts">
import AppIcon from './AppIcon.vue'
import type { MainPage } from '../lib/navigation'
defineProps<{ active: MainPage; chat: boolean; expanded: boolean }>()
const emit = defineEmits<{ navigate: [page: MainPage]; consult: []; toggle: [] }>()
</script>
<template>
  <view class="global-rail" aria-label="主导航">
    <button
      class="rail-brand"
      aria-label="AgriVision 首页"
      title="AgriVision 首页"
      @click="emit('navigate', 'home')"
    >
      <AppIcon name="leaf" :size="24" tone="white" />
    </button>
    <view class="rail-primary">
      <button
        class="rail-item"
        :class="{ active: active === 'home' && !chat }"
        title="首页"
        @click="emit('navigate', 'home')"
      >
        <AppIcon name="home" :size="21" /><text>首页</text>
      </button>
      <button
        class="rail-item"
        :class="{ active: active === 'identify' && !chat }"
        title="拍照问诊"
        @click="emit('navigate', 'identify')"
      >
        <AppIcon name="camera" :size="22" /><text>拍照</text>
      </button>
      <button class="rail-item" :class="{ active: chat }" title="继续咨询" @click="emit('consult')">
        <AppIcon name="chat" :size="21" /><text>咨询</text>
      </button>
    </view>
    <view class="rail-bottom">
      <button
        class="rail-item"
        :aria-expanded="expanded"
        aria-label="展开或收起历史侧栏"
        title="历史侧栏"
        @click="emit('toggle')"
      >
        <AppIcon name="menu" :size="20" />
      </button>
      <button
        class="rail-item"
        :class="{ active: active === 'settings' && !chat }"
        title="设置"
        @click="emit('navigate', 'settings')"
      >
        <AppIcon name="settings" :size="21" /><text>设置</text>
      </button>
      <button
        class="rail-item"
        :class="{ active: active === 'profile' && !chat }"
        title="我的"
        @click="emit('navigate', 'profile')"
      >
        <AppIcon name="user" :size="22" /><text>我的</text>
      </button>
    </view>
  </view>
</template>
<style scoped>
.global-rail {
  width: 72px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  background: var(--surface);
  padding: 22px 9px 17px;
  border-right: 1px solid var(--line);
}
.rail-brand {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 14px;
  background: #28654e;
  margin-bottom: 29px;
}
.rail-primary,
.rail-bottom {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}
.rail-bottom {
  margin-top: auto;
  padding-top: 24px;
}
.rail-item {
  width: 100%;
  min-height: 51px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 3px;
  border-radius: 12px;
  color: var(--muted);
  font-size: 10px;
}
.rail-item.active {
  background: var(--subtle);
  color: var(--ink);
}
@media (max-width: 760px) {
  .global-rail {
    display: none;
  }
}
</style>
