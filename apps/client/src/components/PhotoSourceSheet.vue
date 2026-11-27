<script setup lang="ts">
import UiDialog from './UiDialog.vue'
import AppIcon from './AppIcon.vue'
import type { Crop } from '../lib/api'
import { crops } from '../lib/options'
defineProps<{ crop: Crop; allowCrop?: boolean }>()
const emit = defineEmits<{ close: []; choose: [source: 'camera' | 'album']; crop: [value: Crop] }>()
</script>
<template>
  <UiDialog
    title="添加症状照片"
    subtitle="拍清有异常的部位，先获得初步识别结果。"
    @close="emit('close')"
    ><view v-if="allowCrop" class="photo-crop-field"
      ><text class="field-label">照片中的作物</text
      ><view class="intake-crops"
        ><button
          v-for="item in crops"
          :key="item.id"
          :class="{ selected: crop === item.id }"
          :aria-pressed="crop === item.id"
          @click="emit('crop', item.id)"
        >
          {{ item.name }}
        </button></view
      ></view
    ><view class="photo-source-list"
      ><button @click="emit('choose', 'camera')">
        <view class="source-symbol"><AppIcon name="camera" :size="27" /></view
        ><view><text>拍照</text><text>使用手机或设备相机拍摄</text></view
        ><text>›</text></button
      ><button @click="emit('choose', 'album')">
        <view class="source-symbol"><AppIcon name="upload" :size="26" /></view
        ><view><text>从相册或文件上传</text><text>选择已经拍好的症状照片</text></view
        ><text>›</text>
      </button></view
    ><text class="photo-source-tip"
      >先拍一张清晰近照，再按需要补充叶背和整株照片。地区与生育期可在对话时补充。</text
    ></UiDialog
  >
</template>
<style scoped>
.intake-crops {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 7px;
  margin: 9px 0 18px;
  background: var(--subtle);
  padding: 5px;
  border-radius: 12px;
}
.intake-crops > button {
  min-width: 0;
  min-height: 48px;
  white-space: nowrap;
  padding: 10px 8px;
  border-radius: 9px;
  font-size: 13px;
  color: var(--muted);
  border: 1px solid transparent;
}
.intake-crops > button.selected {
  background: var(--surface);
  border-color: var(--line);
  color: var(--ink);
}

.photo-source-list {
  display: flex;
  flex-direction: column;
  gap: 11px;
  margin: 5px 0 17px;
}
.photo-source-list > button {
  display: flex;
  align-items: center;
  gap: 15px;
  width: 100%;
  padding: 17px 15px;
  border: 1px solid var(--line);
  background: var(--surface);
  border-radius: 14px;
  text-align: left;
  color: var(--ink);
}
.source-symbol {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 45px;
  height: 45px;
  background: var(--subtle);
  border-radius: 13px;
}
.photo-source-list > button > view:nth-child(2) {
  flex: 1;
}
.photo-source-list > button > view:nth-child(2) > text:first-child {
  display: block;
  font-size: 14px;
  font-weight: 550;
}
.photo-source-list > button > view:nth-child(2) > text:last-child {
  display: block;
  font-size: 11px;
  color: var(--muted);
  margin-top: 5px;
}
.photo-source-list > button > text {
  font-size: 23px;
  color: var(--muted);
}
.photo-source-tip {
  display: block;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.9;
}
@media (max-width: 360px) {
  .intake-crops {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
