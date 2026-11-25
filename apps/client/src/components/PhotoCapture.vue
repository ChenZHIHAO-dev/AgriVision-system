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
  <view class="photo-page">
    <text class="photo-subtitle">选择作物，拍摄或上传症状照片。</text>
    <view class="photo-panel">
      <view class="crop-choices" role="group" aria-label="选择照片中的作物"
        ><button
          v-for="[id, name] in choices"
          :key="id"
          :class="{ selected: crop === id }"
          :aria-pressed="crop === id"
          @click="emit('crop', id)"
        >
          <AppIcon :name="id" :size="27" /><text>{{ name }}</text>
        </button></view
      >
      <button class="crop-lookup-link" :disabled="busy" @click="emit('identify-crop')">
        <AppIcon name="leaf" :size="17" />
        <text>不确定作物？识别作物</text>
        <AppIcon name="right" :size="15" />
      </button>
      <view class="camera-stage"
        ><view class="camera-halo"
          ><button
            class="button primary camera-shutter"
            :aria-label="desktopWeb ? '从电脑上传作物照片' : '拍摄作物照片'"
            :disabled="busy"
            @click="emit('capture', desktopWeb ? 'album' : 'camera')"
          >
            <AppIcon :name="desktopWeb ? 'upload' : 'camera'" white :size="39" /></button></view
        ><text class="camera-title">{{ desktopWeb ? '从电脑上传作物照片' : '拍摄作物照片' }}</text
        ><text class="camera-description">{{
          desktopWeb ? '选择清晰的症状近照，单张不超过 8MB' : '对准有异常的叶片，保持画面清晰'
        }}</text
        ><button
          v-if="!desktopWeb"
          class="album-button"
          :disabled="busy"
          @click="emit('capture', 'album')"
        >
          <AppIcon name="upload" :size="17" /><text>从相册上传</text>
        </button></view
      >
      <view class="recognition-scope"
        ><view class="scope-dot" :class="{ ready }" /><text>{{ scope }}</text></view
      >
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
      <view class="photo-consult-icon"><AppIcon name="chat" :size="23" /></view>
      <view><text>不拍照，直接问</text><text>询问种植问题或了解药品作用</text></view>
      <AppIcon name="right" :size="18" />
    </button>
    <text class="photo-tip">可在同一条记录中补充叶背和整株照片。单张不超过 8MB。</text>
  </view>
</template>
<style scoped>
.photo-page {
  max-width: 680px;
  margin: 8px auto 20px;
}
.photo-subtitle {
  display: block;
  margin-bottom: 18px;
  font-size: 13px;
  color: var(--muted);
  margin-top: 9px;
  line-height: 1.8;
}
.photo-panel {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 22px;
  overflow: hidden;
}
.crop-choices {
  display: flex;
  gap: 6px;
  background: var(--subtle);
  padding: 5px;
  margin: 20px 22px 0;
  border-radius: 13px;
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
.crop-lookup-link:hover,
.crop-lookup-link:active {
  background: var(--hover);
}
.crop-choices > button {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  min-height: 43px;
  border-radius: 10px;
  color: var(--muted);
  border: 1px solid transparent;
}
.crop-choices > button.selected {
  background: var(--accent-soft);
  color: var(--accent);
  border-color: var(--line);
}
.camera-stage {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 30px 20px 27px;
}
.camera-halo {
  padding: 18px;
  background: var(--subtle);
  border-radius: 50%;
}
.camera-shutter {
  width: 92px;
  height: 92px;
  min-width: 92px;
  border-radius: 50%;
  padding: 0;
  box-shadow: 0 6px 18px #00000012;
}
.camera-title {
  font-size: 17px;
  font-weight: 600;
  margin-top: 21px;
}
.camera-description {
  font-size: 12px;
  color: var(--muted);
  margin-top: 8px;
}
.album-button {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  font-size: 13px;
  margin-top: 22px;
  padding: 10px 19px;
  min-height: 42px;
  border: 1px solid var(--line);
  border-radius: 11px;
  background: var(--elevated);
  color: var(--ink);
}
.recognition-scope {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  gap: 7px;
  border-top: 1px solid var(--line);
  padding: 13px 18px;
  font-size: 11px;
  line-height: 1.8;
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
  font-size: 11px;
  color: var(--muted);
  line-height: 1.9;
  margin: 17px 10px 0;
}
@media (max-width: 760px) {
  .photo-page {
    margin: 5px auto 10px;
  }
  .photo-subtitle {
    font-size: 11px;
    line-height: 1.8;
  }
  .crop-choices {
    margin: 15px 15px 0;
  }
  .camera-stage {
    padding: 26px 15px;
  }
  .camera-halo {
    padding: 15px;
  }
  .camera-shutter {
    width: 85px;
    height: 85px;
    min-width: 85px;
  }
  .camera-title {
    margin-top: 17px;
    font-size: 16px;
  }
  .camera-description {
    font-size: 11px;
  }
  .album-button {
    margin-top: 18px;
  }
  .recognition-scope {
    font-size: 10px;
    padding: 11px 14px;
  }
  .photo-tip {
    font-size: 10px;
    margin-top: 15px;
  }
}
.recent-result {
  display: flex;
  align-items: center;
  gap: 13px;
  text-align: left;
  background: var(--surface);
  width: 100%;
  border-radius: 15px;
  padding: 13px 15px;
  margin-top: 18px;
}
.recent-result > image {
  width: 46px;
  height: 46px;
  border-radius: 11px;
  flex-shrink: 0;
}
.recent-result > view {
  min-width: 0;
  flex: 1;
}
.recent-result > view > text:first-child {
  display: block;
  font-size: 13px;
  font-weight: 550;
}
.recent-result > view > text:last-child {
  display: block;
  font-size: 11px;
  color: var(--muted);
  margin-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.photo-consult-entry {
  display: flex;
  align-items: center;
  gap: 13px;
  text-align: left;
  background: var(--surface);
  border: 1px solid var(--line);
  padding: 17px;
  width: 100%;
  border-radius: 16px;
  margin-top: 17px;
}
.photo-consult-icon {
  width: 43px;
  height: 43px;
  border-radius: 13px;
  background: var(--subtle);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.photo-consult-entry > view:nth-child(2) {
  flex: 1;
  min-width: 0;
}
.photo-consult-entry > view:nth-child(2) > text:first-child {
  display: block;
  font-size: 14px;
  font-weight: 650;
}
.photo-consult-entry > view:nth-child(2) > text:last-child {
  display: block;
  margin-top: 4px;
  color: var(--muted);
  font-size: 11px;
}
@media (max-width: 760px) {
  .photo-subtitle {
    margin-top: 0;
  }
}
/* #ifdef H5 */
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
@media (max-width: 760px) {
}
.album-button {
  min-height: 44px;
}
/* #endif */
</style>
