<script setup lang="ts">
import { computed, ref } from 'vue'
import AppIcon from './AppIcon.vue'
import RecognitionSummary from './RecognitionSummary.vue'
import ContentReference from './ContentReference.vue'
import type { CaseRecord, RecognitionReceipt, Source } from '../lib/api'
import { imageUrl } from '../lib/api'
import { dateLabel, statusLabel } from '../lib/options'
const props = defineProps<{ record: CaseRecord; receipt?: RecognitionReceipt; busy: boolean }>()
const emit = defineEmits<{ photo: [id?: string]; source: [source: Source]; edit: []; retry: [] }>()
const details = ref(false)
const score = computed(() =>
  props.record.images.length === 1 &&
  props.record.status === 'identified' &&
  props.record.candidates.length
    ? props.record.candidates[0].score
    : null,
)
const retryable = computed(
  () =>
    props.receipt &&
    ['service_error', 'mixed_model_versions', 'model_unavailable'].includes(props.receipt.outcome),
)
</script>
<template>
  <view class="recognition-result">
    <view v-if="record.is_demo" class="sample-note">演示样例 · 不是对用户照片的识别</view>
    <view class="recognition-layout">
      <view class="result-photo-area"
        ><button class="result-image" aria-label="查看症状图片" @click="emit('photo')">
          <image :src="imageUrl(record)" mode="aspectFit" /></button
        ><view v-if="record.images.length > 1" class="photo-strip"
          ><button
            v-for="(image, index) in record.images"
            :key="image.id"
            :aria-label="'查看第' + (index + 1) + '张照片'"
            @click="emit('photo', image.id)"
          >
            <image :src="imageUrl(record, image.id)" mode="aspectFill" /><text>{{
              index + 1
            }}</text>
          </button></view
        ><view class="photo-metadata"
          ><text>{{ dateLabel(record.created_at) }}</text
          ><button @click="emit('edit')">补充种植信息 ↗</button></view
        ></view
      >
      <view class="result-copy">
        <view class="result-state"
          ><text>{{ statusLabel(record.status) }}</text
          ><text v-if="record.experimental">实验识别</text></view
        >
        <view class="diagnosis-heading"
          ><text class="diagnosis-name">{{ record.title }}</text
          ><view v-if="score !== null" class="diagnosis-score"
            ><text>{{ (score * 100).toFixed(1) }}<text>%</text></text
            ><text>模型匹配分数</text></view
          ></view
        >
        <text class="diagnosis-summary">{{ record.advice.summary }}</text>
        <ContentReference kind="recognition" />
        <text v-if="score !== null" class="score-explanation"
          >分数用于比较候选类别，不代表确诊概率。</text
        >
        <view class="brief-advice"
          ><text class="advice-title">建议</text
          ><view v-for="(action, index) in record.advice.actions.slice(0, 3)" :key="action"
            ><text>{{ index + 1 }}</text
            ><text>{{ action }}</text></view
          ></view
        >
        <view v-if="record.advice.products.length" class="matched-products"
          ><view v-for="product in record.advice.products" :key="product.id"
            ><text>{{ product.name }}</text
            ><text>{{ product.instructions }}</text
            ><button
              @click="emit('source', { title: product.name, url: product.label_url, date: '' })"
            >
              查看产品标签 ↗
            </button></view
          ></view
        >
        <button
          v-if="retryable"
          class="button quiet full-width result-retry"
          :disabled="busy"
          @click="emit('retry')"
        >
          重新识别现有照片
        </button>
        <RecognitionSummary
          v-if="receipt && (record.images.length > 1 || record.status !== 'identified' || details)"
          :result="receipt"
        />
        <button
          v-if="record.images.length === 1 && record.status === 'identified'"
          class="details-toggle"
          :aria-expanded="details"
          @click="details = !details"
        >
          {{ details ? '收起识别详情' : '查看识别详情' }}<text>{{ details ? '−' : '＋' }}</text>
        </button>
        <view v-if="record.advice.sources.length" class="brief-sources"
          ><text>参考资料</text
          ><button
            v-for="source in record.advice.sources"
            :key="source.url"
            @click="emit('source', source)"
          >
            {{ source.title }} ↗
          </button></view
        >
      </view></view
    >
  </view>
</template>
<style scoped>
.recognition-result {
  max-width: 1060px;
  margin: 0 auto;
  padding: 23px 28px 24px;
}
.sample-note {
  font-size: 12px;
  color: var(--muted);
  padding-bottom: 15px;
}
.recognition-layout {
  display: grid;
  grid-template-columns: minmax(240px, 0.8fr) minmax(0, 1.2fr);
  gap: 32px;
  align-items: start;
}
.result-image {
  display: block;
  width: 100%;
  height: 300px;
  background: var(--subtle);
  border: 1px solid var(--line);
  border-radius: 17px;
  overflow: hidden;
}
.result-image > image {
  width: 100%;
  height: 100%;
}
.photo-metadata {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 10px;
  color: var(--muted);
  padding: 13px 2px;
}
.photo-metadata > button {
  font-size: 11px;
  color: var(--accent);
}
.photo-strip {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  margin-top: 11px;
}
.photo-strip > button {
  position: relative;
  width: 55px;
  height: 55px;
  min-width: 55px;
  border: 1px solid var(--line);
  border-radius: 9px;
  overflow: hidden;
}
.photo-strip image {
  width: 100%;
  height: 100%;
}
.photo-strip text {
  position: absolute;
  bottom: 2px;
  right: 2px;
  background: #15171bb3;
  color: #fff;
  border-radius: 4px;
  padding: 0 4px;
  font-size: 9px;
}
.result-copy {
  min-width: 0;
}
.result-state {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}
.result-state > text {
  font-size: 10px;
  border-radius: 6px;
  padding: 4px 8px;
  background: var(--accent-soft);
  color: var(--accent);
}
.result-state > text:last-child:not(:first-child) {
  color: var(--muted);
  background: var(--subtle);
}
.diagnosis-heading {
  display: flex;
  gap: 15px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.diagnosis-name {
  display: block;
  font-size: 24px;
  font-weight: 650;
  line-height: 1.5;
  letter-spacing: -0.5px;
}
.diagnosis-score {
  text-align: right;
  flex-shrink: 0;
}
.diagnosis-score > text:first-child {
  display: block;
  font-size: 28px;
  font-weight: 600;
  line-height: 1.2;
  letter-spacing: -0.8px;
}
.diagnosis-score > text:first-child > text {
  font-size: 13px;
  letter-spacing: 0;
  margin-left: 1px;
}
.diagnosis-score > text:last-child {
  display: block;
  font-size: 9px;
  color: var(--muted);
  margin-top: 4px;
}
.diagnosis-summary {
  display: block;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.9;
}
.score-explanation {
  display: block;
  font-size: 10px;
  color: var(--muted);
  line-height: 1.8;
  margin-top: 7px;
}
.brief-advice {
  margin: 23px 0 16px;
}
.advice-title {
  font-size: 14px;
  font-weight: 600;
  display: block;
  margin-bottom: 14px;
}
.brief-advice > view {
  display: flex;
  gap: 12px;
  font-size: 13px;
  line-height: 1.8;
  margin: 12px 0;
}
.brief-advice > view > text:first-child {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 23px;
  min-width: 23px;
  height: 25px;
  border-radius: 7px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 11px;
}
.result-retry {
  margin-bottom: 12px;
}
.details-toggle {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  font-size: 11px;
  color: var(--muted);
  padding: 14px 0;
  border-top: 1px solid var(--line);
}
.brief-sources {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 17px 0 0;
  border-top: 1px solid var(--line);
  font-size: 11px;
  color: var(--muted);
}
.brief-sources > text {
  font-size: 11px;
  font-weight: 550;
}
.brief-sources > button {
  font-size: 10px;
  text-align: left;
  line-height: 1.9;
  color: var(--muted);
}
.matched-products > view {
  display: flex;
  flex-direction: column;
  gap: 8px;
  border: 1px solid var(--line);
  padding: 13px;
  border-radius: 12px;
  font-size: 12px;
  margin: 10px 0;
}
.matched-products > view > button {
  font-size: 11px;
  color: var(--accent);
  text-align: left;
}
@media (max-width: 760px) {
  .recognition-result {
    padding: 15px 16px 20px;
  }
  .recognition-layout {
    display: flex;
    flex-direction: column;
    gap: 11px;
  }
  .result-photo-area,
  .result-copy {
    width: 100%;
  }
  .result-image {
    height: 178px;
    border-radius: 14px;
  }
  .photo-metadata {
    padding: 10px 1px;
    font-size: 9px;
  }
  .photo-metadata > button {
    font-size: 10px;
  }
  .result-state {
    margin-bottom: 10px;
  }
  .diagnosis-name {
    font-size: 22px;
  }
  .diagnosis-score > text:first-child {
    font-size: 25px;
  }
  .diagnosis-summary {
    font-size: 12px;
    line-height: 1.9;
  }
  .brief-advice {
    margin-top: 19px;
  }
  .brief-advice > view {
    font-size: 12px;
    margin: 12px 0;
  }
  .score-explanation {
    font-size: 9px;
  }
  .brief-sources > button {
    font-size: 10px;
  }
}
</style>
