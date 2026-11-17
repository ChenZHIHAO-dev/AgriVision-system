<script setup lang="ts">
import ChoicePicker from './ChoicePicker.vue'
import type { ChatModel } from '../lib/api'
const props = defineProps<{ modelValue: ChatModel; disabled?: boolean; webSearch?: boolean }>()
const emit = defineEmits<{
  'update:modelValue': [value: ChatModel]
  'update:webSearch': [value: boolean]
}>()
function choose(value: string) {
  emit('update:modelValue', value as ChatModel)
  if (value !== 'deepseek-flash') emit('update:webSearch', false)
}
const options = [
  {
    value: 'deepseek-flash',
    label: 'DeepSeek Flash',
    symbol: '⚡',
    description: '日常种植咨询，轻快响应',
  },
  {
    value: 'deepseek-v4-pro',
    label: 'DeepSeek V4 Pro',
    symbol: '✦',
    description: '复杂问题分析与资料问答',
  },
]
</script>
<template>
  <ChoicePicker
    :model-value="modelValue"
    :options="options"
    label="选择对话模型"
    caption="切换模型后，当前对话继续保留"
    compact
    above
    :disabled="disabled"
    @update:model-value="choose"
    ><template #footer
      ><button
        class="model-web-option"
        role="switch"
        tabindex="0"
        :aria-checked="!!webSearch"
        :disabled="disabled || modelValue !== 'deepseek-flash'"
        @click="emit('update:webSearch', !webSearch)"
      >
        <view
          ><text class="web-title">联网检索</text
          ><text class="web-caption">{{
            modelValue === 'deepseek-flash'
              ? '按需检索公开资料，回答附来源'
              : '联网检索目前支持 DeepSeek Flash'
          }}</text></view
        ><text class="web-switch" :class="{ on: webSearch }"><text /></text></button
      ><text class="web-footnote"
        >图像由独立识别模型处理；对话模型只接收文字与识别回执。</text
      ></template
    ></ChoicePicker
  >
</template>
<style scoped>
.model-web-option {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 15px;
  padding: 5px 0 9px;
  text-align: left;
  color: var(--ink);
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
}
.web-switch {
  display: flex;
  align-items: center;
  width: 34px;
  min-width: 34px;
  height: 21px;
  border-radius: 12px;
  background: var(--line);
  padding: 3px;
  box-sizing: border-box;
}
.web-switch > text {
  width: 15px;
  height: 15px;
  background: var(--surface);
  border-radius: 50%;
  box-shadow: 0 1px 3px #0002;
}
.web-switch.on {
  background: var(--accent);
  justify-content: flex-end;
}
.web-switch.on > text {
  background: var(--accent-ink);
}
.web-footnote {
  font-size: 10px;
  color: var(--muted);
  line-height: 1.8;
  display: block;
  margin-top: 7px;
}
</style>
