<script setup lang="ts">
import AppIcon from './AppIcon.vue'
const props = defineProps<{ modelValue: string; options: string[]; label: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
function pick(event: { detail: { value: string | number } }) { emit('update:modelValue', props.options[Number(event.detail.value)]) }
</script>
<template>
  <view class="select-wrapper">
    <!-- #ifdef H5 -->
    <select class="native-select" :aria-label="label" :value="modelValue" @change="emit('update:modelValue', ($event.target as HTMLSelectElement).value)"><option v-for="option in options" :key="option" :value="option">{{ option }}</option></select><AppIcon name="chevron" :size="15" class="select-chevron" />
    <!-- #endif -->
    <!-- #ifndef H5 -->
    <picker :range="options" :value="Math.max(0, options.indexOf(modelValue))" @change="pick"><view class="select-native"><text>{{ modelValue }}</text><AppIcon name="chevron" :size="15" /></view></picker>
    <!-- #endif -->
  </view>
</template>
