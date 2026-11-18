<script setup lang="ts">
import ChoicePicker from './ChoicePicker.vue'
import type { ChatModel } from '../lib/api'
const props = defineProps<{ modelValue: ChatModel; disabled?: boolean; webSearch?: boolean }>()
const emit = defineEmits<{
  'update:modelValue': [value: ChatModel]
  'update:webSearch': [value: boolean]
}>()
const captionId = 'web-caption-' + Math.random().toString(36).slice(2, 9)
function choose(value: string) {
  emit('update:modelValue', value as ChatModel)
  if (value !== 'deepseek-flash') emit('update:webSearch', false)
}
const options = [
  {
    value: 'deepseek-flash',
    label: 'DeepSeek Flash',
    description: '日常咨询与公开资料检索',
  },
  {
    value: 'deepseek-v4-pro',
    label: 'DeepSeek V4 Pro',
    description: '复杂问题与长资料分析',
  },
]
</script>
<template>
  <ChoicePicker
    :model-value="modelValue"
    :options="options"
    label="选择对话模型"
    caption=""
    compact
    above
    :disabled="disabled"
    @update:model-value="choose"
  >
    <template #footer>
      <view class="model-web-option">
        <view class="web-copy">
          <text class="web-title">联网检索</text>
          <text :id="captionId" class="web-caption">{{
            modelValue === 'deepseek-flash'
              ? '按需检索公开资料，回答附来源'
              : '联网检索目前支持 DeepSeek Flash'
          }}</text>
        </view>
        <button
          class="web-toggle"
          role="switch"
          aria-label="联网检索"
          :aria-describedby="captionId"
          :aria-checked="!!webSearch && modelValue === 'deepseek-flash'"
          :disabled="disabled || modelValue !== 'deepseek-flash'"
          hover-class="none"
          @click.stop="emit('update:webSearch', !webSearch)"
        >
          <view class="web-switch" :class="{ on: webSearch && modelValue === 'deepseek-flash' }">
            <view class="web-knob" />
          </view>
        </button>
      </view>
    </template>
  </ChoicePicker>
</template>
<style scoped>
.model-web-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 0 0 6px;
  text-align: left;
  color: var(--ink);
}
.web-copy {
  flex: 1;
  min-width: 0;
}
.web-title {
  display: block;
  font-size: 12px;
  font-weight: 550;
}
.web-caption {
  display: block;
  color: var(--muted);
  font-size: 10px;
  margin-top: 3px;
  line-height: 1.7;
}
.web-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  min-width: 48px;
  height: 44px;
  border-radius: 12px;
  background: transparent !important;
  padding: 0;
}
.web-toggle:hover,
.web-toggle:active,
.web-toggle[disabled] {
  background: transparent !important;
}
.web-toggle[disabled] {
  opacity: 0.5;
}
.web-switch {
  position: relative;
  display: block;
  width: 38px;
  height: 24px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--line);
  transition:
    background-color 0.18s ease,
    border-color 0.18s ease;
}
.web-knob {
  position: absolute;
  width: 18px;
  height: 18px;
  top: 2px;
  left: 2px;
  background: #f8f9fb;
  border-radius: 50%;
  box-shadow: 0 1px 4px #0003;
  transform: translateX(0);
  transition: transform 0.18s ease;
}
.web-switch.on {
  background: var(--accent);
  border-color: var(--accent);
}
.web-switch.on > .web-knob {
  transform: translateX(14px);
  background: var(--accent-ink);
}
@media (prefers-reduced-motion: reduce) {
  .web-switch,
  .web-knob {
    transition: none;
  }
}
</style>
