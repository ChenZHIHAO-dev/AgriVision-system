<script setup lang="ts">
import AppIcon from './AppIcon.vue'
import ConversationHistory from './ConversationHistory.vue'
import type { CaseRecord } from '../lib/api'
import type { User } from '../lib/auth'
defineProps<{ records: CaseRecord[]; user: User | null; selected?: string }>()
const emit = defineEmits<{ open: [id: string]; new: []; login: []; close: [] }>()
</script>
<template>
  <view class="history-sidebar-panel">
    <view class="sidebar-heading"
      ><view><text>宛农植保助手</text><text>照片和咨询，记录在一起</text></view
      ><button class="icon-button" aria-label="收起历史侧栏" @click="emit('close')">
        <AppIcon name="collapse" :size="20" /></button
    ></view>
    <ConversationHistory
      :records="records"
      :user="user"
      :selected="selected"
      @open="emit('open', $event)"
      @new="emit('new')"
      @login="emit('login')"
    />
    <text class="sidebar-note">AgriVision · 田间工作台</text>
  </view>
</template>
<style scoped>
.history-sidebar-panel {
  width: 244px;
  flex-shrink: 0;
  background: var(--surface);
  border-right: 1px solid var(--line);
  display: flex;
  flex-direction: column;
  padding: 24px 13px 18px;
}
.sidebar-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  padding-left: 9px;
}
.sidebar-heading > view > text:first-child {
  display: block;
  font-size: 14px;
  font-weight: 600;
}
.sidebar-heading > view > text:last-child {
  display: block;
  font-size: 10px;
  color: var(--muted);
  margin-top: 5px;
}
.sidebar-note {
  display: block;
  color: var(--muted);
  font-size: 10px;
  padding: 15px 10px 0;
}
@media (max-width: 1050px) {
  .history-sidebar-panel {
    width: 216px;
  }
}
@media (max-width: 760px) {
  .history-sidebar-panel {
    display: none;
  }
}
</style>
