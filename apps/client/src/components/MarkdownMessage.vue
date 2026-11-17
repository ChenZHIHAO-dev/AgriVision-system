<script setup lang="ts">
import { computed } from 'vue'
import { renderMarkdown } from '../lib/markdown'
const props = defineProps<{ content: string }>()
const html = computed(() => renderMarkdown(props.content))
</script>
<template>
  <view class="markdown-message">
    <!-- #ifdef H5 -->
    <div class="markdown-body" v-html="html" />
    <!-- #endif -->
    <!-- #ifndef H5 -->
    <rich-text class="markdown-body" :nodes="html" :selectable="true" />
    <!-- #endif -->
  </view>
</template>
<style scoped>
.markdown-message {
  font-size: 14px;
  line-height: 1.95;
  color: var(--ink);
  min-width: 0;
  max-width: 100%;
  overflow-wrap: anywhere;
  user-select: text;
  white-space: normal;
}
.markdown-message :deep(.md-p) {
  margin: 0 0 13px;
}
.markdown-message :deep(.md-p:last-child) {
  margin-bottom: 0;
}
.markdown-message :deep(.md-h1),
.markdown-message :deep(.md-h2),
.markdown-message :deep(.md-h3),
.markdown-message :deep(.md-h4) {
  font-size: 16px;
  line-height: 1.7;
  margin: 21px 0 10px;
  font-weight: 650;
  color: var(--ink);
}
.markdown-message :deep(.md-h1:first-child),
.markdown-message :deep(.md-h2:first-child),
.markdown-message :deep(.md-h3:first-child) {
  margin-top: 0;
}
.markdown-message :deep(.md-ul),
.markdown-message :deep(.md-ol) {
  padding-left: 23px;
  margin: 8px 0 15px;
}
.markdown-message :deep(.md-li) {
  margin: 5px 0;
  padding-left: 2px;
}
.markdown-message :deep(.md-li .md-p) {
  margin: 3px 0;
}
.markdown-message :deep(.md-strong) {
  font-weight: 650;
}
.markdown-message :deep(.md-a) {
  color: var(--accent);
  text-decoration: underline;
  text-underline-offset: 3px;
}
.markdown-message :deep(.md-blockquote) {
  margin: 14px 0;
  padding: 9px 14px;
  border-left: 3px solid var(--line);
  background: var(--subtle);
  border-radius: 0 9px 9px 0;
  color: var(--muted);
}
.markdown-message :deep(.md-code) {
  font-family: Consolas, Menlo, monospace;
  font-size: 0.9em;
  background: var(--subtle);
  padding: 2px 5px;
  border-radius: 5px;
}
.markdown-message :deep(.md-pre) {
  background: var(--subtle);
  border: 1px solid var(--line);
  border-radius: 11px;
  margin: 14px 0;
  padding: 13px 15px;
  max-width: 100%;
  overflow-x: auto;
  white-space: pre;
  font-size: 12px;
  line-height: 1.8;
}
.markdown-message :deep(.md-pre .md-code) {
  padding: 0;
  background: transparent;
  white-space: pre;
}
.markdown-message :deep(.md-table-wrap) {
  max-width: 100%;
  overflow-x: auto;
  margin: 13px 0;
}
.markdown-message :deep(.md-table) {
  border-collapse: collapse;
  font-size: 12px;
  min-width: 280px;
}
.markdown-message :deep(.md-th),
.markdown-message :deep(.md-td) {
  border: 1px solid var(--line);
  padding: 8px 11px;
  text-align: left;
  white-space: normal;
  min-width: 90px;
}
.markdown-message :deep(.md-th) {
  background: var(--subtle);
  font-weight: 600;
}
.markdown-message :deep(.md-hr) {
  border: 0;
  border-top: 1px solid var(--line);
  margin: 18px 0;
}
.markdown-message :deep(.md-image-note) {
  color: var(--muted);
  font-size: 12px;
}
@media (max-width: 760px) {
  .markdown-message {
    font-size: 14px;
  }
  .markdown-message :deep(.md-h1),
  .markdown-message :deep(.md-h2),
  .markdown-message :deep(.md-h3) {
    font-size: 15px;
  }
}
</style>
