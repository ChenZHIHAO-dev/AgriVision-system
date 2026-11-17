<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import ModelPicker from './ModelPicker.vue'
// #ifdef H5
import NativeChatInput from './NativeChatInput'
// #endif
import type { ChatModel, DocumentAttachment } from '../lib/api'

const props = withDefaults(
  defineProps<{
    modelValue: string
    disabled?: boolean
    model: ChatModel
    thinking: boolean
    webSearch: boolean
    attachments: DocumentAttachment[]
    images: { id: string; url: string }[]
    preview: boolean
  }>(),
  { disabled: false },
)
const emit = defineEmits<{
  'update:modelValue': [value: string]
  'update:model': [value: ChatModel]
  'update:thinking': [value: boolean]
  'update:webSearch': [value: boolean]
  send: []
  attach: [kind: 'image' | 'document']
  remove: [id: string]
  'remove-image': [id: string]
  resize: []
  limit: []
  keyboard: [height: number]
}>()
const attachOpen = ref(false)
function attachmentKeyboard(event: KeyboardEvent) {
  // #ifdef H5
  if (!attachOpen.value) return
  if (event.key === 'Escape') {
    event.preventDefault()
    attachOpen.value = false
    document.querySelector<HTMLElement>('.add-attachment')?.focus()
  }
  // #endif
}
watch(attachOpen, async (value) => {
  // #ifdef H5
  if (value) {
    await nextTick()
    document.querySelector<HTMLElement>('.attachment-menu [role="menuitem"]')?.focus()
  }
  // #endif
})
onMounted(() => {
  // #ifdef H5
  document.addEventListener('keydown', attachmentKeyboard)
  // #endif
})
onUnmounted(() => {
  // #ifdef H5
  document.removeEventListener('keydown', attachmentKeyboard)
  // #endif
})
function attach(kind: 'image' | 'document') {
  attachOpen.value = false
  emit('attach', kind)
}
function input(event: unknown) {
  const value = event as { detail?: { value?: string }; target?: { value?: string } }
  emit('update:modelValue', value.detail?.value ?? value.target?.value ?? '')
}
</script>
<template>
  <view class="chat-composer-shell">
    <view v-if="attachments.length" class="composer-attachments"
      ><view v-for="file in attachments" :key="file.id" class="attachment-chip"
        ><text class="file-icon">▤</text
        ><view class="flex-one"
          ><text class="file-name">{{ file.name }}</text
          ><text class="file-status">{{
            file.extraction === 'requires-backend' ? '资料解析服务暂不可用' : '资料文字已准备'
          }}</text></view
        ><button
          class="file-remove"
          :aria-label="'移除附件 ' + file.name"
          :disabled="disabled"
          @click="emit('remove', file.id)"
        >
          ×
        </button></view
      ></view
    >
    <view v-if="images.length" class="composer-photo-rail"
      ><view v-for="(image, index) in images" :key="image.id" class="composer-photo"
        ><image :src="image.url" mode="aspectFill" /><button
          :disabled="disabled"
          :aria-label="'移除第' + (index + 1) + '张待发送照片'"
          @click="emit('remove-image', image.id)"
        >
          ×</button
        ><text>已处理 · 待发送</text></view
      ></view
    >
    <view class="composer-writing-area">
      <!-- #ifdef H5 -->
      <NativeChatInput
        :model-value="modelValue"
        :disabled="disabled"
        @update:model-value="emit('update:modelValue', $event)"
        @send="emit('send')"
        @resize="emit('resize')"
        @limit="emit('limit')"
      />
      <!-- #endif -->
      <!-- #ifndef H5 -->
      <textarea
        class="mp-chat-input"
        :value="modelValue"
        :auto-height="false"
        :maxlength="12000"
        :disabled="disabled"
        :adjust-position="false"
        placeholder="描述情况，或添加照片、资料继续问…"
        confirm-type="send"
        @input="input"
        @confirm="emit('send')"
        @keyboardheightchange="emit('keyboard', $event.detail.height)"
      />
      <!-- #endif -->
    </view>
    <view class="composer-controls">
      <button
        class="add-attachment"
        aria-label="添加附件"
        :aria-expanded="attachOpen"
        :disabled="disabled"
        @click="attachOpen = !attachOpen"
      >
        ＋
      </button>
      <view class="composer-model"
        ><ModelPicker
          :model-value="model"
          :disabled="disabled"
          :web-search="webSearch"
          @update:model-value="emit('update:model', $event)"
          @update:web-search="emit('update:webSearch', $event)"
      /></view>
      <button
        class="thinking-toggle"
        :class="{ active: thinking }"
        :aria-pressed="thinking"
        :disabled="disabled"
        @click="emit('update:thinking', !thinking)"
      >
        <text>◈</text><text>深度思考</text>
      </button>
      <text v-if="modelValue.length > 8000" class="input-count">{{ modelValue.length }}/12000</text>
      <button
        class="composer-send"
        aria-label="发送消息"
        :disabled="disabled || (!modelValue.trim() && !attachments.length && !images.length)"
        @click="emit('send')"
      >
        <text>{{ disabled ? '…' : '↑' }}</text>
      </button>
    </view>
    <view v-if="attachOpen" class="attachment-dismiss" @click="attachOpen = false" />
    <view v-if="attachOpen" class="attachment-menu" role="menu"
      ><button role="menuitem" @click="attach('image')">
        <text>▧</text
        ><view
          ><text class="strong">添加症状照片</text
          ><text class="file-status">照片先独立识别，再带结果继续咨询</text></view
        ></button
      ><button role="menuitem" @click="attach('document')">
        <text>▤</text
        ><view
          ><text class="strong">上传资料文件</text
          ><text class="file-status">TXT、MD、PDF、DOCX · 8MB 以内</text></view
        >
      </button></view
    >
  </view>
  <view class="chat-composer-meta"
    ><text>{{
      preview ? '智能咨询服务暂不可用，当前提供资料参考' : '建议供排查参考，具体用药请核对产品标签'
    }}</text
    ><text class="composer-shortcut">Enter 发送 · Shift + Enter 换行</text></view
  >
</template>
<style scoped>
.composer-photo-rail {
  display: flex;
  gap: 9px;
  overflow-x: auto;
  padding: 0 0 12px;
  max-height: 96px;
}
.composer-photo {
  position: relative;
  width: 82px;
  min-width: 82px;
  height: 78px;
  border-radius: 11px;
  overflow: hidden;
  border: 1px solid var(--line);
  background: var(--subtle);
}
.composer-photo > image {
  width: 100%;
  height: 100%;
}
.composer-photo > button {
  position: absolute;
  right: 3px;
  top: 3px;
  width: 21px;
  height: 21px;
  border-radius: 50%;
  background: #1a1c20c9;
  color: #fff;
  font-size: 17px;
  line-height: 20px;
}
.composer-photo > text {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  font-size: 9px;
  background: #1a1c20b0;
  color: #fff;
  padding: 3px;
  text-align: center;
}

.chat-composer-shell {
  position: relative;
  background: var(--elevated);
  border: 1px solid var(--line);
  border-radius: 23px;
  padding: 15px 14px 11px;
  box-shadow: 0 4px 20px #00000006;
  min-width: 0;
  overflow: visible;
}
.chat-composer-shell:focus-within {
  border-color: var(--focus);
  box-shadow: 0 0 0 2px var(--subtle);
}
.composer-writing-area {
  min-width: 0;
  padding: 0 4px 10px;
  overflow: hidden;
}
.composer-writing-area :deep(.native-chat-input) {
  display: block;
  width: 100%;
  min-width: 0;
  min-height: 30px;
  max-height: 180px;
  border: 0;
  border-radius: 0;
  margin: 0;
  padding: 0;
  resize: none;
  outline: 0;
  color: var(--ink);
  background: transparent;
  font: inherit;
  font-size: 14px;
  line-height: 1.9;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  box-sizing: border-box;
  caret-color: var(--accent);
  scrollbar-width: thin;
  scrollbar-color: var(--line) transparent;
}
.composer-writing-area :deep(.native-chat-input::placeholder) {
  color: var(--muted);
  opacity: 1;
}
.mp-chat-input {
  height: 88px;
  width: 100%;
  font-size: 15px;
  line-height: 1.8;
  color: var(--ink);
}
.composer-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 38px;
  min-width: 0;
}
.add-attachment {
  width: 33px;
  min-width: 33px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 25px;
  line-height: 1;
  border-radius: 9px;
  color: var(--ink);
}
.add-attachment:hover {
  background: var(--subtle);
}
.composer-model {
  width: 170px;
  max-width: 42%;
  min-width: 0;
}
.composer-model :deep(.select-wrapper) {
  min-height: 33px;
  border: 0;
  background: var(--subtle);
  border-radius: 9px;
}
.composer-model :deep(.native-select) {
  height: 33px;
  font-size: 11px;
  padding-left: 10px;
  padding-right: 30px;
}
.composer-model :deep(.select-chevron) {
  top: 10px !important;
  right: 9px !important;
}
.composer-model :deep(.select-native) {
  font-size: 11px;
  padding: 6px 10px;
}
.thinking-toggle {
  display: flex;
  gap: 5px;
  align-items: center;
  border: 1px solid var(--line);
  background: var(--subtle);
  border-radius: 9px;
  padding: 6px 9px;
  min-height: 33px;
  white-space: nowrap;
  color: var(--muted);
  font-size: 11px;
}
.thinking-toggle.active {
  color: var(--ink);
  border-color: var(--focus);
  background: var(--accent-soft);
}
.thinking-toggle > text:first-child {
  font-size: 15px;
}
.composer-send {
  margin-left: auto;
  width: 35px;
  min-width: 35px;
  height: 35px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--accent);
  color: var(--accent-ink);
  font-size: 24px;
  line-height: 1;
}
.input-count {
  font-size: 9px;
  color: var(--muted);
  margin-left: auto;
  white-space: nowrap;
}
.input-count + .composer-send {
  margin-left: 0;
}
.chat-composer-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--muted);
  font-size: 10px;
  padding: 9px 4px 0;
  line-height: 1.7;
}
.composer-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 11px;
  max-height: 120px;
  overflow-y: auto;
}
.attachment-chip {
  display: flex;
  align-items: center;
  gap: 9px;
  background: var(--subtle);
  border: 1px solid var(--line);
  padding: 7px 9px;
  border-radius: 11px;
  max-width: 100%;
  width: 260px;
  min-width: 0;
}
.file-icon {
  font-size: 20px;
  color: var(--muted);
}
.file-name {
  display: block;
  font-size: 11px;
  font-weight: 550;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-status {
  display: block;
  font-size: 9px;
  color: var(--muted);
  line-height: 1.8;
  margin-top: 2px;
}
.file-remove {
  width: 25px;
  height: 25px;
  min-width: 25px;
  border-radius: 7px;
  font-size: 18px;
  color: var(--muted);
}
.attachment-dismiss {
  position: fixed;
  inset: 0;
  z-index: 80;
}
.attachment-menu {
  position: absolute;
  z-index: 81;
  bottom: 54px;
  left: 9px;
  width: 300px;
  max-width: calc(100vw - 34px);
  background: var(--elevated);
  border: 1px solid var(--line);
  border-radius: 16px;
  box-shadow: 0 12px 45px #0002;
  padding: 8px;
}
.attachment-menu > button {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 11px 10px;
  width: 100%;
  text-align: left;
  border-radius: 10px;
  font-size: 12px;
}
.attachment-menu > button:hover {
  background: var(--subtle);
}
.attachment-menu > button > text {
  font-size: 21px;
  color: var(--muted);
}
@media (max-width: 760px) {
  .chat-composer-shell {
    padding: 13px 10px 10px;
    border-radius: 21px;
  }
  .composer-writing-area {
    padding-left: 4px;
    padding-right: 4px;
  }
  .composer-writing-area :deep(.native-chat-input) {
    font-size: 16px;
    line-height: 1.8;
  }
  .composer-controls {
    gap: 5px;
  }
  .composer-model {
    max-width: 43%;
    width: 156px;
  }
  .thinking-toggle {
    font-size: 10px;
    padding: 6px 7px;
    gap: 4px;
  }
  .add-attachment {
    width: 30px;
    min-width: 30px;
  }
  .composer-send {
    width: 33px;
    height: 33px;
    min-width: 33px;
  }
  .composer-shortcut {
    display: none;
  }
  .chat-composer-meta {
    justify-content: center;
    font-size: 10px;
    line-height: 1.8;
    text-align: center;
  }
  .attachment-chip {
    width: 100%;
  }
  .input-count {
    display: none;
  }
  .attachment-menu {
    bottom: 54px;
    left: 0;
  }
}
</style>
