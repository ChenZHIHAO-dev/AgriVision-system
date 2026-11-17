<script setup lang="ts">
import { computed } from 'vue'
import type { CaseRecord } from '../lib/api'
import type { User } from '../lib/auth'
import { dateLabel } from '../lib/options'
const props = defineProps<{ records: CaseRecord[]; user: User | null; selected?: string }>()
const emit = defineEmits<{ open: [id: string]; new: []; login: [] }>()
const conversations = computed(() => props.records)
function title(record: CaseRecord) {
  return (
    record.messages
      .find(
        (item) =>
          item.role === 'user' &&
          item.provider !== 'photo' &&
          item.text.length > 4 &&
          !/^(这次咨询的作物|目前处于|请结合|照片已上传)/.test(item.text),
      )
      ?.text.slice(0, 23) || record.title
  )
}
</script>
<template>
  <view class="conversation-history"
    ><view class="history-caption"><text>历史问诊</text></view
    ><button class="history-new" @click="emit('new')">＋ 新建咨询</button
    ><view v-if="!user" class="history-guest"
      ><text>登录后，保存后续咨询，随时接着聊。</text
      ><button @click="emit('login')">登录查看咨询记录 ↗</button></view
    ><view v-else-if="!conversations.length" class="history-guest"
      >还没有问诊记录，登录后的问诊会显示在这里。</view
    ><scroll-view v-else scroll-y class="history-conversations"
      ><button
        v-for="record in conversations"
        :key="record.id"
        class="conversation-entry"
        :class="{ selected: selected === record.id }"
        @click="emit('open', record.id)"
      >
        <text>{{ title(record) }}</text
        ><text>{{ record.crop_name }} · {{ dateLabel(record.updated_at) }}</text>
      </button></scroll-view
    ></view
  >
</template>
<style scoped>
.conversation-history {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  margin-top: 24px;
}
.history-caption {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--muted);
  font-size: 11px;
  padding: 0 10px 10px;
}
.history-caption > button {
  font-size: 20px;
  width: 28px;
  height: 28px;
  border-radius: 8px;
}
.history-new {
  font-size: 12px;
  text-align: left;
  border: 1px solid var(--line);
  border-radius: 11px;
  padding: 10px 12px;
  background: var(--surface);
  margin: 0 2px 12px;
  color: var(--ink);
}
.history-guest {
  font-size: 11px;
  color: var(--muted);
  line-height: 1.9;
  padding: 10px;
}
.history-guest > text {
  display: block;
}
.history-guest > button {
  display: block;
  text-align: left;
  font-size: 11px;
  color: var(--accent);
  margin-top: 12px;
  min-height: 32px;
}
.history-conversations {
  min-height: 0;
  max-height: 55vh;
  flex: 1;
}
.conversation-entry {
  display: block;
  text-align: left;
  width: 100%;
  padding: 11px 10px;
  margin: 2px 0;
  border-radius: 10px;
  color: var(--ink);
}
.conversation-entry:hover,
.conversation-entry.selected {
  background: var(--subtle);
}
.conversation-entry > text:first-child {
  font-size: 12px;
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.conversation-entry > text:last-child {
  font-size: 9px;
  color: var(--muted);
  display: block;
  margin-top: 4px;
}
</style>
