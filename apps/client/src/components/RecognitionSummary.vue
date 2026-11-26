<script setup lang="ts">
import { ref } from 'vue'
import AppIcon from './AppIcon.vue'
import ContentReference from './ContentReference.vue'
import type { RecognitionReceipt } from '../lib/api'
defineProps<{ result: RecognitionReceipt; compact?: boolean }>()
const expanded = ref(false)
function state(status: string) {
  return (
    (
      {
        identified: '初步结果',
        uncertain: '未判明',
        needs_retake: '需补拍',
        needs_model: '模型未就绪',
        model_error: '需重试',
        pending: '待处理',
      } as Record<string, string>
    )[status] || '待核对'
  )
}
</script>
<template>
  <view class="recognition-receipt" :class="{ compact }">
    <view class="receipt-heading"
      ><AppIcon name="image" :size="17" /><text class="strong">图片识别结果</text
      ><text class="receipt-count">{{ result.image_count }} 张照片</text></view
    >
    <text class="receipt-summary">{{ result.summary }}</text>
    <ContentReference kind="recognition" />
    <view v-if="result.image_results?.length" class="receipt-images"
      ><view v-for="image in result.image_results" :key="image.image_id" class="receipt-image-row"
        ><text class="receipt-number">图 {{ image.image_index }}</text
        ><view class="receipt-image-info"
          ><text>{{ image.title }}</text
          ><text v-if="image.quality_issues?.length" class="receipt-issue">{{
            image.quality_issues.join('；')
          }}</text></view
        ><text class="receipt-state">{{ state(image.status) }}</text></view
      ></view
    >
    <button
      v-if="result.image_results?.some((image) => image.candidates.length)"
      class="receipt-details"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      {{ expanded ? '收起' : '查看' }}逐张模型候选分数 <text>{{ expanded ? '−' : '＋' }}</text>
    </button>
    <view v-if="expanded" class="receipt-scores"
      ><view
        v-for="image in result.image_results?.filter((item) => item.candidates.length)"
        :key="image.image_id"
        ><text class="receipt-score-heading"
          >图 {{ image.image_index }} · {{ image.model_version || '版本未记录' }}</text
        ><view v-for="candidate in image.candidates" :key="candidate.id" class="receipt-score-row"
          ><text>{{ candidate.name }}</text
          ><text>{{ (candidate.score * 100).toFixed(1) }}%</text></view
        ></view
      ><text class="receipt-score-note"
        >分数只用于该张图片的候选比较，不做跨图平均，也不代表确诊概率。</text
      ></view
    >
  </view>
</template>
<style scoped>
.recognition-receipt {
  border: 1px solid var(--line);
  background: var(--surface);
  border-radius: 15px;
  padding: 17px 18px;
  margin: 0 0 20px;
  color: var(--ink);
  min-width: 0;
}
.receipt-heading {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  margin-bottom: 10px;
}
.receipt-symbol {
  font-size: 17px;
  color: var(--muted);
}
.receipt-count {
  margin-left: auto;
  color: var(--muted);
  font-size: 10px;
}
.receipt-summary {
  display: block;
  font-size: 12px;
  line-height: 1.9;
  overflow-wrap: anywhere;
}
.receipt-images {
  margin-top: 12px;
  border-top: 1px solid var(--line);
}
.receipt-image-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 11px 0;
  border-bottom: 1px solid var(--line);
  font-size: 11px;
}
.receipt-image-row:last-child {
  border-bottom: 0;
}
.receipt-number {
  color: var(--muted);
  min-width: 28px;
}
.receipt-image-info {
  flex: 1;
  min-width: 0;
  line-height: 1.8;
}
.receipt-image-info > text {
  display: block;
}
.receipt-issue {
  font-size: 10px;
  color: var(--muted);
  margin-top: 3px;
}
.receipt-state {
  font-size: 9px;
  background: var(--subtle);
  color: var(--muted);
  border-radius: 6px;
  padding: 2px 5px;
  white-space: nowrap;
}
.receipt-details {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  text-align: left;
  color: var(--muted);
  font-size: 10px;
  min-height: 30px;
  margin-top: 5px;
}
.receipt-details > text {
  font-size: 16px;
}
.receipt-scores {
  border-top: 1px solid var(--line);
  margin-top: 7px;
  padding-top: 11px;
}
.receipt-score-heading {
  font-size: 10px;
  color: var(--muted);
  display: block;
  margin: 9px 0 5px;
}
.receipt-score-row {
  font-size: 11px;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  line-height: 1.9;
}
.receipt-score-note {
  display: block;
  font-size: 9px;
  color: var(--muted);
  margin-top: 12px;
  line-height: 1.8;
}
.compact {
  padding: 14px 16px;
  margin-bottom: 15px;
}
@media (max-width: 760px) {
  .recognition-receipt {
    padding: 14px;
    border-radius: 13px;
  }
  .receipt-summary {
    font-size: 12px;
  }
  .receipt-image-row {
    gap: 7px;
  }
}
</style>
