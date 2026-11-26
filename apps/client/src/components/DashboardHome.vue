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
  { id: 'recent', label: '最近记录', icon: 'history' },
  { id: 'resources', label: '参考资料', icon: 'book' },
  { id: 'news', label: '农业资讯', icon: 'file' },
] as const

const shortcuts = [
  { id: 'capture', title: '拍照识别', description: '拍摄或上传作物照片', icon: 'camera' },
  { id: 'consult', title: '询问 AI', description: '新建对话，询问作物和田间问题', icon: 'chat' },
] as const
type Shortcut = (typeof shortcuts)[number]['id']
const orderKey = 'agrivision.dashboard.first-action'
const first = ref<Shortcut>(uni.getStorageSync(orderKey) === 'consult' ? 'consult' : 'capture')
const ordered = computed(() =>
  first.value === 'capture' ? shortcuts : [shortcuts[1], shortcuts[0]],
)
const recordQuery = ref('')
const hasHistory = computed(() => props.loggedIn && props.records.length > 0)
const recentEntries = computed(() => {
  if (!hasHistory.value) return []
  const term = recordQuery.value.trim().toLowerCase()
  return props.records
    .filter(
      (entry) =>
        !term ||
        [conversationTitle(entry), entry.title, entry.crop_name, entry.note].some((field) =>
          field?.toLowerCase().includes(term),
        ),
    )
    .slice(0, 5)
})
watch(
  () => props.loggedIn,
  (loggedIn) => {
    if (!loggedIn) recordQuery.value = ''
  },
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
    scroll-y
    :scroll-top="mobile ? scrollTarget : undefined"
    @scroll="scrollDashboard"
  >
    <view
      class="dashboard"
      :style="mobile && viewHeight ? { '--dashboard-view-height': viewHeight + 'px' } : undefined"
    >
      <view class="dashboard-heading">
        <text class="dashboard-title" role="heading" aria-level="2">快捷入口</text>
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
          <view class="dashboard-action-copy">
            <text class="dashboard-action-title">{{ item.title }}</text>
            <text class="dashboard-action-description">{{ item.description }}</text>
          </view>
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
          hover-class="none"
          @click="chooseSection(item.id)"
        >
          <AppIcon :name="item.icon" :size="16" />
          <text class="dashboard-tab-label">{{ item.label }}</text>
        </button>
      </view>
      <view class="dashboard-section-anchor" />
      <view
        v-if="section === 'recent'"
        class="dashboard-recent"
        role="tabpanel"
        aria-label="最近记录"
      >
        <view v-if="hasHistory" class="dashboard-history-tools">
          <view class="dashboard-history-search">
            <AppIcon name="search" :size="17" />
            <input
              v-model="recordQuery"
              type="text"
              confirm-type="search"
              aria-label="搜索最近记录"
              placeholder="搜索作物、标题或备注"
            />
          </view>
          <button class="dashboard-all-records" @click="emit('history')">全部记录</button>
        </view>
        <view v-if="recentEntries.length" class="dashboard-record-list">
          <button
            v-for="record in recentEntries"
            :key="record.id"
            class="dashboard-record"
            @click="emit('open', record.id)"
          >
            <image
              v-if="record.images.length"
              :src="imageUrl(record)"
              mode="aspectFill"
              class="dashboard-record-media"
            />
            <view v-else class="dashboard-record-media text-record-icon">
              <AppIcon name="chat" :size="22" />
            </view>
            <view class="dashboard-record-copy">
              <text class="dashboard-record-title">{{ conversationTitle(record) }}</text>
              <text class="dashboard-record-meta">
                {{ record.crop_name }} · {{ dateLabel(record.updated_at) }}
              </text>
            </view>
            <text class="record-state">{{ statusLabel(record.status) }}</text>
            <AppIcon name="right" :size="17" />
          </button>
        </view>
        <view v-else class="dashboard-empty">
          <view class="empty-record-icon"><AppIcon name="history" :size="25" /></view>
          <view class="dashboard-empty-copy">
            <text class="dashboard-empty-title">{{
              !loggedIn ? '登录后查看记录' : hasHistory ? '没有匹配记录' : '还没有记录'
            }}</text>
            <text class="dashboard-empty-description">{{
              !loggedIn
                ? '登录后使用在线识别、AI 对话和记录。'
                : hasHistory
                  ? '试试作物名、标题或备注里的其他词。'
                  : '拍照识别或新建对话后，可在这里继续查看。'
            }}</text>
          </view>
          <button v-if="!loggedIn" class="button secondary" @click="emit('login')">登录</button>
        </view>
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
<style>
/* #ifdef MP-WEIXIN */
:host {
  display: block;
  flex: 1 1 auto;
  width: 100%;
  min-width: 0;
  min-height: 0;
}
/* #endif */
</style>
<style scoped>
.dashboard-scroll {
  width: 100%;
  flex: 1;
  min-height: 0;
  min-width: 0;
  height: 100%;
}
.dashboard {
  box-sizing: border-box;
  width: 100%;
  max-width: 992px;
  margin: 0 auto;
  padding: 34px 24px;
}
.dashboard-mobile-scroll .dashboard {
  box-sizing: border-box;
  width: 100%;
  padding: 4px 16px 16px;
  max-width: 620px;
  margin: 0 auto;
}
.dashboard-mobile-scroll .dashboard-heading {
  margin-bottom: 8px;
}
.dashboard-mobile-scroll .dashboard-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--muted);
}
.dashboard-mobile-scroll .dashboard-arrange {
  min-height: 44px;
  font-size: 12px;
  background: transparent;
}
.dashboard-mobile-scroll .dashboard-action {
  border-radius: 16px;
}
.dashboard-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}
.dashboard-title {
  font-size: 17px;
  font-weight: 650;
  color: var(--ink);
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
/* #ifdef H5 */
.dashboard-scroll:not(.dashboard-mobile-scroll) .dashboard {
  padding-inline: clamp(20px, 4vw, 48px);
}
.dashboard-scroll:not(.dashboard-mobile-scroll) .dashboard-actions {
  flex-direction: row;
  flex-wrap: wrap;
  gap: 14px;
}
.dashboard-scroll:not(.dashboard-mobile-scroll) .dashboard-action {
  flex: 1 1 270px;
  width: auto;
  min-width: 0;
  min-height: 110px;
}
/* #endif */
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
.dashboard-action-title {
  display: block;
  font-size: 18px;
  font-weight: 650;
}
.dashboard-action-description {
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
.dashboard-recent,
.dashboard-record-list {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  width: 100%;
  min-width: 0;
}
.dashboard-recent {
  gap: 8px;
  margin-top: 14px;
}
.dashboard-history-tools {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-width: 0;
}
.dashboard-history-search {
  display: flex;
  align-items: center;
  flex: 1 1 0;
  min-height: 42px;
  min-width: 0;
  gap: 8px;
  padding: 0 11px;
  border: 1px solid var(--line);
  border-radius: 11px;
  background: var(--surface);
}
.dashboard-history-search > input {
  flex: 1 1 0;
  width: 0;
  min-width: 0;
  font-size: 13px;
}
.dashboard-all-records {
  flex-shrink: 0;
  min-height: 42px;
  padding: 6px 9px;
  border-radius: 9px;
  color: var(--accent);
  font-size: 12px;
  white-space: nowrap;
}
.dashboard-record {
  display: flex;
  align-items: center;
  gap: 15px;
  width: 100%;
  min-width: 0;
  padding: 15px 10px;
  border-bottom: 1px solid var(--line);
  border-radius: 12px;
  text-align: left;
}
.dashboard-record-media {
  flex-shrink: 0;
  width: 56px;
  height: 56px;
  border-radius: 12px;
  background: var(--subtle);
}
.text-record-icon {
  display: flex;
  align-items: center;
  justify-content: center;
}
.dashboard-record-copy {
  flex: 1 1 0;
  min-width: 0;
}
.dashboard-record-title,
.dashboard-record-meta {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dashboard-record-title {
  font-size: 14px;
  font-weight: 550;
}
.dashboard-record-meta {
  margin-top: 5px;
  color: var(--muted);
  font-size: 11px;
}
.record-state {
  flex-shrink: 0;
  white-space: nowrap;
  font-size: 10px;
  color: var(--muted);
  background: var(--subtle);
  padding: 4px 7px;
  border-radius: 6px;
}
.dashboard-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  width: 100%;
  min-width: 0;
  text-align: center;
  padding: 44px 20px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 17px;
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
.dashboard-empty-copy {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.dashboard-empty-title {
  font-size: 14px;
  font-weight: 550;
}
.dashboard-empty-description {
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
    font-size: 14px;
    font-weight: 550;
    color: var(--muted);
  }
  .dashboard-heading {
    align-items: center;
    margin: 0 0 8px;
  }
  .dashboard-actions,
  .dashboard-arrangement {
    gap: 8px;
  }
  .dashboard-action {
    min-height: 68px;
    padding: 10px 12px;
    gap: 10px;
    border-radius: 15px;
  }
  .dashboard-action-icon {
    width: 42px;
    height: 42px;
    border-radius: 12px;
  }
  .dashboard-action-title {
    font-size: 16px;
    line-height: 1.35;
  }
  .dashboard-action-description {
    margin-top: 4px;
    font-size: 12px;
    line-height: 1.4;
  }
  .dashboard-recent {
    margin-top: 10px;
  }
  .dashboard-record {
    gap: 10px;
    padding: 11px 9px;
  }
  .dashboard-record-media {
    width: 44px;
    height: 44px;
    border-radius: 10px;
  }
  .dashboard-record-title {
    font-size: 13px;
  }
  .dashboard-record-meta {
    font-size: 11px;
  }
  .record-state {
    display: none;
  }
  .dashboard-empty {
    min-height: 76px;
    flex-direction: row;
    gap: 10px;
    padding: 12px;
    text-align: left;
  }
  .empty-record-icon {
    flex-shrink: 0;
    width: 38px;
    height: 38px;
    margin-bottom: 0;
    border-radius: 12px;
  }
  .dashboard-empty-copy {
    flex: 1;
    min-width: 0;
    gap: 3px;
  }
  .dashboard-empty-title {
    line-height: 1.35;
  }
  .dashboard-empty-description {
    font-size: 11px;
    line-height: 1.5;
  }
  .dashboard-empty > .button {
    flex-shrink: 0;
    min-width: 48px;
    min-height: 40px;
    margin-top: 0;
    padding: 6px 10px;
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
.dashboard-empty {
  border-color: transparent;
  box-shadow: 0 2px 12px #00000003;
}
@media (max-width: 760px) {
  .dashboard-tabs {
    gap: 4px;
    margin: 12px 0 6px;
    padding-bottom: 5px;
  }
  .dashboard-tabs > button {
    flex: 1 1 0;
    justify-content: center;
    align-items: center;
    min-width: 0;
    min-height: 44px;
    gap: 4px;
    padding: 8px 4px;
    color: var(--muted);
    font-size: 12px;
    font-weight: 550;
    line-height: 1.35;
  }
  .dashboard-tabs > button.active {
    background: var(--accent-soft);
  }
  .dashboard-tab-label {
    flex-shrink: 0;
    font-size: 12px;
    line-height: 1.35;
    white-space: nowrap;
  }
}
@media (max-width: 360px) {
  .dashboard-mobile-scroll .dashboard {
    padding-right: 12px;
    padding-left: 12px;
  }
}
</style>
