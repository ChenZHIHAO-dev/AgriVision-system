<script setup lang="ts">
import ChoicePicker from './ChoicePicker.vue'
defineProps<{ modelValue: string; options: string[]; label: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
</script>
<template>
  <ChoicePicker
    :model-value="modelValue"
    :options="options.map((value) => ({ value, label: value }))"
    :label="label"
    caption="选择一项，继续填写种植信息"
    @update:model-value="emit('update:modelValue', $event)"
  />
</template>
