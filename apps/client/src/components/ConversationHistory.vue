<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from './AppIcon.vue'
import type { CaseRecord } from '../lib/api'
import type { User } from '../lib/auth'
import { dateLabel } from '../lib/options'
import { conversationTitle } from '../lib/conversationTitle'

const props = defineProps<{
  records: CaseRecord[]
  user: User | null
  selected?: string
  query?: string
  drawer?: boolean
}>()
const emit = defineEmits<{ open: [id: string]; new: []; login: [] }>()

const keyword = computed(() => props.query?.trim().toLowerCase() || '')
const conversations = computed(() => {
  if (!props.user) return []
  const term = keyword.value
  if (!term) return props.records
  return props.records.filter((record) => {
    const fields = [
      conversationTitle(record),
      record.title,
      record.crop_name,
      record.location,
      record.note,
    ]
    const includes = (text: string) => text.toLowerCase().includes(term)
    return fields.some(includes) || record.messages.some((message) => includes(message.text))
  })
})
</script>

<template>
  <view class="conversation-history" :class="{ 'in-drawer': drawer }">
    <view class="history-caption"><text>历史问诊</text></view>
    <button v-if="!drawer" class="history-new" @click="emit('new')">
      <AppIcon name="new" :size="18" /><text>新建咨询</text>
    </button>
    <view v-if="!user" class="history-guest">
      <text>登录后，保存后续咨询，随时接着聊。</text>
      <button v-if="!drawer" @click="emit('login')">登录查看咨询记录 ↗</button>
    </view>
    <view v-else-if="!conversations.length" class="history-guest" aria-live="polite">
      {{ keyword ? '没有找到匹配的问诊记录。' : '还没有问诊记录。' }}
    </view>
    <scroll-view v-else scroll-y class="history-conversations">
      <button
        v-for="record in conversations"
        :key="record.id"
        class="conversation-entry"
        :class="{ selected: selected === record.id }"
        :aria-current="selected === record.id ? 'true' : undefined"
        @click="emit('open', record.id)"
      >
        <text>{{ conversationTitle(record) }}</text>
        <text>{{ record.crop_name }} · {{ dateLabel(record.updated_at) }}</text>
      </button>
    </scroll-view>
  </view>
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
.history-new {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 44px;
  font-size: 12px;
  text-align: left;
  border-radius: 11px;
  padding: 10px 12px;
  margin: 0 2px 12px;
  color: var(--ink);
  background: var(--subtle);
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
.conversation-history.in-drawer {
  margin-top: 10px;
}
.in-drawer .history-caption {
  padding-left: 10px;
  font-size: 12px;
}
.in-drawer .history-guest {
  font-size: 12px;
}
.in-drawer .history-conversations {
  height: 0;
  max-height: none;
}
.in-drawer .conversation-entry {
  min-height: 44px;
}
.in-drawer .conversation-entry > text:first-child {
  font-size: 13px;
}
.in-drawer .conversation-entry > text:last-child {
  font-size: 11px;
}
</style>
