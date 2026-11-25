<script setup lang="ts">
import { computed } from 'vue'
import UiDialog from './UiDialog.vue'
import AppIcon from './AppIcon.vue'
import { crops } from '../lib/options'
import type { Crop, CropIdentification, Meta } from '../lib/api'

const props = defineProps<{
  ready: boolean
  diagnosisModels: Meta['models']
  desktopWeb: boolean
  busy: boolean
  photo: string
  result: CropIdentification | null
  error: string
}>()
const emit = defineEmits<{
  close: []
  photo: [source: 'album' | 'camera']
  select: [crop: Crop]
}>()

const accepted = computed(() =>
  props.result?.status === 'recognized'
    ? props.result.candidates.find((item) => item.id === props.result?.crop_id)
    : undefined,
)
const supportedCrop = computed(() => crops.find((item) => item.id === accepted.value?.id))
const diagnosisReady = computed(() =>
  props.diagnosisModels.some((model) => model.crop === supportedCrop.value?.id && model.ready),
)
const status = computed(() => {
  if (props.busy) return '正在识别作物…'
  if (props.error) return props.error
  if (!props.ready || props.result?.status === 'model_unavailable')
    return '作物识别模型尚未开放。你可以手动选择作物。'
  if (props.result?.status === 'service_error') return '作物识别暂时不可用，请重试或手动选择。'
  if (props.result?.status === 'needs_retake') return '照片不够清晰，请在光线充足处补拍整株。'
  if (accepted.value && !diagnosisReady.value) return '此作物目前仅可查看作物识别结果。'
  if (accepted.value) return '确认作物后，再拍摄异常部位识别症状。'
  if (props.result?.status === 'uncertain') return '暂未确认作物，可补拍或手动选择。'
  return '拍摄整株，尽量保留叶、茎、穗或果实特征。'
})
</script>

<template>
  <UiDialog title="识别作物" subtitle="先确认是什么作物，再识别病虫害。" @close="emit('close')">
    <image v-if="photo" class="crop-lookup-photo" :src="photo" mode="aspectFit" />
    <text v-if="accepted" class="crop-lookup-name">可能是{{ accepted.name }}</text>
    <text class="crop-lookup-status" role="status">{{ status }}</text>
    <text v-for="issue in result?.quality_issues || []" :key="issue" class="crop-lookup-status">
      {{ issue }}
    </text>
    <view
      v-if="result?.status === 'uncertain' && result.candidates.length"
      class="crop-lookup-candidates"
    >
      <text v-for="item in result.candidates" :key="item.id">{{ item.name }}</text>
    </view>
    <view v-if="ready" class="crop-lookup-actions">
      <button
        v-if="!desktopWeb"
        class="button secondary"
        :disabled="busy"
        @click="emit('photo', 'camera')"
      >
        <AppIcon name="camera" :size="18" />拍整株
      </button>
      <button class="button secondary" :disabled="busy" @click="emit('photo', 'album')">
        <AppIcon name="upload" :size="18" />{{ desktopWeb ? '上传整株照片' : '从相册上传' }}
      </button>
    </view>
    <view v-if="!busy" class="crop-lookup-manual">
      <button
        v-if="supportedCrop && diagnosisReady"
        class="button primary full-width"
        @click="emit('select', supportedCrop.id)"
      >
        使用{{ supportedCrop.name }}进入症状识别
      </button>
      <text class="crop-lookup-status">{{ accepted ? '更正作物' : '手动选择' }}</text>
      <view class="crop-lookup-actions">
        <button
          v-for="item in crops"
          :key="item.id"
          class="button quiet"
          @click="emit('select', item.id)"
        >
          <AppIcon :name="item.id" :size="20" />{{ item.name }}
        </button>
      </view>
    </view>
  </UiDialog>
</template>

<style scoped>
.crop-lookup-photo {
  width: 100%;
  height: 160px;
  border-radius: 14px;
  background: var(--subtle);
  margin-bottom: 12px;
}
.crop-lookup-name,
.crop-lookup-status {
  display: block;
}
.crop-lookup-name {
  color: var(--ink);
  font-size: 17px;
  font-weight: 650;
}
.crop-lookup-status {
  margin-top: 6px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.6;
}
.crop-lookup-manual,
.crop-lookup-actions,
.crop-lookup-candidates {
  margin-top: 12px;
}
.crop-lookup-actions,
.crop-lookup-candidates {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.crop-lookup-actions .button {
  min-height: 44px;
}
.crop-lookup-candidates text {
  border-radius: 8px;
  padding: 3px 9px;
  background: var(--subtle);
  color: var(--ink);
  font-size: 12px;
}
</style>
