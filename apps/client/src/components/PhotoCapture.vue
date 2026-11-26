<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from './AppIcon.vue'
import { imageUrl, type Crop, type Meta, type CaseRecord } from '../lib/api'
const props = defineProps<{
  crop: Crop
  models: Meta['models']
  busy: boolean
  loading: boolean
  lastResult?: CaseRecord | null
  desktopWeb?: boolean
  pausedUpload?: string
}>()
const emit = defineEmits<{
  crop: [value: Crop]
  capture: [source: 'camera' | 'album']
  resume: []
  result: []
  'retry-upload': []
  'identify-crop': []
}>()
const choices: [Crop, string][] = [
  ['wheat', '小麦'],
  ['maize', '玉米'],
  ['peanut', '花生'],
]
const ready = computed(() => props.models.some((item) => item.crop === props.crop && item.ready))
const scope = computed(() => {
  if (props.loading) return '正在准备识别服务…'
  if (ready.value) return '已开放照片识别'
  return props.crop === 'wheat'
    ? '图片识别暂不可用，仍可询问 AI。'
    : '该作物暂未开放图片识别，可先询问 AI。'
})
</script>
<template>
  <view class="photo-page" :class="{ 'photo-desktop': desktopWeb }">
    <view class="photo-panel">
      <text class="photo-field-label">照片中的作物</text>
      <view class="crop-choices" role="group" aria-label="选择照片中的作物">
        <button
          v-for="[id, name] in choices"
          :key="id"
          :disabled="busy"
          :class="{ selected: crop === id }"
          :aria-pressed="crop === id"
          @click="emit('crop', id)"
        >
          <AppIcon :name="id" :size="25" /><text>{{ name }}</text>
        </button>
      </view>
      <button class="crop-lookup-link" :disabled="busy" @click="emit('identify-crop')">
        <AppIcon name="leaf" :size="17" /><text>不确定作物？识别作物</text
        ><AppIcon name="right" :size="15" />
      </button>
      <view class="camera-stage">
        <button
          class="capture-upload-area"
          :disabled="busy"
          :aria-label="desktopWeb ? '从电脑上传作物照片' : '拍摄作物照片'"
          @click="emit('capture', desktopWeb ? 'album' : 'camera')"
        >
          <view class="capture-guide-icon"
            ><AppIcon :name="desktopWeb ? 'upload' : 'camera'" :size="30"
          /></view>
          <text class="camera-title">{{ desktopWeb ? '上传电脑照片' : '拍清楚，再识别' }}</text>
          <text class="camera-description">{{
            desktopWeb
              ? '选择叶片或麦穗等异常部位的清晰近照，尽量使用原图'
              : '建议在光线充足时，清晰拍摄异常部位'
          }}</text>
        </button>
        <view class="capture-actions">
          <button
            class="button primary capture-main"
            :disabled="busy"
            :aria-label="desktopWeb ? '从电脑上传作物照片' : '拍摄作物照片'"
            @click="emit('capture', desktopWeb ? 'album' : 'camera')"
          >
            <AppIcon :name="desktopWeb ? 'upload' : 'camera'" white :size="21" />
            <text>{{ desktopWeb ? '选择照片' : '拍照识别' }}</text>
          </button>
          <button
            v-if="!desktopWeb"
            class="button secondary album-button"
            :disabled="busy"
            @click="emit('capture', 'album')"
          >
            <AppIcon name="image" :size="20" /><text>从相册选</text>
          </button>
        </view>
        <text class="capture-format">JPG、PNG、WebP · 单张不超过 8MB</text>
      </view>
      <view class="recognition-scope" role="status">
        <view class="scope-dot" :class="{ ready }" /><text>{{ scope }}</text>
      </view>
    </view>
    <!-- #ifdef H5 -->
    <view v-if="pausedUpload" class="paused-upload">
      <text role="status">当前网络已断开。照片暂留在本页，联网后可继续上传。</text>
      <button class="button quiet" @click="emit('retry-upload')">
        继续上传{{ pausedUpload }}照片
      </button>
    </view>
    <!-- #endif -->
    <button v-if="lastResult" class="recent-result" @click="emit('result')">
      <image :src="imageUrl(lastResult)" mode="aspectFill" />
      <view
        ><text>查看本次识别</text><text>{{ lastResult.title }}</text></view
      >
      <AppIcon name="right" :size="18" />
    </button>
    <button
      class="photo-consult-entry"
      :disabled="busy"
      aria-label="询问 AI"
      @click="emit('resume')"
    >
      <view class="photo-consult-icon"><AppIcon name="chat" :size="22" /></view>
      <view><text>不拍照，直接问</text><text>描述种植问题，询问 AI</text></view>
      <AppIcon name="right" :size="18" />
    </button>
    <text class="photo-tip">识别后可继续补充叶背和整株照片，帮助了解实际情况。</text>
  </view>
</template>
<style scoped>
.photo-page {
  max-width: 680px;
  margin: 0 auto 20px;
}
.photo-panel {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 20px;
  overflow: hidden;
}
.photo-field-label {
  display: block;
  margin: 18px 18px 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--muted);
}
.crop-choices {
  display: flex;
  gap: 6px;
  background: var(--subtle);
  padding: 4px;
  margin: 0 16px;
  border-radius: 14px;
}
.crop-choices > button {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  min-height: 44px;
  border: 1px solid transparent;
  border-radius: 11px;
  color: var(--muted);
}
.crop-choices > button.selected {
  color: var(--ink);
  background: var(--surface);
  border-color: var(--line);
}
.crop-lookup-link {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 44px;
  padding: 4px 12px;
  margin: 4px auto 0;
  border-radius: 12px;
  color: var(--accent);
  font-size: 13px;
}
.crop-lookup-link:active {
  background: var(--pressed);
}
.camera-stage {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px 18px 22px;
}
.capture-upload-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  min-height: 140px;
  padding: 12px;
  border: 1px dashed var(--line);
  border-radius: 16px;
  background: var(--elevated);
  cursor: pointer;
}
.capture-upload-area:hover {
  background: var(--hover);
}
.capture-upload-area:active {
  background: var(--pressed);
}
.capture-guide-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 60px;
  height: 60px;
  border-radius: 18px;
  background: var(--accent-soft);
  color: var(--accent);
}
.camera-title {
  display: block;
  font-size: 18px;
  font-weight: 600;
  color: var(--ink);
  margin-top: 16px;
}
.camera-description {
  display: block;
  text-align: center;
  font-size: 13px;
  line-height: 1.6;
  color: var(--muted);
  margin-top: 6px;
}
.capture-actions {
  display: flex;
  gap: 10px;
  width: 100%;
  max-width: 380px;
  margin-top: 22px;
}
.capture-main,
.album-button {
  flex: 1;
  min-height: 48px;
  padding: 10px 12px;
  border-radius: 13px;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
}
.capture-main {
  box-shadow: 0 2px 6px #0000000a;
}
.album-button {
  background: var(--elevated);
  border-color: var(--line);
}
.capture-format {
  display: block;
  text-align: center;
  margin-top: 12px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.5;
}
.recognition-scope {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  gap: 7px;
  border-top: 1px solid var(--line);
  padding: 12px 16px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--muted);
  background: var(--elevated);
}
.scope-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--muted);
  margin-top: 7px;
  flex-shrink: 0;
}
.scope-dot.ready {
  background: var(--accent);
}
.photo-tip {
  display: block;
  text-align: center;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.7;
  margin: 14px 8px 0;
}
.recent-result,
.photo-consult-entry {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 16px;
  text-align: left;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 16px;
  margin-top: 14px;
  color: var(--ink);
}
.recent-result > image {
  width: 46px;
  height: 46px;
  border-radius: 11px;
  flex-shrink: 0;
}
.recent-result > view,
.photo-consult-entry > view:nth-child(2) {
  min-width: 0;
  flex: 1;
}
.recent-result > view > text:first-child,
.photo-consult-entry > view:nth-child(2) > text:first-child {
  display: block;
  font-size: 14px;
  font-weight: 600;
}
.recent-result > view > text:last-child,
.photo-consult-entry > view:nth-child(2) > text:last-child {
  display: block;
  font-size: 12px;
  line-height: 1.6;
  color: var(--muted);
  margin-top: 3px;
}
.recent-result > view > text:last-child {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.photo-consult-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 42px;
  height: 42px;
  border-radius: 12px;
  background: var(--subtle);
}
.photo-desktop .camera-stage {
  padding: 32px 32px 28px;
}
.photo-desktop .capture-guide-icon {
  width: 72px;
  height: 72px;
  border-radius: 22px;
}
.photo-desktop .camera-title {
  font-size: 20px;
  margin-top: 20px;
}
.photo-desktop .capture-actions {
  max-width: 280px;
}
.photo-desktop .photo-field-label {
  margin-top: 22px;
}
.paused-upload {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 6px 14px;
  padding: 12px 14px;
  margin-top: 12px;
  border-radius: 14px;
  background: var(--warning-soft);
  color: var(--ink);
  font-size: 13px;
}
@media (max-width: 360px) {
  .capture-actions {
    gap: 8px;
  }
  .capture-main,
  .album-button {
    padding-inline: 8px;
  }
}
</style>
