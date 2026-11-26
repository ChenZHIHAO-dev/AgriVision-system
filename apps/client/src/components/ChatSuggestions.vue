<script setup lang="ts">
import { ref } from 'vue'
import AppIcon from './AppIcon.vue'
import type { ContextField, ContextSuggestion, PhotoSuggestion } from '../lib/api'

const props = defineProps<{
  context?: ContextSuggestion
  photo?: PhotoSuggestion
  disabled?: boolean
}>()
const emit = defineEmits<{
  select: [suggestion: ContextSuggestion, choice: { value: string; label: string }]
  skip: [field: ContextField]
  photo: []
}>()
const location = ref('')
const photoDismissed = ref(false)
function saveLocation() {
  const value = location.value.trim()
  if (value && props.context && !props.disabled)
    emit('select', props.context, { value, label: value })
}
</script>

<template>
  <view v-if="context || (photo && !photoDismissed)" class="chat-suggestions">
    <view v-if="context" class="suggestion-group">
      <view class="suggestion-heading">
        <text>{{ context.prompt }}</text
        ><text class="optional-label">选填</text>
      </view>
      <view v-if="context.field === 'location'" class="location-entry">
        <input
          v-model="location"
          aria-label="种植地区（选填）"
          placeholder="省、市或县即可"
          :maxlength="120"
          :disabled="disabled"
          :adjust-position="false"
          confirm-type="done"
          @confirm="saveLocation"
        />
        <button :disabled="disabled || !location.trim()" @click="saveLocation">保存</button>
      </view>
      <view v-else class="suggestion-options">
        <button
          v-for="choice in context.options"
          :key="choice.value"
          :disabled="disabled"
          @click="emit('select', context, choice)"
        >
          {{ choice.label }}
        </button>
      </view>
      <button class="skip-suggestion" :disabled="disabled" @click="emit('skip', context.field)">
        暂不填写
      </button>
    </view>
    <view v-if="photo && !photoDismissed" class="photo-suggestion">
      <view class="photo-copy"
        ><AppIcon name="camera" :size="18" /><text>{{ photo.prompt }}</text></view
      >
      <view class="photo-actions">
        <button :disabled="disabled" @click="emit('photo')">添加照片</button>
        <button class="skip-suggestion" :disabled="disabled" @click="photoDismissed = true">
          暂不拍照
        </button>
      </view>
    </view>
  </view>
</template>

<style scoped>
.chat-suggestions {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-top: 14px;
}
.suggestion-group,
.photo-suggestion {
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--surface);
}
.suggestion-heading {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  font-size: 13px;
  color: var(--ink);
}
.optional-label {
  font-size: 12px;
  color: var(--muted);
}
.suggestion-options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}
.chat-suggestions button {
  min-height: 44px;
  margin: 0;
  padding: 9px 13px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--subtle);
  color: var(--ink);
  font-size: 13px;
  line-height: 1.5;
}
.chat-suggestions button:disabled {
  opacity: 0.55;
}
.chat-suggestions .skip-suggestion {
  border-color: transparent;
  background: transparent;
  color: var(--muted);
  padding-left: 0;
}
.location-entry {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}
.location-entry input {
  flex: 1;
  width: 0;
  min-width: 0;
  height: 44px;
  padding: 0 12px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--subtle);
  color: var(--ink);
  font-size: 14px;
}
.photo-copy {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.6;
}
.photo-copy text {
  flex: 1;
  min-width: 0;
}
.photo-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 10px;
}
</style>
