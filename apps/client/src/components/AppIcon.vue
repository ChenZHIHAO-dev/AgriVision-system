<script setup lang="ts">
import { computed } from 'vue'
import { asset } from '../lib/assets'
import { resolvedTheme } from '../lib/theme'
const props = withDefaults(
  defineProps<{ name: string; size?: number; white?: boolean; tone?: 'default' | 'white' }>(),
  { size: 22, white: false, tone: 'default' },
)
const source = computed(() => {
  if (['wheat', 'maize', 'peanut'].includes(props.name))
    return asset('icons/' + props.name + '.png')
  const tone =
    props.tone === 'white'
      ? 'white'
      : props.white
        ? resolvedTheme.value === 'dark'
          ? 'inverse'
          : 'white'
        : resolvedTheme.value
  return asset('icons/ui/' + props.name + '-' + tone + '.png')
})
</script>
<template>
  <image
    :src="source"
    :style="{ width: size + 'px', height: size + 'px' }"
    mode="aspectFit"
    class="app-icon"
    aria-hidden="true"
    :draggable="false"
  />
</template>
<style scoped>
.app-icon {
  display: inline-block;
  flex-shrink: 0;
  vertical-align: middle;
}
</style>
