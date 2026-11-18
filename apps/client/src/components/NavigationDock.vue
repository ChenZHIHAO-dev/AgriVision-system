<script setup lang="ts">
import { computed, getCurrentInstance, onMounted, onUnmounted, ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'
import { resolvedTheme } from '../lib/theme'
import { DockGesture, DOCK_HOLD_MS, type DockBounds } from '../lib/dockGesture'

const props = defineProps<{ active: string; keyboardOpen?: boolean }>()
const emit = defineEmits<{ navigate: [value: 'home' | 'identify' | 'profile'] }>()
const tabs = [
  { page: 'home' as const, icon: 'home', label: '首页', accessible: '首页' },
  { page: 'identify' as const, icon: 'camera', label: '拍照', accessible: '拍照识别' },
  { page: 'profile' as const, icon: 'user', label: '我的', accessible: '我的' },
]
const selected = computed(() =>
  props.active === 'home' || props.active === 'history' || props.active === 'knowledge'
    ? 0
    : props.active === 'profile' || props.active === 'settings'
      ? 2
      : 1,
)
const id = 'dock-' + Math.random().toString(36).slice(2, 9)
const instance = getCurrentInstance()
const gesture = new DockGesture()
const glassPhase = ref<'idle' | 'dragging' | 'settling'>('idle')
const preview = ref(1),
  offset = ref(0),
  slotWidth = ref(0)
const glassStyle = computed(() => ({
  width: Math.max(0, slotWidth.value - 4) + 'px',
  left: 14 + offset.value + 'px',
  background:
    resolvedTheme.value === 'dark' ? 'rgba(129, 145, 169, .26)' : 'rgba(255, 255, 255, .56)',
  borderColor:
    resolvedTheme.value === 'dark' ? 'rgba(206, 221, 242, .27)' : 'rgba(255, 255, 255, .82)',
}))
let bounds: DockBounds | null = null
let generation = 0
let inputActive = false,
  source: 'touch' | 'mouse' | null = null
let holdTimer: ReturnType<typeof setTimeout> | undefined
let fadeTimer: ReturnType<typeof setTimeout> | undefined
let suppressUntil = 0,
  lastTouch = 0
let latest = { x: 0, y: 0 }

function measure(done?: (value: DockBounds) => void) {
  // #ifdef H5
  const rect = document.getElementById(id)?.getBoundingClientRect()
  if (rect && rect.width > 24) {
    bounds = { left: rect.left + 12, top: rect.top + 6, width: rect.width - 24, height: 54 }
    done?.(bounds)
  }
  return
  // #endif
  // #ifndef H5
  uni
    .createSelectorQuery()
    .in(instance?.proxy)
    .select('.av-dock')
    .boundingClientRect((raw) => {
      const rect = raw as { left: number; top: number; width: number }
      if (!rect || rect.width <= 24) return
      bounds = { left: rect.left + 12, top: rect.top + 6, width: rect.width - 24, height: 54 }
      done?.(bounds)
    })
    .exec()
  // #endif
}
function syncGlass() {
  if (gesture.phase !== 'dragging') return
  glassPhase.value = 'dragging'
  preview.value = gesture.preview
  offset.value = gesture.offset
  slotWidth.value = gesture.slotWidth
}
function begin(index: number, point: { x: number; y: number }, kind: 'touch' | 'mouse') {
  if (props.keyboardOpen || inputActive) return
  suppressUntil = 0
  clearTimeout(fadeTimer)
  glassPhase.value = 'idle'
  inputActive = true
  source = kind
  latest = point
  const beganAt = Date.now()
  const token = ++generation
  const ready = (rect: DockBounds) => {
    if (!inputActive || source !== kind || token !== generation) return
    if (!gesture.start(index, point.x, point.y, rect, beganAt)) return
    gesture.move(latest.x, latest.y, Date.now())
    holdTimer = setTimeout(
      () => {
        gesture.activate(Date.now())
        syncGlass()
      },
      Math.max(0, DOCK_HOLD_MS - (Date.now() - beganAt)),
    )
  }
  // H5 measures synchronously. Mini-programs remeasure the component through their native selector API.
  measure(ready)
}
function move(point: { x: number; y: number }) {
  if (!inputActive) return
  latest = point
  gesture.move(point.x, point.y, Date.now())
  if (gesture.phase === 'cancelled') clearTimeout(holdTimer)
  syncGlass()
}
function settle(target: number) {
  clearTimeout(holdTimer)
  offset.value = target * slotWidth.value
  glassPhase.value = 'settling'
  fadeTimer = setTimeout(() => {
    glassPhase.value = 'idle'
  }, 460)
}
function finish(point: { x: number; y: number }) {
  if (!inputActive) return
  clearTimeout(holdTimer)
  const result = gesture.finish(point.x, point.y, Date.now())
  generation++
  inputActive = false
  source = null
  if (result.suppressClick) suppressUntil = Date.now() + 650
  if (result.dragged) settle(result.target ?? selected.value)
  else glassPhase.value = 'idle'
  if (result.target !== null) emit('navigate', tabs[result.target].page)
}
function cancel() {
  generation++
  clearTimeout(holdTimer)
  if (gesture.cancel() || inputActive) suppressUntil = Date.now() + 650
  inputActive = false
  source = null
  if (glassPhase.value === 'dragging') settle(selected.value)
}
function select(index: number) {
  if (props.keyboardOpen || Date.now() < suppressUntil) return
  emit('navigate', tabs[index].page)
}
type TouchInput = {
  touches?: ArrayLike<{ clientX: number; clientY: number }>
  changedTouches?: ArrayLike<{ clientX: number; clientY: number }>
}
function touchStart(event: TouchInput, index: number) {
  lastTouch = Date.now()
  if (event.touches?.length !== 1) {
    cancel()
    return
  }
  const touch = event.touches[0]
  begin(index, { x: touch.clientX, y: touch.clientY }, 'touch')
}
function touchMove(event: TouchInput) {
  if (source !== 'touch') return
  if (event.touches?.length !== 1) {
    cancel()
    return
  }
  move({ x: event.touches[0].clientX, y: event.touches[0].clientY })
}
function touchEnd(event: TouchInput) {
  lastTouch = Date.now()
  if (source !== 'touch') return
  const point = event.changedTouches?.[0]
  finish(point ? { x: point.clientX, y: point.clientY } : latest)
}
function mouseStart(event: MouseEvent, index: number) {
  // #ifdef H5
  if (event.button !== 0 || Date.now() - lastTouch < 800) return
  event.preventDefault()
  document.getElementById(id + '-' + index)?.focus()
  begin(index, { x: event.clientX, y: event.clientY }, 'mouse')
  // #endif
}
function mouseMove(event: MouseEvent) {
  if (source === 'mouse') move({ x: event.clientX, y: event.clientY })
}
function mouseEnd(event: MouseEvent) {
  if (source === 'mouse') finish({ x: event.clientX, y: event.clientY })
}
function keyboard(event: KeyboardEvent, index: number) {
  // #ifdef H5
  if (['Enter', ' '].includes(event.key)) {
    event.preventDefault()
    event.stopPropagation()
    cancel()
    if (!props.keyboardOpen) emit('navigate', tabs[index].page)
  } else if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
    event.preventDefault()
    event.stopPropagation()
    const target =
      event.key === 'Home'
        ? 0
        : event.key === 'End'
          ? 2
          : (index + (event.key === 'ArrowRight' ? 1 : 2)) % 3
    document.getElementById(id + '-' + target)?.focus()
  }
  // #endif
}
function resized() {
  cancel()
  measure()
}
watch(
  () => props.keyboardOpen,
  (hidden) => {
    if (hidden) cancel()
  },
)
onMounted(() => {
  measure()
  // #ifdef H5
  window.addEventListener('mousemove', mouseMove)
  window.addEventListener('mouseup', mouseEnd)
  window.addEventListener('blur', cancel)
  document.addEventListener('mouseleave', cancel)
  window.addEventListener('resize', resized)
  // #endif
  // #ifndef H5
  uni.onWindowResize(resized)
  // #endif
})
onUnmounted(() => {
  clearTimeout(holdTimer)
  clearTimeout(fadeTimer)
  // #ifdef H5
  window.removeEventListener('mousemove', mouseMove)
  window.removeEventListener('mouseup', mouseEnd)
  window.removeEventListener('blur', cancel)
  document.removeEventListener('mouseleave', cancel)
  window.removeEventListener('resize', resized)
  // #endif
  // #ifndef H5
  uni.offWindowResize(resized)
  // #endif
})
</script>
<template>
  <view
    :id="id"
    class="av-dock"
    :class="{
      'keyboard-hidden': keyboardOpen,
      'has-glass': glassPhase !== 'idle',
      'is-dragging': glassPhase === 'dragging',
    }"
    :aria-hidden="keyboardOpen"
    :inert="keyboardOpen || undefined"
    role="navigation"
    aria-label="主页面导航"
  >
    <view
      v-if="glassPhase !== 'idle'"
      class="dock-glass"
      :class="{ settling: glassPhase === 'settling' }"
      :style="glassStyle"
      aria-hidden="true"
    />
    <button
      v-for="(tab, index) in tabs"
      :id="id + '-' + index"
      :key="tab.page"
      class="dock-tab"
      :class="[
        {
          active: selected === index,
          'drag-preview': glassPhase === 'dragging' && preview === index,
        },
        'dock-' + tab.page,
      ]"
      :aria-label="tab.accessible"
      :aria-current="selected === index ? 'page' : undefined"
      hover-class="dock-hover"
      @click="select(index)"
      @touchstart="touchStart($event, index)"
      @touchmove.stop.prevent="touchMove"
      @touchend="touchEnd"
      @touchcancel="cancel"
      @mousedown="mouseStart($event, index)"
      @keydown="keyboard($event, index)"
      @contextmenu.prevent
    >
      <view class="dock-icon" :class="{ 'camera-core': tab.page === 'identify' }"
        ><AppIcon
          :name="tab.icon"
          :size="tab.page === 'identify' ? 24 : 22"
          :white="selected === index"
      /></view>
      <text>{{ tab.label }}</text
      ><view v-if="selected === index" class="dock-active-mark" aria-hidden="true" />
    </button>
  </view>
</template>
<style scoped>
.av-dock {
  display: none;
}
@media (max-width: 760px) {
  .av-dock {
    position: relative;
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    align-items: stretch;
    min-height: 74px;
    max-height: 112px;
    flex-shrink: 0;
    padding: 6px 12px calc(8px + env(safe-area-inset-bottom));
    background: var(--glass);
    border-top: 1px solid var(--line);
    backdrop-filter: blur(16px);
    z-index: 35;
    touch-action: none;
    user-select: none;
    -webkit-user-select: none;
    transition:
      opacity 0.18s ease,
      max-height 0.18s ease,
      min-height 0.18s ease,
      padding 0.18s ease,
      transform 0.18s ease;
  }
  .av-dock > .dock-tab {
    position: relative;
    display: grid;
    grid-template-rows: 36px 16px;
    justify-items: center;
    align-items: center;
    gap: 3px;
    min-height: 58px;
    width: 100%;
    min-width: 0;
    padding: 1px 0 3px;
    border-radius: 17px;
    color: var(--muted);
    background: transparent;
    font-size: 11px;
    font-weight: 500;
    z-index: 2;
    transition:
      background-color 0.22s ease,
      color 0.22s ease;
    -webkit-touch-callout: none;
  }
  .av-dock > .dock-tab.active {
    background: var(--accent-soft);
    color: var(--accent);
    font-weight: 650;
  }
  .av-dock.has-glass > .dock-tab.active {
    background: transparent;
  }
  .av-dock > .dock-tab.drag-preview {
    color: var(--ink);
    font-weight: 650;
  }
  .dock-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 35px;
    height: 35px;
    border-radius: 12px;
    transition:
      background-color 0.22s ease,
      transform 0.22s ease;
  }
  .camera-core {
    width: 38px;
    height: 36px;
    border-radius: 13px;
    background: var(--subtle);
  }
  .active > .dock-icon {
    background: var(--accent);
    box-shadow: 0 2px 7px #00000012;
  }
  .dock-active-mark {
    position: absolute;
    bottom: 0;
    width: 14px;
    height: 2px;
    border-radius: 2px;
    background: var(--accent);
    opacity: 0.8;
  }
  .dock-glass {
    position: absolute;
    top: 5px;
    height: 60px;
    border: 1.3px solid;
    border-radius: 19px;
    backdrop-filter: blur(14px) saturate(1.3);
    -webkit-backdrop-filter: blur(14px) saturate(1.3);
    box-shadow:
      0 6px 18px #00000016,
      inset 0 1px 0 #ffffff40;
    pointer-events: none;
    z-index: 1;
    opacity: 1;
    transform: scale(1.045);
    transition:
      opacity 0.42s ease,
      transform 0.25s ease;
    will-change: left;
  }
  .dock-glass.settling {
    opacity: 0;
    transform: scale(1);
    transition:
      left 0.24s ease,
      opacity 0.42s ease,
      transform 0.25s ease;
  }
  .av-dock .dock-hover {
    background: var(--hover);
  }
  .av-dock.keyboard-hidden {
    min-height: 0;
    max-height: 0;
    padding-top: 0;
    padding-bottom: 0;
    opacity: 0;
    transform: translateY(12px);
    border-width: 0;
    pointer-events: none;
  }
}
@media (prefers-reduced-motion: reduce) {
  .av-dock,
  .av-dock .dock-tab,
  .dock-icon,
  .dock-glass,
  .dock-glass.settling {
    transition: none;
  }
  .dock-glass {
    transform: none;
  }
}
</style>
