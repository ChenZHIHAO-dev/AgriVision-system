<script setup lang="ts">
import { ref } from 'vue'
import AppIcon from './AppIcon.vue'
import UiDialog from './UiDialog.vue'
import { crops } from '../lib/options'
import type { Crop } from '../lib/api'

defineProps<{ photo: string; busy: boolean }>()
const emit = defineEmits<{ close: []; confirm: [crop: Crop] }>()
// 每次打开新照片都从未选择开始，避免默认值被当成识别结论。
const selected = ref<Crop | null>(null)
function confirm() {
  if (selected.value) emit('confirm', selected.value)
}
</script>

<template>
  <UiDialog
    title="先确认照片中的作物"
    subtitle="选择后再识别，不确定时可先继续文字提问。"
    @close="emit('close')"
  >
    <image :src="photo" mode="aspectFit" class="chat-photo-preview" aria-label="待识别照片" />
    <text class="photo-field-label">照片中的作物</text>
    <view class="photo-crop-choices" role="group" aria-label="选择照片中的作物">
      <button
        v-for="option in crops"
        :key="option.id"
        :disabled="busy"
        :class="{ active: selected === option.id }"
        :aria-pressed="selected === option.id"
        @click="selected = option.id"
      >
        <AppIcon :name="option.id" :size="22" /><text>{{ option.name }}</text>
      </button>
    </view>
    <text class="photo-choice-hint" role="status">{{
      selected ? '按所选作物识别这张照片。' : '尚未选择作物'
    }}</text>
    <text class="photo-choice-note"
      >请按照片中的实际作物选择。其他作物可以先描述情况，直接向 AI 提问。</text
    >
    <template #footer>
      <view class="photo-confirm-actions">
        <button class="button primary full-width" :disabled="busy || !selected" @click="confirm">
          {{ busy ? '正在识别…' : '确认作物并识别' }}
        </button>
        <button class="button quiet full-width" :disabled="busy" @click="emit('close')">
          先不识别，继续文字提问
        </button>
      </view>
    </template>
  </UiDialog>
</template>

<style scoped>
.photo-confirm-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.chat-photo-preview {
  display: block;
  width: 100%;
  height: 160px;
  border-radius: 14px;
  background: var(--subtle);
  margin-bottom: 20px;
}
.photo-field-label {
  display: block;
  color: var(--ink);
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 10px;
}
.photo-crop-choices {
  display: flex;
  gap: 8px;
}
.photo-crop-choices > button {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 48px;
  padding: 8px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--surface);
  color: var(--ink);
  font-size: 14px;
}
.photo-crop-choices > button.active {
  border-color: var(--accent);
  background: var(--accent-soft);
  color: var(--accent);
}
.photo-crop-choices > button:active {
  background: var(--pressed);
}
.photo-choice-hint {
  display: block;
  margin-top: 10px;
  color: var(--muted);
  font-size: 13px;
}
.photo-choice-note {
  display: block;
  margin-top: 18px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.7;
}
</style>
