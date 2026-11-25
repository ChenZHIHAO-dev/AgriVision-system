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
const preview = ref(1)
const offset = ref(0)
const slotWidth = ref(0)
const glassStyle = computed(() => ({
  width: Math.max(0, slotWidth.value - 4) + 'px',
  transform:
    'translate3d(' +
    offset.value +
    'px,0,0) scale(' +
    (glassPhase.value === 'dragging' ? '1.035' : '1') +
    ')',
  background:
    resolvedTheme.value === 'dark' ? 'rgba(149, 149, 149, .26)' : 'rgba(255, 255, 255, .56)',
  borderColor:
    resolvedTheme.value === 'dark' ? 'rgba(223, 223, 223, .27)' : 'rgba(255, 255, 255, .82)',
}))
type Point = { x: number; y: number }
let bounds: DockBounds | null = null
let generation = 0
let inputActive = false
let holdTimer: ReturnType<typeof setTimeout> | undefined
let fadeTimer: ReturnType<typeof setTimeout> | undefined
let suppressUntil = 0
let latest: Point = { x: 0, y: 0 }
let usePointerEvents = false
let pointerId: number | null = null
let pointerTarget: HTMLElement | null = null
let dockSurface: HTMLElement | null = null

function measure(done?: (value: DockBounds) => void) {
  const accept = (rect: DockBounds | null) => {
    if (!rect || rect.width <= 0 || rect.height <= 0) {
      bounds = null
      return
    }
    const { left, top, width, height } = rect
    bounds = { left, top, width, height }
    done?.(bounds)
  }
  // #ifdef H5
  accept(dockSurface?.getBoundingClientRect() ?? null)
  // #endif
  // #ifndef H5
  uni
    .createSelectorQuery()
    .in(instance?.proxy)
    .select('.dock-tabs')
    .boundingClientRect((rect) => accept(rect as DockBounds | null))
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
function begin(index: number, point: Point) {
  if (props.keyboardOpen || inputActive) return false
  suppressUntil = 0
  clearTimeout(fadeTimer)
  glassPhase.value = 'idle'
  inputActive = true
  latest = point
  const beganAt = Date.now()
  const token = ++generation
  const ready = (rect: DockBounds) => {
    if (!inputActive || token !== generation) return
    if (!gesture.start(index, point.x, point.y, rect, beganAt)) return
    gesture.move(latest.x, latest.y, Date.now())
    syncGlass()
    if (gesture.phase === 'pressing')
      holdTimer = setTimeout(
        () => {
          gesture.activate(Date.now())
          syncGlass()
        },
        Math.max(0, DOCK_HOLD_MS - (Date.now() - beganAt)),
      )
  }
  // H5 can measure synchronously on each pointerdown. Native selectors cross the rendering bridge,
  // so reuse the measured surface when available and remeasure on window resize.
  if (!usePointerEvents && bounds) ready(bounds)
  else measure(ready)
  return true
}
function move(point: Point) {
  if (!inputActive) return
  latest = point
  gesture.move(point.x, point.y, Date.now())
  if (gesture.phase !== 'pressing') clearTimeout(holdTimer)
  syncGlass()
}
function settle(target: number) {
  offset.value = target * slotWidth.value
  glassPhase.value = 'settling'
  fadeTimer = setTimeout(() => {
    glassPhase.value = 'idle'
  }, 320)
}
function releaseInput() {
  generation++
  inputActive = false
  clearTimeout(holdTimer)
  // #ifdef H5
  const target = pointerTarget
  const id = pointerId
  pointerTarget = null
  pointerId = null
  if (id !== null && target?.hasPointerCapture?.(id)) target.releasePointerCapture(id)
  // #endif
}
function finish(point: Point) {
  if (!inputActive) return
  const result = gesture.finish(point.x, point.y, Date.now())
  releaseInput()
  if (result.suppressClick) suppressUntil = Date.now() + 650
  if (result.dragged && glassPhase.value === 'dragging') settle(result.target ?? selected.value)
  else glassPhase.value = 'idle'
  if (result.target !== null) emit('navigate', tabs[result.target].page)
}
function cancel() {
  if (gesture.cancel() || inputActive) suppressUntil = Date.now() + 650
  releaseInput()
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
  if (usePointerEvents) return
  if (event.touches?.length !== 1) {
    cancel()
    return
  }
  const { clientX, clientY } = event.touches[0]
  begin(index, { x: clientX, y: clientY })
}
function touchMove(event: TouchInput) {
  if (usePointerEvents || !inputActive) return
  if (event.touches?.length !== 1) {
    cancel()
    return
  }
  const { clientX, clientY } = event.touches[0]
  move({ x: clientX, y: clientY })
}
function touchEnd(event: TouchInput) {
  if (usePointerEvents) return
  const point = event.changedTouches?.[0]
  finish(point ? { x: point.clientX, y: point.clientY } : latest)
}
function touchCancel() {
  if (!usePointerEvents) cancel()
}
// #ifdef H5
function pointerStart(event: PointerEvent) {
  if (!event.isPrimary) {
    cancel()
    return
  }
  if (event.button !== 0) return
  const target = (event.target as Element).closest<HTMLElement>('.dock-tab')
  if (!target) return
  const index = Number(target.dataset.dockIndex)
  if (!Number.isInteger(index) || !tabs[index]) return
  if (!begin(index, { x: event.clientX, y: event.clientY })) return
  pointerId = event.pointerId
  pointerTarget = target
  if (event.pointerType === 'mouse') target.focus({ preventScroll: true })
  // Capture on the originating button so a short press keeps its ordinary click target.
  // The window listeners also handle browsers that fail to capture the pointer.
  try {
    target.setPointerCapture?.(event.pointerId)
  } catch {
    // The active pointer may already have left the viewport.
  }
}
function pointerMove(event: PointerEvent) {
  if (event.pointerId === pointerId) move({ x: event.clientX, y: event.clientY })
}
function pointerEnd(event: PointerEvent) {
  if (event.pointerId === pointerId) finish({ x: event.clientX, y: event.clientY })
}
function pointerCancel(event: PointerEvent) {
  if (event.pointerId === pointerId) cancel()
}
// #endif
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
    else measure()
  },
)
onMounted(() => {
  // #ifdef H5
  dockSurface = document.getElementById(id)
  usePointerEvents = typeof window.PointerEvent === 'function'
  dockSurface?.addEventListener('pointerdown', pointerStart)
  dockSurface?.addEventListener('lostpointercapture', pointerCancel)
  window.addEventListener('pointermove', pointerMove)
  window.addEventListener('pointerup', pointerEnd)
  window.addEventListener('pointercancel', pointerCancel)
  window.addEventListener('blur', cancel)
  document.addEventListener('mouseleave', cancel)
  window.addEventListener('resize', resized)
  // #endif
  // #ifndef H5
  uni.onWindowResize(resized)
  // #endif
  measure()
})
onUnmounted(() => {
  releaseInput()
  clearTimeout(fadeTimer)
  // #ifdef H5
  dockSurface?.removeEventListener('pointerdown', pointerStart)
  dockSurface?.removeEventListener('lostpointercapture', pointerCancel)
  window.removeEventListener('pointermove', pointerMove)
  window.removeEventListener('pointerup', pointerEnd)
  window.removeEventListener('pointercancel', pointerCancel)
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
    class="av-dock"
    :class="{ 'keyboard-hidden': keyboardOpen, 'is-dragging': glassPhase === 'dragging' }"
    :aria-hidden="keyboardOpen"
    :inert="keyboardOpen || undefined"
    role="navigation"
    aria-label="主页面导航"
  >
    <view :id="id" class="dock-tabs">
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
        :data-dock-index="index"
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
        @touchmove.stop="touchMove"
        @touchend="touchEnd"
        @touchcancel="touchCancel"
        @keydown="keyboard($event, index)"
        @contextmenu.prevent
      >
        <view class="dock-icon" :class="{ 'camera-core': tab.page === 'identify' }"
          ><AppIcon
            :name="tab.icon"
            :size="tab.page === 'identify' ? 24 : 22"
            :white="selected === index"
        /></view>
        <text>{{ tab.label }}</text>
      </button>
    </view>
  </view>
</template>
<style scoped>
.av-dock {
  position: relative;
  display: block;
  min-height: 74px;
  max-height: 112px;
  flex-shrink: 0;
  padding: 6px 12px calc(8px + var(--mobile-safe-bottom, env(safe-area-inset-bottom, 0px)));
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
.dock-tabs {
  position: relative;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  touch-action: none;
}
.dock-tabs > .dock-tab {
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
  touch-action: none;
  -webkit-touch-callout: none;
}
.dock-tabs > .dock-tab.active {
  color: var(--accent);
  font-weight: 650;
}
.dock-tabs > .dock-tab.drag-preview {
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
.dock-glass {
  position: absolute;
  top: -1px;
  left: 2px;
  height: calc(100% + 2px);
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
  will-change: transform;
}
.dock-glass.settling {
  opacity: 0;
  transition:
    opacity 0.28s ease,
    transform 0.22s ease;
}
.av-dock:not(.is-dragging) .dock-hover .dock-icon {
  transform: scale(0.94);
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
@media (prefers-reduced-motion: reduce) {
  .av-dock,
  .av-dock .dock-tab,
  .dock-icon,
  .dock-glass,
  .dock-glass.settling {
    transition: none;
  }
}
</style>
