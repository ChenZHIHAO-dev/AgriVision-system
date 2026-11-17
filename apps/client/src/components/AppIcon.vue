<script setup lang="ts">
withDefaults(defineProps<{ name: string; size?: number; white?: boolean }>(), { size: 22, white: false })
</script>
<template><image :src="'/static/icons/' + name + (white ? '-white' : '') + '.png'" :style="{ width: size + 'px', height: size + 'px' }" mode="aspectFit" class="app-icon" aria-hidden="true" /></template>
<style scoped>.app-icon { flex-shrink: 0; display: inline-block; vertical-align: middle; }</style>
