<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from './AppIcon.vue'
import { resolvedTheme, setTheme } from '../lib/theme'
const labels = { light: '浅色', dark: '深色' }
const icons = { light: 'sun', dark: 'moon' }
const next = computed(() => (resolvedTheme.value === 'dark' ? 'light' : 'dark'))
</script>
<template>
  <button
    class="appearance-switch"
    :aria-label="'外观：' + labels[resolvedTheme] + '，切换为' + labels[next]"
    :title="'外观：' + labels[resolvedTheme]"
    @click="setTheme(next)"
  >
    <AppIcon :name="icons[resolvedTheme]" :size="19" />
    <text>{{ labels[resolvedTheme] }}</text>
  </button>
</template>
<style scoped>
.appearance-switch {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  min-height: 44px;
  flex-shrink: 0;
  padding: 8px 10px;
  border-radius: 11px;
  color: var(--ink);
  white-space: nowrap;
  font-size: 12px;
}
.appearance-switch:hover {
  background: var(--hover);
}
.appearance-switch:active {
  background: var(--pressed);
}
@media (max-width: 420px) {
  .appearance-switch {
    gap: 5px;
    padding: 8px 7px;
  }
}
</style>
