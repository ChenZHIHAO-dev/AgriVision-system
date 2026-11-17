<script setup lang="ts">
import AppIcon from './AppIcon.vue'
defineProps<{ active: string; keyboardOpen?: boolean }>()
const emit = defineEmits<{
  navigate: [value: 'identify' | 'knowledge' | 'profile']
  chat: []
  capture: []
}>()
</script>
<template>
  <view
    class="av-dock"
    :class="{ 'keyboard-hidden': keyboardOpen }"
    :aria-hidden="keyboardOpen"
    :inert="keyboardOpen || undefined"
  >
    <button
      class="dock-home"
      :class="{ active: active === 'identify' }"
      @click="emit('navigate', 'identify')"
    >
      <AppIcon name="home" :size="21" /><text>首页</text>
    </button>
    <button class="dock-chat" :class="{ active: active === 'chat' }" @click="emit('chat')">
      <AppIcon name="chat" :size="21" /><text>咨询</text>
    </button>
    <button class="dock-camera" aria-label="拍照识别" @click="emit('capture')">
      <view class="camera-core"><AppIcon name="camera" white :size="26" /></view><text>拍照</text>
    </button>
    <button
      class="dock-profile"
      :class="{ active: active === 'profile' || active === 'settings' || active === 'knowledge' }"
      @click="emit('navigate', 'profile')"
    >
      <view class="person-mark"><view /></view><text>我的</text>
    </button>
  </view>
</template>
<style scoped>
.av-dock {
  display: none;
}
@media (max-width: 760px) {
  .av-dock {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    align-items: end;
    gap: 2px;
    min-height: 72px;
    max-height: 112px;
    flex-shrink: 0;
    padding: 5px 10px calc(6px + env(safe-area-inset-bottom));
    background: var(--glass);
    border-top: 1px solid var(--line);
    backdrop-filter: blur(16px);
    z-index: 35;
    transition:
      opacity 0.15s ease,
      max-height 0.18s ease,
      min-height 0.18s ease,
      padding 0.18s ease,
      transform 0.18s ease;
  }
  .av-dock > button {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 48px;
    gap: 5px;
    font-size: 10px;
    color: var(--muted);
    border-radius: 11px;
    min-width: 0;
  }
  .av-dock > button.active {
    color: var(--accent);
  }
  .dock-home {
    grid-column: 1;
  }
  .dock-chat {
    grid-column: 2;
  }
  .av-dock > .dock-camera {
    grid-column: 3;
    color: var(--ink);
    gap: 4px;
    min-height: 64px;
    font-size: 10px;
    font-weight: 550;
  }
  .camera-core {
    width: 44px;
    height: 44px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 16px;
    background: var(--accent);
    box-shadow: 0 3px 9px #00000014;
  }
  .av-dock > .dock-profile {
    grid-column: 4/6;
    justify-self: center;
    width: 70px;
  }
  .person-mark {
    position: relative;
    width: 22px;
    height: 22px;
  }
  .person-mark > view {
    position: absolute;
    top: 0;
    left: 7px;
    width: 8px;
    height: 8px;
    border: 1.6px solid currentColor;
    border-radius: 50%;
    box-sizing: border-box;
  }
  .person-mark:after {
    content: '';
    position: absolute;
    bottom: 0;
    left: 2px;
    width: 18px;
    height: 11px;
    border: 1.6px solid currentColor;
    border-radius: 9px 9px 3px 3px;
    box-sizing: border-box;
  }
  .keyboard-hidden {
    min-height: 0;
    max-height: 0;
    padding-top: 0;
    padding-bottom: 0;
    opacity: 0;
    transform: translateY(12px);
    border-width: 0;
    pointer-events: none;
  }
}
</style>
