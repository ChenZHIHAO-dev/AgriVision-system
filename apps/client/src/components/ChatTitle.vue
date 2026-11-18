<script setup lang="ts">
import AppIcon from './AppIcon.vue'

defineProps<{ title: string; expanded: boolean }>()
const emit = defineEmits<{ open: [] }>()
</script>
<template>
  <button
    class="chat-title-control"
    :aria-label="title + '，对话选项'"
    :aria-expanded="expanded"
    aria-haspopup="dialog"
    @click="emit('open')"
  >
    <text>{{ title }}</text>
    <AppIcon name="chevron" :size="14" />
  </button>
</template>
<style scoped>
.chat-title-control {
  display: flex;
  align-items: center;
  min-width: 0;
  max-width: 100%;
  min-height: 40px;
  gap: 6px;
  padding: 4px 9px;
  border-radius: 11px;
  color: var(--ink);
  text-align: left;
  font-size: 15px;
  font-weight: 650;
}
.chat-title-control > text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.chat-title-control:hover {
  background: var(--hover);
}
.chat-title-control:active,
.chat-title-control[aria-expanded='true'] {
  background: var(--pressed);
}
</style>
