<script setup lang="ts">
import AppIcon from './AppIcon.vue'
import ConversationHistory from './ConversationHistory.vue'
import type { CaseRecord } from '../lib/api'
import type { User } from '../lib/auth'

defineProps<{ records: CaseRecord[]; user: User | null; selected?: string; expanded: boolean }>()
const emit = defineEmits<{ open: [id: string]; new: []; login: []; toggle: [] }>()
</script>

<template>
  <view class="history-sidebar-panel" :class="{ expanded }">
    <view
      id="desktop-history-sidebar"
      class="history-sidebar-clip"
      :aria-hidden="!expanded"
      :inert="!expanded || undefined"
    >
      <view class="history-sidebar-body">
        <view class="sidebar-heading">
          <text>宛农植保助手</text>
          <text>照片和咨询，记录在一起</text>
        </view>
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
    </view>
    <button
      class="history-edge-toggle"
      :class="{ 'is-expanded': expanded }"
      :aria-label="expanded ? '收起历史侧栏' : '展开历史侧栏'"
      :title="expanded ? '收起历史侧栏' : '展开历史侧栏'"
      :aria-expanded="expanded"
      aria-controls="desktop-history-sidebar"
      @click="emit('toggle')"
    >
      <AppIcon :name="expanded ? 'collapse' : 'right'" :size="17" />
    </button>
  </view>
</template>

<style scoped>
.history-sidebar-panel {
  --history-width: 244px;
  position: relative;
  z-index: 50;
  width: 0;
  flex-shrink: 0;
  background: var(--surface);
  transition: width 0.2s ease;
}
.history-sidebar-panel.expanded {
  width: var(--history-width);
}
.history-sidebar-clip {
  height: 100%;
  width: 100%;
  overflow: hidden;
}
.history-sidebar-body {
  width: var(--history-width);
  height: 100%;
  border-right: 1px solid var(--line);
  display: flex;
  flex-direction: column;
  padding: 24px 13px 18px;
}
.sidebar-heading {
  padding-left: 9px;
}
.sidebar-heading > text:first-child {
  display: block;
  font-size: 14px;
  font-weight: 600;
}
.sidebar-heading > text:last-child {
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
.history-edge-toggle {
  position: absolute;
  top: 23px;
  right: -19px;
  width: 20px;
  height: 34px;
  display: grid;
  place-items: center;
  border: 1px solid var(--line);
  border-radius: 0 8px 8px 0;
  background: var(--surface);
}
.history-edge-toggle.is-expanded {
  right: 8px;
  width: 32px;
  border-color: transparent;
  border-radius: 8px;
  background: transparent;
}
.history-edge-toggle:not(.is-expanded):hover,
.history-edge-toggle:not(.is-expanded):focus-visible {
  background: var(--hover);
  border-color: var(--control-line);
}
@media (max-width: 1050px) {
  .history-sidebar-panel {
    --history-width: 216px;
  }
}
@media (max-width: 760px) {
  .history-sidebar-panel {
    display: none;
  }
}
@media (prefers-reduced-motion: reduce) {
  .history-sidebar-panel {
    transition: none;
  }
}
</style>
