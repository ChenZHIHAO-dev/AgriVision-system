<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from './AppIcon.vue'
import { themeChoice, setTheme, type ThemeChoice } from '../lib/theme'
const modes: ThemeChoice[] = ['light', 'dark', 'system']
const labels = { light: '浅色', dark: '深色', system: '跟随系统' }
const icons = { light: 'sun', dark: 'moon', system: 'system' }
const next = computed(() => modes[(modes.indexOf(themeChoice.value) + 1) % modes.length])
</script>
<template>
  <button
    class="appearance-switch"
    :aria-label="'外观：' + labels[themeChoice] + '，切换为' + labels[next]"
    :title="'外观：' + labels[themeChoice]"
    @click="setTheme(next)"
  >
    <AppIcon :name="icons[themeChoice]" :size="19" />
    <text>{{ labels[themeChoice] }}</text>
  </button>
</template>
<style scoped>
.appearance-switch {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  min-height: 38px;
  padding: 8px 10px;
  border-radius: 11px;
  color: var(--muted);
  white-space: nowrap;
  font-size: 11px;
}
@media (max-width: 420px) {
  .appearance-switch {
    gap: 5px;
    padding: 8px 7px;
  }
}
</style>
