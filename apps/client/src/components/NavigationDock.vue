<script setup lang="ts">
import AppIcon from './AppIcon.vue'
defineProps<{ active: string; keyboardOpen?: boolean }>()
const emit = defineEmits<{
  navigate: [value: 'home' | 'identify' | 'profile']
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
      :class="{ active: active === 'home' }"
      @click="emit('navigate', 'home')"
    >
      <AppIcon name="home" :size="21" /><text>首页</text>
    </button>

    <button class="dock-camera" aria-label="拍照识别" @click="emit('navigate', 'identify')">
      <view class="camera-core"><AppIcon name="camera" white :size="24" /></view><text>拍照</text>
    </button>
    <button
      class="dock-profile"
      :class="{ active: active === 'profile' || active === 'settings' || active === 'knowledge' }"
      @click="emit('navigate', 'profile')"
    >
      <AppIcon name="user" :size="22" /><text>我的</text>
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
    grid-template-columns: repeat(3, minmax(0, 1fr));
    align-items: stretch;
    gap: 0;
    min-height: 68px;
    max-height: 105px;
    flex-shrink: 0;
    padding: 6px 12px calc(6px + env(safe-area-inset-bottom));
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
    display: grid;
    grid-template-rows: 38px 14px;
    place-items: center;
    gap: 2px;
    min-height: 54px;
    width: 100%;
    min-width: 0;
    border-radius: 11px;
    color: var(--muted);
    font-size: 11px;
    font-weight: 400;
  }
  .av-dock > button.active {
    color: var(--accent);
  }
  .av-dock > .dock-camera {
    color: var(--ink);
    font-weight: 500;
  }
  .camera-core {
    width: 36px;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 12px;
    background: var(--accent);
    box-shadow: 0 2px 6px #00000012;
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
  .av-dock.keyboard-hidden {
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
