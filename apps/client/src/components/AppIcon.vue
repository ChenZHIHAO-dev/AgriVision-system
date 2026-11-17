<script setup lang="ts">
import { asset } from '../lib/assets'
withDefaults(defineProps<{ name: string; size?: number; white?: boolean }>(), { size: 22, white: false })
</script>
<template><image :src="asset('icons/' + name + (white ? '-white' : '') + '.png')" :style="{ width: size + 'px', height: size + 'px' }" mode="aspectFit" class="app-icon" :class="{ 'icon-adaptive': !white }" aria-hidden="true" /></template>
<style scoped>.app-icon { flex-shrink: 0; display: inline-block; vertical-align: middle; }</style>
