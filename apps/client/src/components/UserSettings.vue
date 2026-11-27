<script setup lang="ts">
import AppIcon from './AppIcon.vue'
import { appVersion } from '../lib/appInfo'
import { dataMode } from '../lib/api'
import { themeChoice, setTheme } from '../lib/theme'
const themes = [
  { id: 'light' as const, label: '浅色', icon: 'sun' },
  { id: 'dark' as const, label: '深色', icon: 'moon' },
  { id: 'system' as const, label: '跟随系统', icon: 'system' },
]
const preview = dataMode() === 'preview'
defineProps<{ showBack?: boolean }>()
const emit = defineEmits<{ back: [] }>()
</script>
<template>
  <view class="user-settings">
    <!-- #ifndef MP-WEIXIN -->
    <button v-if="showBack" class="settings-back" @click="emit('back')">
      <AppIcon name="back" :size="17" /><text>返回我的</text>
    </button>
    <!-- #endif -->
    <view class="panel settings-card settings-appearance">
      <text class="appearance-label">外观</text>
      <view class="appearance-options" role="group" aria-label="选择外观">
        <button
          v-for="theme in themes"
          :key="theme.id"
          :aria-pressed="themeChoice === theme.id"
          :class="{ selected: themeChoice === theme.id }"
          @click="setTheme(theme.id)"
        >
          <AppIcon :name="theme.icon" :size="18" /><text>{{ theme.label }}</text>
        </button>
      </view>
    </view>
    <view class="panel settings-card"
      ><text class="settings-section-title">记录与隐私</text
      ><view class="privacy-row"
        ><text>测试说明</text
        ><text
          >个人开发的内测版本，当前仅管理员账号使用，不开放注册、不收费。登录用于身份核验与防滥用，不主动要求手机号或身份证信息。</text
        ></view
      ><view class="privacy-row"
        ><text>未登录</text
        ><text>可以阅读参考资料与农业资讯；识别、AI 对话和记录需登录。</text></view
      ><view class="privacy-row"
        ><text>登录后</text
        ><text>{{
          preview
            ? '演示记录仅保留在当前页面内存，刷新或退出后清除。'
            : '服务端保存照片、对话和登录会话。你可以在历史记录中删除记录。'
        }}</text></view
      ><view class="privacy-row"
        ><text>图片与对话</text
        ><text>{{
          preview
            ? '离线预览只使用本地数据。'
            : '照片由识别服务处理。使用 AI 问答时，必要的问题、历史对话、种植信息、识别摘要及所选文档和农业资料摘录会交给 DeepSeek。图片和文件原件不发送给 DeepSeek。'
        }}</text></view
      ></view
    ><view class="panel settings-card about-card"
      ><text class="settings-section-title">关于 AgriVision</text><text>版本 {{ appVersion }}</text
      ><text class="settings-description"
        >记录作物田间情况，提供照片辅助识别与种植问答。</text
      ></view
    ></view
  >
</template>
<style scoped>
.settings-appearance {
  margin-top: 12px;
  padding: 16px;
}
.appearance-label {
  display: block;
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 10px;
}
.appearance-options {
  display: flex;
  gap: 6px;
}
.appearance-options > button {
  display: flex;
  flex: 1;
  justify-content: center;
  align-items: center;
  gap: 6px;
  min-height: 44px;
  font-size: 12px;
  border: 1px solid transparent;
  border-radius: 10px;
  background: var(--subtle);
}
.appearance-options > button.selected {
  background: var(--accent-soft);
  color: var(--accent);
  border-color: var(--line);
}

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
/* #ifdef MP-WEIXIN */
.settings-back {
  margin-bottom: 12px;
}
/* #endif */
</style>
