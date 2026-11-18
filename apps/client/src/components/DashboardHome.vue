<script setup lang="ts">
import { computed, getCurrentInstance, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'
import KnowledgeLibrary from './KnowledgeLibrary.vue'
import { imageUrl, type CaseRecord, type KnowledgeCard, type Source } from '../lib/api'
import { dateLabel, statusLabel } from '../lib/options'
import { conversationTitle } from '../lib/conversationTitle'
type DashboardSection = 'recent' | 'resources' | 'news'
const props = defineProps<{
  records: CaseRecord[]
  loggedIn: boolean
  cards: KnowledgeCard[]
  section: DashboardSection
  mobile?: boolean
}>()
const emit = defineEmits<{
  consult: []
  'update:section': [value: DashboardSection]
  capture: []
  open: [id: string]
  history: []
  login: []
  card: [value: KnowledgeCard]
  source: [value: Source]
}>()

const sections = [
  { id: 'recent', label: '最近问诊', icon: 'history' },
  { id: 'resources', label: '参考资料', icon: 'book' },
  { id: 'news', label: '农业资讯', icon: 'file' },
] as const

const shortcuts = [
  { id: 'capture', title: '拍照问诊', description: '拍摄或上传作物照片', icon: 'camera' },
  { id: 'consult', title: '文字咨询', description: '询问种植问题或了解药品作用', icon: 'chat' },
] as const
type Shortcut = (typeof shortcuts)[number]['id']
const orderKey = 'agrivision.dashboard.first-action'
const first = ref<Shortcut>(uni.getStorageSync(orderKey) === 'consult' ? 'consult' : 'capture')
const ordered = computed(() =>
  first.value === 'capture' ? shortcuts : [shortcuts[1], shortcuts[0]],
)
const arranging = ref(false)
let dragStart: { action: Shortcut; y: number } | undefined
const dragged = ref<Shortcut>()
const dragOffset = ref(0)

function swapActions() {
  first.value = first.value === 'capture' ? 'consult' : 'capture'
  uni.setStorageSync(orderKey, first.value)
}
function beginDrag(action: Shortcut, y: number) {
  dragStart = { action, y }
  dragged.value = action
}
function moveDrag(y: number) {
  if (!dragStart) return
  const delta = Math.min(48, Math.max(-48, y - dragStart.y))
  dragOffset.value = dragStart.action === first.value ? Math.max(0, delta) : Math.min(0, delta)
}
function finishDrag(cancel = false) {
  if (!cancel && Math.abs(dragOffset.value) >= 24) swapActions()
  dragStart = undefined
  dragged.value = undefined
  dragOffset.value = 0
}
type Touch = {
  touches: ArrayLike<{ clientY: number }>
  changedTouches: ArrayLike<{ clientY: number }>
}
function touchDown(action: Shortcut, event: Touch) {
  const touch = event.touches[0]
  if (touch) beginDrag(action, touch.clientY)
}
function touchMove(event: Touch) {
  const touch = event.touches[0]
  if (touch) moveDrag(touch.clientY)
}
function touchUp(event: Touch) {
  const touch = event.changedTouches[0]
  if (touch) moveDrag(touch.clientY)
  finishDrag()
}
function mouseDown(action: Shortcut, event: PointerEvent) {
  if (!event.isPrimary || event.button !== 0) return
  const handle = event.currentTarget as Element
  handle.setPointerCapture?.(event.pointerId)
  beginDrag(action, event.clientY)
}
function mouseMove(event: PointerEvent) {
  if (event.isPrimary) moveDrag(event.clientY)
}
function mouseUp(event: PointerEvent) {
  if (!event.isPrimary) return
  moveDrag(event.clientY)
  finishDrag()
}

const currentComponent = getCurrentInstance()?.proxy
const pageTop = ref(0)
const anchorTop = ref(0)
const viewHeight = ref(0)
const scrollTarget = ref(0)
const readOffset = computed(() =>
  viewHeight.value ? Math.max(0, pageTop.value - anchorTop.value) : 0,
)

async function measureSection() {
  if (!props.mobile || !currentComponent) return
  await nextTick()
  const query = uni.createSelectorQuery().in(currentComponent)
  query.select('.dashboard-scroll').boundingClientRect()
  query.select('.dashboard-section-anchor').boundingClientRect()
  query.exec(([viewport, anchor]) => {
    if (!viewport || !anchor || viewport.height <= 0) return
    anchorTop.value = Math.max(0, Math.round(anchor.top - viewport.top + pageTop.value))
    viewHeight.value = viewport.height
  })
}

function scrollDashboard(event: { detail: { scrollTop: number } }) {
  if (props.mobile) pageTop.value = Math.max(0, event.detail.scrollTop)
}

let scrollRequest = 0
function resetReading() {
  if (!props.mobile || !viewHeight.value || pageTop.value <= anchorTop.value) return
  // Reset only the content area. Cards above it remain on the same page.
  const request = ++scrollRequest
  scrollTarget.value = pageTop.value
  nextTick(() => {
    if (request === scrollRequest) scrollTarget.value = anchorTop.value
  })
}

function chooseSection(value: DashboardSection) {
  if (value === props.section) return
  resetReading()
  emit('update:section', value)
}
onMounted(() => {
  measureSection()
  uni.onWindowResize?.(measureSection)
})
onUnmounted(() => uni.offWindowResize?.(measureSection))
watch(() => props.mobile, measureSection)
watch(arranging, measureSection)
</script>
<template>
  <scroll-view
    class="dashboard-scroll"
    :class="{ 'dashboard-mobile-scroll': mobile }"
    :scroll-y="mobile"
    :scroll-top="mobile ? scrollTarget : undefined"
    @scroll="scrollDashboard"
  >
    <view
      class="dashboard"
      :style="mobile && viewHeight ? { '--dashboard-view-height': viewHeight + 'px' } : undefined"
    >
      <view class="dashboard-heading">
        <view>
          <text class="dashboard-title">工作台</text>
          <text class="dashboard-intro">快捷入口</text>
        </view>
        <button
          class="dashboard-arrange"
          :aria-expanded="arranging"
          @click="arranging = !arranging"
        >
          {{ arranging ? '完成' : '调整顺序' }}
        </button>
      </view>
      <template v-if="arranging">
        <view class="dashboard-arrangement" aria-label="调整快捷入口顺序">
          <view
            v-for="(item, index) in ordered"
            :key="item.id"
            class="arrangement-row"
            :class="{ dragging: dragged === item.id }"
            :style="
              dragged === item.id ? { transform: 'translateY(' + dragOffset + 'px)' } : undefined
            "
          >
            <!-- #ifdef H5 -->
            <div
              class="arrangement-handle"
              aria-hidden="true"
              @pointerdown.prevent="mouseDown(item.id, $event)"
              @pointermove="mouseMove"
              @pointerup="mouseUp"
              @pointercancel="finishDrag(true)"
              @lostpointercapture="finishDrag(true)"
            >
              <text>⠿</text>
            </div>
            <!-- #endif -->
            <!-- #ifndef H5 -->
            <view
              class="arrangement-handle"
              @touchstart.stop="touchDown(item.id, $event)"
              @touchmove.stop.prevent="touchMove"
              @touchend.stop="touchUp"
              @touchcancel.stop="finishDrag(true)"
            >
              <text aria-hidden="true">⠿</text>
            </view>
            <!-- #endif -->
            <AppIcon :name="item.icon" :size="21" />
            <text class="arrangement-name">{{ item.title }}</text>
            <button
              class="arrangement-move"
              :aria-label="item.title + (index === 0 ? '下移' : '上移')"
              @click="swapActions"
            >
              {{ index === 0 ? '下移' : '上移' }}
            </button>
          </view>
        </view>
      </template>
      <view v-else class="dashboard-actions">
        <button
          v-for="item in ordered"
          :key="item.id"
          class="dashboard-action"
          :class="{
            'dashboard-capture': item.id === 'capture',
            'dashboard-consult': item.id === 'consult',
          }"
          @click="item.id === 'capture' ? emit('capture') : emit('consult')"
        >
          <view class="dashboard-action-icon"><AppIcon :name="item.icon" :size="27" /></view>
          <view class="dashboard-action-copy"
            ><text>{{ item.title }}</text
            ><text>{{ item.description }}</text></view
          >
          <AppIcon name="right" :size="18" />
        </button>
      </view>
      <view class="dashboard-tabs" role="tablist" aria-label="首页栏目">
        <button
          v-for="item in sections"
          :key="item.id"
          role="tab"
          :aria-selected="section === item.id"
          :class="{ active: section === item.id }"
          @click="chooseSection(item.id)"
        >
          <AppIcon :name="item.icon" :size="16" /><text>{{ item.label }}</text>
        </button>
      </view>
      <view class="dashboard-section-anchor" />
      <view
        v-show="section === 'recent'"
        class="dashboard-recent"
        role="tabpanel"
        aria-label="最近问诊"
      >
        <view class="dashboard-section-heading"
          ><text>{{ loggedIn ? '接着上次的问诊' : '问诊记录' }}</text
          ><button v-if="loggedIn && records.length" @click="emit('history')">
            全部记录 <AppIcon name="external" :size="14" /></button
        ></view>
        <template v-if="loggedIn && records.length">
          <button
            v-for="record in records.slice(0, 5)"
            :key="record.id"
            class="dashboard-record"
            @click="emit('open', record.id)"
          >
            <image v-if="record.images.length" :src="imageUrl(record)" mode="aspectFill" /><view
              v-else
              class="text-record-icon"
              ><AppIcon name="chat" :size="22"
            /></view>
            <view
              ><text>{{ conversationTitle(record) }}</text
              ><text>{{ record.crop_name }} · {{ dateLabel(record.updated_at) }}</text></view
            >
            <text class="record-state">{{ statusLabel(record.status) }}</text
            ><AppIcon name="right" :size="17" />
          </button>
        </template>
        <view v-else class="dashboard-empty"
          ><view class="empty-record-icon"><AppIcon name="history" :size="25" /></view
          ><text>{{ loggedIn ? '还没有问诊记录' : '登录后保存问诊记录' }}</text
          ><text>{{
            loggedIn
              ? '完成拍照或开始咨询后，可在这里继续查看。'
              : '访客可以使用拍照与咨询，当前内容不保存到历史。'
          }}</text
          ><button v-if="!loggedIn" class="button secondary" @click="emit('login')">
            登录
          </button></view
        >
      </view>
      <KnowledgeLibrary
        v-show="section !== 'recent'"
        embedded
        :reading="mobile"
        :section="section === 'news' ? 'news' : 'library'"
        :read-offset="readOffset"
        :cards="cards"
        @reset-scroll="resetReading"
        @open="emit('card', $event)"
        @source="emit('source', $event)"
      />
    </view>
  </scroll-view>
</template>
<style scoped>
.dashboard-scroll {
  width: 100%;
}
.dashboard-mobile-scroll {
  flex: 1;
  min-height: 0;
  height: 100%;
}
.dashboard {
  max-width: 860px;
  margin: 8px auto 20px;
}
.dashboard-mobile-scroll .dashboard {
  padding: 8px 16px 14px;
  margin: 0;
}
.dashboard-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}
.dashboard-title {
  display: block;
  font-size: 25px;
  font-weight: 650;
}
.dashboard-intro {
  display: block;
  margin-top: 9px;
  color: var(--muted);
  font-size: 13px;
}
.dashboard-arrange,
.arrangement-move {
  min-height: 36px;
  padding: 6px 10px;
  color: var(--muted);
  font-size: 11px;
  border-radius: 9px;
}
.dashboard-arrange {
  background: var(--subtle);
}
.dashboard-actions,
.dashboard-arrangement {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.dashboard-action {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
  width: 100%;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 18px;
  text-align: left;
}
.dashboard-action.dashboard-capture {
  background: var(--accent-soft);
}
.dashboard-action-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 52px;
  height: 52px;
  background: var(--subtle);
  border-radius: 15px;
}
.dashboard-capture .dashboard-action-icon {
  background: var(--surface);
}
.dashboard-action-copy {
  flex: 1;
  min-width: 0;
}
.dashboard-action-copy > text:first-child {
  display: block;
  font-size: 18px;
  font-weight: 650;
}
.dashboard-action-copy > text:last-child {
  display: block;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.65;
  margin-top: 5px;
}
.arrangement-row {
  position: relative;
  display: flex;
  align-items: center;
  gap: 11px;
  min-height: 60px;
  padding: 6px 10px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--surface);
}
.arrangement-row.dragging {
  z-index: 2;
  background: var(--accent-soft);
}
.arrangement-handle {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  width: 40px;
  height: 44px;
  color: var(--muted);
  font-size: 25px;
  cursor: grab;
  user-select: none;
  touch-action: none;
}
.arrangement-name {
  flex: 1;
  min-width: 0;
  font-size: 14px;
}
.arrangement-move {
  background: var(--subtle);
}
.dashboard-recent {
  margin-top: 22px;
}
.dashboard-section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 15px;
  margin-bottom: 10px;
}
.dashboard-section-heading > text {
  font-size: 15px;
  font-weight: 600;
}
.dashboard-section-heading > button {
  font-size: 11px;
  color: var(--accent);
}
.dashboard-record {
  display: flex;
  align-items: center;
  gap: 15px;
  text-align: left;
  width: 100%;
  padding: 19px 0;
  border-bottom: 1px solid var(--line);
}
.dashboard-record > image,
.text-record-icon {
  width: 56px;
  height: 56px;
  min-width: 56px;
  border-radius: 12px;
  background: var(--subtle);
}
.text-record-icon {
  display: flex;
  align-items: center;
  justify-content: center;
}
.dashboard-record > view:nth-child(2) {
  flex: 1;
  min-width: 0;
}
.dashboard-record > view:nth-child(2) > text:first-child {
  display: block;
  font-size: 14px;
  font-weight: 550;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dashboard-record > view:nth-child(2) > text:last-child {
  display: block;
  font-size: 11px;
  color: var(--muted);
  margin-top: 7px;
}
.record-state {
  font-size: 10px;
  color: var(--muted);
  background: var(--subtle);
  padding: 4px 7px;
  border-radius: 6px;
}
.dashboard-record > text:last-child {
  color: var(--muted);
}
.dashboard-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  text-align: center;
  padding: 44px 20px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 17px;
  margin-top: 17px;
}
.empty-record-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 54px;
  height: 54px;
  background: var(--subtle);
  border-radius: 17px;
  margin-bottom: 4px;
}
.dashboard-empty > text:nth-child(2) {
  font-size: 14px;
  font-weight: 550;
}
.dashboard-empty > text:nth-child(3) {
  font-size: 12px;
  color: var(--muted);
  line-height: 1.9;
}
.dashboard-empty > .button {
  min-height: 39px;
  padding: 6px 20px;
  font-size: 12px;
  margin-top: 5px;
}
@media (max-width: 760px) {
  .dashboard-title {
    display: none;
  }
  .dashboard-intro {
    margin: 0;
  }
  .dashboard-heading {
    align-items: center;
    margin: 0 0 10px;
  }
  .dashboard-action {
    padding: 15px 13px;
    gap: 11px;
    border-radius: 16px;
  }
  .dashboard-action-icon {
    width: 46px;
    height: 46px;
    border-radius: 13px;
  }
  .dashboard-action-copy > text:first-child {
    font-size: 16px;
  }
  .dashboard-action-copy > text:last-child {
    font-size: 11px;
  }
  .dashboard-recent {
    margin-top: 20px;
  }
  .dashboard-record {
    gap: 12px;
    padding: 16px 0;
  }
  .dashboard-record > image,
  .text-record-icon {
    width: 48px;
    height: 48px;
    min-width: 48px;
    border-radius: 10px;
  }
  .dashboard-record > view:nth-child(2) > text:first-child {
    font-size: 13px;
  }
  .dashboard-record > view:nth-child(2) > text:last-child {
    font-size: 10px;
  }
  .record-state {
    display: none;
  }
  .dashboard-empty {
    padding: 32px 17px;
  }
  .dashboard-empty > text:nth-child(3) {
    font-size: 11px;
  }
}

.dashboard-tabs {
  display: flex;
  gap: 6px;
  border-bottom: 1px solid var(--line);
  margin: 28px 0 21px;
  padding-bottom: 9px;
}
.dashboard-tabs > button {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 42px;
  padding: 10px 15px;
  border-radius: 11px;
  color: var(--muted);
  font-size: 13px;
}
.dashboard-tabs > button.active {
  background: var(--subtle);
  color: var(--ink);
  font-weight: 550;
}
.dashboard-section-heading > button {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 7px 8px;
  border-radius: 8px;
}
.dashboard-record {
  padding-left: 10px;
  padding-right: 10px;
  border-radius: 12px;
}
.dashboard-empty {
  border-color: transparent;
  box-shadow: 0 2px 12px #00000003;
}
@media (max-width: 760px) {
  .dashboard-tabs {
    gap: 4px;
    margin: 17px 0 8px;
    padding-bottom: 6px;
  }
  .dashboard-tabs > button {
    flex: 1;
    justify-content: center;
    min-width: 0;
    gap: 4px;
    padding: 8px 4px;
    font-size: 12px;
    white-space: nowrap;
  }
}
</style>
