<script setup lang="ts">
import { ref } from 'vue'
import AppIcon from './AppIcon.vue'
import KnowledgeLibrary from './KnowledgeLibrary.vue'
import { imageUrl, type CaseRecord, type KnowledgeCard, type Source } from '../lib/api'
import { dateLabel, statusLabel } from '../lib/options'
defineProps<{ records: CaseRecord[]; loggedIn: boolean; cards: KnowledgeCard[] }>()
const emit = defineEmits<{
  capture: []
  open: [id: string]
  history: []
  login: []
  card: [value: KnowledgeCard]
  source: [value: Source]
}>()
const section = ref<'recent' | 'resources'>('recent')
</script>
<template>
  <view class="dashboard">
    <view class="dashboard-heading"
      ><text>工作台</text><text>拍照问诊、咨询记录与植保资料</text></view
    >
    <button class="dashboard-capture" @click="emit('capture')">
      <view class="dashboard-camera"><AppIcon name="camera" :size="29" /></view>
      <view><text>拍照问诊</text><text>选择作物，拍摄照片并查看初步结果</text></view>
      <AppIcon name="right" :size="19" />
    </button>
    <view class="dashboard-tabs" role="tablist" aria-label="首页栏目">
      <button
        role="tab"
        :aria-selected="section === 'recent'"
        :class="{ active: section === 'recent' }"
        @click="section = 'recent'"
      >
        <AppIcon name="history" :size="17" /><text>最近问诊</text>
      </button>
      <button
        role="tab"
        :aria-selected="section === 'resources'"
        :class="{ active: section === 'resources' }"
        @click="section = 'resources'"
      >
        <AppIcon name="book" :size="17" /><text>参考资料</text>
      </button>
    </view>
    <view
      v-show="section === 'recent'"
      class="dashboard-recent"
      role="tabpanel"
      aria-label="最近问诊"
    >
      <view class="dashboard-section-heading"
        ><text>{{ loggedIn ? '接着上次的问诊' : '问诊记录' }}</text
        ><button v-if="loggedIn && records.length" @click="emit('history')">
          全部记录 <AppIcon name="external" :size="14" /></button
      ></view>
      <template v-if="loggedIn && records.length">
        <button
          v-for="record in records.slice(0, 5)"
          :key="record.id"
          class="dashboard-record"
          @click="emit('open', record.id)"
        >
          <image v-if="record.images.length" :src="imageUrl(record)" mode="aspectFill" /><view
            v-else
            class="text-record-icon"
            ><AppIcon name="chat" :size="22"
          /></view>
          <view
            ><text>{{ record.title }}</text
            ><text>{{ record.crop_name }} · {{ dateLabel(record.updated_at) }}</text></view
          >
          <text class="record-state">{{ statusLabel(record.status) }}</text
          ><AppIcon name="right" :size="17" />
        </button>
      </template>
      <view v-else class="dashboard-empty"
        ><view class="empty-record-icon"><AppIcon name="history" :size="25" /></view
        ><text>{{ loggedIn ? '还没有问诊记录' : '登录后保存问诊记录' }}</text
        ><text>{{
          loggedIn
            ? '完成拍照或开始咨询后，可在这里继续查看。'
            : '访客可以使用拍照与咨询，当前内容不保存到历史。'
        }}</text
        ><button v-if="!loggedIn" class="button secondary" @click="emit('login')">
          登录
        </button></view
      >
    </view>
    <KnowledgeLibrary
      v-show="section === 'resources'"
      embedded
      :cards="cards"
      @open="emit('card', $event)"
      @source="emit('source', $event)"
    />
  </view>
</template>
<style scoped>
.dashboard {
  max-width: 860px;
  margin: 8px auto 20px;
}
.dashboard-heading {
  margin-bottom: 27px;
}
.dashboard-heading > text:first-child {
  display: block;
  font-size: 26px;
  font-weight: 650;
  letter-spacing: -0.5px;
}
.dashboard-heading > text:last-child {
  display: block;
  font-size: 13px;
  color: var(--muted);
  margin-top: 9px;
}
.dashboard-capture {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 25px;
  width: 100%;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 19px;
  text-align: left;
}
.dashboard-camera {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 62px;
  height: 62px;
  background: var(--accent-soft);
  border-radius: 18px;
}
.dashboard-capture > view:nth-child(2) {
  flex: 1;
  min-width: 0;
}
.dashboard-capture > view:nth-child(2) > text:first-child {
  display: block;
  font-size: 19px;
  font-weight: 600;
}
.dashboard-capture > view:nth-child(2) > text:last-child {
  display: block;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.8;
  margin-top: 7px;
}
.dashboard-capture > text {
  font-size: 20px;
  color: var(--muted);
}
.dashboard-recent {
  margin-top: 22px;
}
.dashboard-section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 15px;
  margin-bottom: 10px;
}
.dashboard-section-heading > text {
  font-size: 15px;
  font-weight: 600;
}
.dashboard-section-heading > button {
  font-size: 11px;
  color: var(--accent);
}
.dashboard-record {
  display: flex;
  align-items: center;
  gap: 15px;
  text-align: left;
  width: 100%;
  padding: 19px 0;
  border-bottom: 1px solid var(--line);
}
.dashboard-record > image,
.text-record-icon {
  width: 56px;
  height: 56px;
  min-width: 56px;
  border-radius: 12px;
  background: var(--subtle);
}
.text-record-icon {
  display: flex;
  align-items: center;
  justify-content: center;
}
.dashboard-record > view:nth-child(2) {
  flex: 1;
  min-width: 0;
}
.dashboard-record > view:nth-child(2) > text:first-child {
  display: block;
  font-size: 14px;
  font-weight: 550;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dashboard-record > view:nth-child(2) > text:last-child {
  display: block;
  font-size: 11px;
  color: var(--muted);
  margin-top: 7px;
}
.record-state {
  font-size: 10px;
  color: var(--muted);
  background: var(--subtle);
  padding: 4px 7px;
  border-radius: 6px;
}
.dashboard-record > text:last-child {
  color: var(--muted);
}
.dashboard-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  text-align: center;
  padding: 44px 20px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 17px;
  margin-top: 17px;
}
.empty-record-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 54px;
  height: 54px;
  background: var(--subtle);
  border-radius: 17px;
  margin-bottom: 4px;
}
.dashboard-empty > text:nth-child(2) {
  font-size: 14px;
  font-weight: 550;
}
.dashboard-empty > text:nth-child(3) {
  font-size: 12px;
  color: var(--muted);
  line-height: 1.9;
}
.dashboard-empty > .button {
  min-height: 39px;
  padding: 6px 20px;
  font-size: 12px;
  margin-top: 5px;
}
@media (max-width: 760px) {
  .dashboard-heading {
    margin-bottom: 23px;
  }
  .dashboard-heading > text:first-child {
    font-size: 24px;
  }
  .dashboard-heading > text:last-child {
    font-size: 12px;
  }
  .dashboard-capture {
    padding: 20px 17px;
    gap: 13px;
    border-radius: 17px;
  }
  .dashboard-camera {
    width: 49px;
    height: 49px;
    border-radius: 15px;
  }
  .dashboard-capture > view:nth-child(2) > text:first-child {
    font-size: 17px;
  }
  .dashboard-capture > view:nth-child(2) > text:last-child {
    font-size: 11px;
  }
  .dashboard-recent {
    margin-top: 20px;
  }
  .dashboard-record {
    gap: 12px;
    padding: 16px 0;
  }
  .dashboard-record > image,
  .text-record-icon {
    width: 48px;
    height: 48px;
    min-width: 48px;
    border-radius: 10px;
  }
  .dashboard-record > view:nth-child(2) > text:first-child {
    font-size: 13px;
  }
  .dashboard-record > view:nth-child(2) > text:last-child {
    font-size: 10px;
  }
  .record-state {
    display: none;
  }
  .dashboard-empty {
    padding: 32px 17px;
  }
  .dashboard-empty > text:nth-child(3) {
    font-size: 11px;
  }
}

.dashboard-tabs {
  display: flex;
  gap: 6px;
  border-bottom: 1px solid var(--line);
  margin: 28px 0 21px;
  padding-bottom: 9px;
}
.dashboard-tabs > button {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 42px;
  padding: 10px 15px;
  border-radius: 11px;
  color: var(--muted);
  font-size: 13px;
}
.dashboard-tabs > button.active {
  background: var(--subtle);
  color: var(--ink);
  font-weight: 550;
}
.dashboard-section-heading > button {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 7px 8px;
  border-radius: 8px;
}
.dashboard-record {
  padding-left: 10px;
  padding-right: 10px;
  border-radius: 12px;
}
.dashboard-capture,
.dashboard-empty {
  border-color: transparent;
  box-shadow: 0 2px 12px #00000003;
}
</style>
