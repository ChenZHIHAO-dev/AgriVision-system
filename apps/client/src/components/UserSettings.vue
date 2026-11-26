<script setup lang="ts">
import AppIcon from './AppIcon.vue'
import { themeChoice, setTheme } from '../lib/theme'
import { appVersion } from '../lib/appInfo'
import { dataMode } from '../lib/api'
const preview = dataMode() === 'preview'
const emit = defineEmits<{ back: [] }>()
const themes = [
  { id: 'light' as const, label: '浅色', icon: 'sun' },
  { id: 'dark' as const, label: '深色', icon: 'moon' },
  { id: 'system' as const, label: '跟随系统', icon: 'system' },
]
</script>
<template>
  <view class="user-settings">
    <!-- #ifndef MP-WEIXIN -->
    <button class="settings-back" @click="emit('back')">
      <AppIcon name="back" :size="17" /><text>返回我的</text>
    </button>
    <text class="settings-title">设置</text>
    <!-- #endif -->
    <view class="panel settings-card"
      ><text class="settings-section-title">外观</text
      ><text class="settings-description">选择浅色、深色或跟随系统，设置会自动保存。</text
      ><view class="settings-themes"
        ><button
          v-for="theme in themes"
          :key="theme.id"
          :class="{ selected: themeChoice === theme.id }"
          :aria-pressed="themeChoice === theme.id"
          @click="setTheme(theme.id)"
        >
          <AppIcon :name="theme.icon" :size="24" /><text>{{ theme.label }}</text
          ><AppIcon
            v-if="themeChoice === theme.id"
            name="check"
            :size="15"
            class="theme-check"
          /></button></view></view
    ><view class="panel settings-card"
      ><text class="settings-section-title">记录与隐私</text
      ><view class="privacy-row"
        ><text>未登录</text><text>登录后可使用在线识别、AI 对话、资料和历史记录。</text></view
      ><view class="privacy-row"
        ><text>登录后</text
        ><text>{{
          preview
            ? '演示记录仅保留在当前页面内存，刷新或退出后清除。'
            : '后续记录按账户保存。点「继续对话」可接续本次照片。'
        }}</text></view
      ><view class="privacy-row"
        ><text>图片与对话</text
        ><text>{{
          preview
            ? '离线预览只使用本地数据。'
            : '照片由识别服务处理。使用 AI 问答时，相关对话、种植信息、识别摘要与农业资料摘录会交给 DeepSeek。照片和文件原件不转发。'
        }}</text></view
      ></view
    ><view class="panel settings-card about-card"
      ><text class="settings-section-title">关于 AgriVision</text><text>版本 {{ appVersion }}</text
      ><text class="settings-description"
        >面向小麦、玉米与花生的田间记录、初步识别与种植问答。</text
      ></view
    ></view
  >
</template>
<style scoped>
.user-settings {
  max-width: 760px;
  margin: 0 auto 30px;
}
.settings-back {
  display: block;
  color: var(--muted);
  font-size: 12px;
  min-height: 36px;
  text-align: left;
}
.settings-title {
  display: block;
  font-size: 28px;
  font-weight: 650;
  margin: 5px 0 23px;
}
.settings-card {
  padding: 24px;
  margin-bottom: 17px;
}
.settings-section-title {
  display: block;
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 9px;
}
.settings-description {
  display: block;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.9;
}
.settings-themes {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 11px;
  margin-top: 20px;
}
.settings-themes > button {
  position: relative;
  border: 1px solid var(--line);
  border-radius: 13px;
  padding: 17px 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 9px;
  color: var(--muted);
  font-size: 12px;
}
.settings-themes > button > text:first-child {
  font-size: 25px;
}
.settings-themes > button.selected {
  color: var(--accent);
  border-color: var(--focus);
  background: var(--accent-soft);
}
.theme-check {
  position: absolute;
  right: 10px;
  top: 8px;
  font-size: 12px;
}
.privacy-row {
  display: flex;
  align-items: flex-start;
  gap: 20px;
  padding: 14px 0;
  border-bottom: 1px solid var(--line);
  font-size: 12px;
  line-height: 1.9;
}
.privacy-row:last-child {
  border: 0;
  padding-bottom: 0;
}
.privacy-row > text:first-child {
  min-width: 72px;
  font-weight: 500;
}
.privacy-row > text:last-child {
  color: var(--muted);
}
.about-card > text:nth-child(2) {
  font-size: 12px;
  display: block;
  margin-bottom: 8px;
}
@media (max-width: 760px) {
  .settings-card {
    padding: 21px;
  }
  .settings-title {
    font-size: 25px;
  }
  .settings-themes {
    gap: 7px;
  }
  .privacy-row {
    gap: 12px;
  }
  .privacy-row > text:first-child {
    min-width: 65px;
  }
}
.settings-back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 10px;
  border-radius: 10px;
  background: var(--subtle);
}
.settings-themes > button {
  border-color: transparent;
  background: var(--subtle);
}
.settings-themes > button.selected {
  border-color: transparent;
}
/* #ifdef MP-WEIXIN */
.settings-back {
  margin-bottom: 12px;
}
/* #endif */
</style>
