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
  <!-- #ifdef H5 -->
  <img
    :key="source"
    :src="source"
    :width="size"
    :height="size"
    class="app-icon"
    alt=""
    aria-hidden="true"
    draggable="false"
  />
  <!-- #endif -->
  <!-- #ifndef H5 -->
  <!-- A keyed native node prevents the previous bitmap from surviving a theme change. -->
  <image
    v-for="url in [source]"
    :key="url"
    :src="url"
    :style="{ width: size + 'px', height: size + 'px' }"
    mode="aspectFit"
    class="app-icon"
    aria-hidden="true"
    :draggable="false"
  />
  <!-- #endif -->
</template>
<style scoped>
.app-icon {
  display: inline-block;
  flex-shrink: 0;
  vertical-align: middle;
  object-fit: contain;
}
</style>
