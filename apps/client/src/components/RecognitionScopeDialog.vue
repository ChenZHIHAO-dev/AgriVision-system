<script setup lang="ts">
import { computed } from 'vue'
import UiDialog from './UiDialog.vue'
import type { ModelScope } from '../lib/api'

const props = defineProps<{
  kind: 'disease' | 'crop'
  title: string
  model?: ModelScope
}>()
const emit = defineEmits<{ close: [] }>()
// 只读服务端实际模型标签；资料卡数量、作物选择目录都不能代替模型能力。
const labels = computed(() =>
  (props.model?.labels || []).map((id) => ({
    id,
    name: props.model?.label_names?.[id] || id,
  })),
)
const diseases = computed(() => labels.value.filter((label) => label.id !== 'healthy'))
const healthy = computed(() => labels.value.find((label) => label.id === 'healthy'))
</script>
<template>
  <UiDialog :title="title" @close="emit('close')">
    <view class="recognition-scope-content">
      <text v-if="!model?.ready" class="scope-description" role="status">
        {{
          kind === 'crop'
            ? '作物识别模型暂未接入或当前不可用，可手动选择作物。'
            : '该作物的症状识别模型暂未接入或当前不可用，可先记录情况或向 AI 提问。'
        }}
      </text>
      <text v-else-if="!labels.length" class="scope-description" role="status">
        当前服务尚未提供模型类别清单，暂时无法显示识别范围。
      </text>
      <template v-else>
        <text v-if="model.experimental" class="scope-description"
          >测试模型：下列范围来自当前已接入模型，田间效果仍需进一步验证。</text
        >
        <text class="scope-section-title">{{
          kind === 'crop' ? '可识别的作物' : '病虫害与症状标签'
        }}</text>
        <view class="scope-label-list" role="list">
          <view
            v-for="label in kind === 'crop' ? labels : diseases"
            :key="label.id"
            class="scope-label"
            role="listitem"
          >
            <text>{{ label.name }}</text>
          </view>
        </view>
        <template v-if="kind === 'disease' && healthy">
          <text class="scope-section-title">健康参考</text>
          <view class="scope-label"
            ><text>{{ healthy.name }}</text></view
          >
          <text class="scope-description"
            >健康标签仅是模型判断，不能排除尚未覆盖的病害或不明显的症状。</text
          >
        </template>
        <text class="scope-caution"
          >超出范围的照片也可能被误判为上述类别。识别结果仅供参考，请结合实际情况判断；不清晰时可换个角度补充近照。</text
        >
      </template>
    </view>
  </UiDialog>
</template>
<style scoped>
.recognition-scope-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-bottom: 4px;
}
.scope-section-title {
  display: block;
  color: var(--ink);
  font-size: 14px;
  font-weight: 600;
  margin-top: 4px;
}
.scope-description,
.scope-caution {
  display: block;
  font-size: 13px;
  line-height: 1.75;
  color: var(--muted);
  overflow-wrap: anywhere;
}
.scope-label-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.scope-label {
  padding: 12px 14px;
  background: var(--subtle);
  color: var(--ink);
  border: 1px solid var(--line);
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}
.scope-caution {
  padding-top: 12px;
  border-top: 1px solid var(--line);
}
</style>
