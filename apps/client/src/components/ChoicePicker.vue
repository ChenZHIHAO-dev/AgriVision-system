<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref } from 'vue'
import AppIcon from './AppIcon.vue'
const props = withDefaults(
  defineProps<{
    modelValue: string
    options: { value: string; label: string; description?: string; symbol?: string }[]
    label: string
    caption?: string
    footer?: string
    compact?: boolean
    above?: boolean
    disabled?: boolean
  }>(),
  { caption: '选择后立即生效', footer: '', compact: false, above: false, disabled: false },
)
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const open = ref(false),
  id = 'choice-' + Math.random().toString(36).slice(2, 9),
  panelStyle = ref<Record<string, string>>({}),
  paletteStyle = ref<Record<string, string>>({})
const selected = computed(
  () => props.options.find((item) => item.value === props.modelValue)?.label || props.modelValue,
)
function close() {
  open.value = false
  // #ifdef H5
  document.getElementById(id + '-trigger')?.focus()
  // #endif
}
async function show() {
  if (props.disabled) return
  if (open.value) {
    close()
    return
  }
  // #ifdef H5
  const trigger = document.getElementById(id + '-trigger')
  if (trigger) {
    const palette = getComputedStyle(trigger),
      style: Record<string, string> = {},
      colors: Record<string, string> = {}
    for (const name of [
      '--bg',
      '--surface',
      '--elevated',
      '--subtle',
      '--ink',
      '--muted',
      '--line',
      '--accent',
      '--accent-ink',
      '--accent-soft',
      '--focus',
      '--hover',
      '--pressed',
    ])
      colors[name] = palette.getPropertyValue(name)
    const viewport = window.visualViewport
    const height = viewport?.height || window.innerHeight,
      width = window.innerWidth
    if (width > 760) {
      const rect = trigger.getBoundingClientRect(),
        estimated = Math.min(430, 91 + props.options.length * 62 + (props.footer ? 48 : 0))
      const above =
        props.above || (height - rect.bottom < estimated && rect.top > height - rect.bottom)
      style.left = Math.max(12, Math.min(rect.left, width - 336)) + 'px'
      style.width = Math.min(324, width - 24) + 'px'
      style.top =
        (above
          ? Math.max(12, rect.top - estimated - 10)
          : Math.min(height - 100, rect.bottom + 10)) + 'px'
      style.maxHeight = Math.max(100, height - parseFloat(style.top) - 12) + 'px'
    }
    panelStyle.value = style
    paletteStyle.value = colors
  }
  // #endif
  open.value = true
  await nextTick()
  // #ifdef H5
  document.querySelector<HTMLElement>(`#${id} [aria-selected="true"]`)?.focus()
  // #endif
}
function select(value: string) {
  emit('update:modelValue', value)
  close()
}
function keyboard(event: KeyboardEvent) {
  if (event.defaultPrevented) return
  if (!open.value) return
  if (event.key === 'Escape') {
    event.preventDefault()
    close()
    return
  }
  // #ifdef H5
  const root = document.getElementById(id),
    options = Array.from(root?.querySelectorAll<HTMLElement>('[role="option"]') || [])
  if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
    event.preventDefault()
    const active = options.indexOf(document.activeElement as HTMLElement)
    const index =
      event.key === 'Home'
        ? 0
        : event.key === 'End'
          ? options.length - 1
          : (active + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length
    options[index]?.focus()
  }
  if (event.key === 'Tab') {
    const targets = Array.from(root?.querySelectorAll<HTMLElement>('[tabindex="0"]') || [])
    if (event.shiftKey && document.activeElement === targets[0]) {
      event.preventDefault()
      targets[targets.length - 1]?.focus()
    } else if (!event.shiftKey && document.activeElement === targets[targets.length - 1]) {
      event.preventDefault()
      targets[0]?.focus()
    }
  }
  // #endif
}
// #ifdef H5
document.addEventListener('keydown', keyboard)
onUnmounted(() => document.removeEventListener('keydown', keyboard))
// #endif
</script>
<template>
  <view class="choice-picker" :class="{ compact }">
    <button
      :id="id + '-trigger'"
      class="choice-trigger"
      :disabled="disabled"
      :aria-label="label"
      aria-haspopup="dialog"
      :aria-expanded="open"
      @click="show"
    >
      <text>{{ selected }}</text
      ><AppIcon name="chevron" :size="13" />
    </button>
    <!-- #ifdef H5 -->
    <Teleport to="body">
      <!-- #endif -->
      <view v-if="open" class="choice-layer" :style="paletteStyle" data-choice-layer>
        <view class="choice-dismiss" @click="close" />
        <view
          :id="id"
          class="choice-popup"
          :style="panelStyle"
          role="dialog"
          aria-modal="true"
          :aria-label="label"
          ><view class="choice-heading"
            ><view
              ><text class="choice-title">{{ label }}</text
              ><text class="choice-caption">{{ caption }}</text></view
            ><button class="choice-close" tabindex="0" :aria-label="'关闭' + label" @click="close">
              <AppIcon name="close" :size="18" /></button></view
          ><scroll-view scroll-y class="choice-options" role="listbox" :aria-label="label"
            ><button
              v-for="item in options"
              :key="item.value"
              class="choice-option"
              :class="{ selected: modelValue === item.value }"
              role="option"
              tabindex="0"
              :aria-selected="modelValue === item.value"
              @click="select(item.value)"
            >
              <text v-if="item.symbol" class="choice-symbol">{{ item.symbol }}</text
              ><view class="choice-copy"
                ><text class="choice-option-title">{{ item.label }}</text
                ><text v-if="item.description" class="choice-description">{{
                  item.description
                }}</text></view
              ><text class="choice-check">{{ modelValue === item.value ? '✓' : '' }}</text>
            </button></scroll-view
          ><view v-if="footer || $slots.footer" class="choice-footer"
            ><slot name="footer"
              ><text>{{ footer }}</text></slot
            ></view
          ></view
        >
      </view>
      <!-- #ifdef H5 -->
    </Teleport>
    <!-- #endif -->
  </view>
</template>
<style scoped>
.choice-picker {
  width: 100%;
  min-width: 0;
}
.choice-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 44px;
  width: 100%;
  padding: 10px 13px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--elevated);
  color: var(--ink);
  font-size: 13px;
  text-align: left;
}
.choice-trigger > text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.compact .choice-trigger {
  height: 35px;
  min-height: 35px;
  padding: 0 10px;
  font-size: 12px;
  background: var(--subtle);
  border-radius: 10px;
}
.choice-layer {
  position: fixed;
  inset: 0;
  top: var(--viewport-top, 0px);
  bottom: auto;
  height: var(--app-height, 100dvh);
  z-index: 1600;
  pointer-events: none;
  color: var(--ink);
  font-family:
    -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}
.choice-dismiss {
  position: absolute;
  inset: 0;
  pointer-events: auto;
}
.choice-popup {
  position: fixed;
  width: 324px;
  max-width: calc(100vw - 24px);
  display: flex;
  flex-direction: column;
  padding: 9px;
  background: var(--elevated);
  border: 1px solid var(--line);
  border-radius: 18px;
  box-shadow: 0 16px 50px #0003;
  pointer-events: auto;
  color: var(--ink);
  box-sizing: border-box;
  overflow: hidden;
}
.choice-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 8px 13px;
  gap: 16px;
  flex-shrink: 0;
}
.choice-title {
  display: block;
  font-size: 13px;
  font-weight: 650;
}
.choice-caption {
  display: block;
  color: var(--muted);
  font-size: 10px;
  margin-top: 4px;
}
.choice-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  font-size: 22px;
  border-radius: 8px;
  color: var(--muted);
  background: var(--subtle);
}
.choice-options {
  min-height: 0;
  max-height: 340px;
  flex: 1;
}
.choice-option {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 13px 10px;
  text-align: left;
  border: 1px solid transparent;
  border-radius: 12px;
  color: var(--ink);
  min-height: 47px;
  box-sizing: border-box;
}
.choice-option:hover,
.choice-option:focus-visible {
  background: var(--subtle);
}
.choice-option.selected {
  background: var(--accent-soft);
  border-color: var(--line);
}
.choice-symbol {
  width: 29px;
  height: 33px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--surface);
  border-radius: 9px;
  font-size: 18px;
}
.choice-copy {
  flex: 1;
  min-width: 0;
}
.choice-option-title {
  display: block;
  font-size: 13px;
  font-weight: 550;
}
.choice-description {
  display: block;
  font-size: 10px;
  color: var(--muted);
  margin-top: 4px;
}
.choice-check {
  width: 18px;
  font-size: 16px;
  color: var(--accent);
}
.choice-footer {
  color: var(--muted);
  font-size: 10px;
  line-height: 1.8;
  border-top: 1px solid var(--line);
  margin: 10px 8px 0;
  padding-top: 10px;
  padding-bottom: 5px;
  flex-shrink: 0;
}
@media (max-width: 760px) {
  .choice-popup {
    position: absolute;
  }
  .choice-dismiss {
    background: #0005;
  }
  .choice-popup {
    left: 12px;
    right: 12px;
    bottom: calc(12px + env(safe-area-inset-bottom));
    top: auto;
    width: auto;
    max-width: none;
    max-height: calc(var(--visual-height, var(--app-height, 100dvh)) - 24px);
    padding: 12px;
    border-radius: 22px;
  }
  .choice-options {
    max-height: 55vh;
  }
  .choice-option {
    min-height: 54px;
  }
  .choice-option-title {
    font-size: 14px;
  }
  .choice-description {
    font-size: 12px;
  }
  .choice-title {
    font-size: 15px;
  }
  .choice-caption,
  .choice-footer {
    font-size: 11px;
  }
  .choice-heading {
    padding: 7px 8px 16px;
  }
}
.choice-close {
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: var(--subtle);
}
.choice-layer .choice-option:hover,
.choice-layer .choice-close:hover {
  background: var(--hover);
}
.choice-layer .choice-option:active,
.choice-layer .choice-close:active,
.choice-layer .button-hover {
  background: var(--pressed) !important;
  color: var(--ink) !important;
}
</style>
