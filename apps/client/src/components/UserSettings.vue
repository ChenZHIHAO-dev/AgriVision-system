<script setup lang="ts">
import { themeChoice, setTheme } from '../lib/theme'
import { appVersion } from '../lib/appInfo'
const emit = defineEmits<{ back: [] }>()
const themes = [
  { id: 'light' as const, label: '浅色', icon: '☀' },
  { id: 'dark' as const, label: '深色', icon: '☾' },
  { id: 'system' as const, label: '跟随系统', icon: '◐' },
]
</script>
<template>
  <view class="user-settings"
    ><button class="settings-back" @click="emit('back')">← 我的</button
    ><text class="settings-title">设置</text
    ><view class="panel settings-card"
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
          <text>{{ theme.icon }}</text
          ><text>{{ theme.label }}</text
          ><text v-if="themeChoice === theme.id" class="theme-check">✓</text>
        </button></view
      ></view
    ><view class="panel settings-card"
      ><text class="settings-section-title">记录与隐私</text
      ><view class="privacy-row"
        ><text>未登录</text><text>仅保留当前临时对话，不写入问诊历史。</text></view
      ><view class="privacy-row"
        ><text>登录后</text><text>后续问诊由服务端按账户保存，访客内容不会自动归档。</text></view
      ><view class="privacy-row"
        ><text>图片与对话</text
        ><text>图片由独立模型处理，对话服务只接收文字与识别回执。</text></view
      ></view
    ><view class="panel settings-card about-card"
      ><text class="settings-section-title">关于 AgriVision</text
      ><text>宛农植保助手 · {{ appVersion }}</text
      ><text class="settings-description"
        >面向小麦、玉米与花生的田间记录、初步识别与种植咨询。</text
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
</style>
