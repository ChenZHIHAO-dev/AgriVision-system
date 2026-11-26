<script setup lang="ts">
withDefaults(defineProps<{ kind?: 'ai' | 'recognition' | 'reference' }>(), { kind: 'ai' })
</script>
<template>
  <text class="content-reference" role="note">{{
    kind === 'ai'
      ? 'AI 生成内容，仅供参考，请结合实际情况判断。'
      : kind === 'recognition'
        ? '识别结果仅供参考，请结合实际情况判断。'
        : '资料与建议仅供参考，请结合实际情况判断。'
  }}</text>
</template>
<style scoped>
.content-reference {
  display: block;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.7;
  margin-top: 12px;
  overflow-wrap: anywhere;
}
</style>
