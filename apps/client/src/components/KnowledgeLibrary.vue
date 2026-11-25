<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'
import type { KnowledgeCard, Source } from '../lib/api'
import { crops } from '../lib/options'
import newsData from '../../../../knowledge/news.json'
const props = defineProps<{
  cards: KnowledgeCard[]
  embedded?: boolean
  section?: 'library' | 'news'
  reading?: boolean
  readOffset?: number
}>()
const emit = defineEmits<{
  open: [card: KnowledgeCard]
  source: [source: Source]
  resetScroll: []
}>()
const localSection = ref<'library' | 'news'>('library')
const section = computed(() => props.section ?? localSection.value)
const filter = ref('all'),
  query = ref('')
const layout = ref(uni.getStorageSync('agrivision.knowledge.layout') === 'list' ? 'list' : 'grid')
function setLayout(value: 'grid' | 'list') {
  layout.value = value
  uni.setStorageSync('agrivision.knowledge.layout', value)
}
const filtered = computed(() =>
  props.cards.filter(
    (card) =>
      (filter.value === 'all' || card.crop === filter.value || card.crop === 'general') &&
      (card.title + card.summary + card.keywords.join('')).includes(query.value.trim()),
  ),
)
const news = computed(() =>
  newsData.filter(
    (item) =>
      (filter.value === 'all' || item.crop === filter.value || item.crop === 'general') &&
      (item.title + item.summary + item.source).includes(query.value.trim()),
  ),
)
const TOOLS_HEIGHT = 46
const TOP_MARGIN = 24
const toolsOffset = ref(0)
const settling = ref(false)
const openedByButton = ref(false)
const toolsId = 'library-tools-' + Math.random().toString(36).slice(2, 8)
const isCompact = computed(() => toolsOffset.value >= TOOLS_HEIGHT / 2)
let nativeSticky = false
// #ifdef MP-WEIXIN
nativeSticky = true
// #endif
const showFilterToggle = computed(() => nativeSticky || isCompact.value || openedByButton.value)
const filterLabel = computed(() => crops.find((crop) => crop.id === filter.value)?.name || '筛选')
let scrollTop = 0
let toolProgress = 0
let idle: ReturnType<typeof setTimeout> | undefined

const pinStyle = computed(() => {
  // #ifndef H5 || MP-WEIXIN
  return props.reading ? { transform: 'translateY(' + (props.readOffset || 0) + 'px)' } : undefined
  // #endif
})

function applyToolsOffset(offset: number, animate: boolean) {
  toolProgress = offset
  settling.value = animate
  toolsOffset.value = offset
}

function scrollReading(nextTop: number) {
  if (!props.reading || nextTop === scrollTop) return
  clearTimeout(idle)
  openedByButton.value = false
  const delta = nextTop - Math.max(TOP_MARGIN, scrollTop)
  toolProgress =
    nextTop <= TOP_MARGIN ? 0 : Math.min(TOOLS_HEIGHT, Math.max(0, toolProgress + delta))
  scrollTop = nextTop
  // On WeChat, only the secondary toolbar animates between its two positions.
  // The search row remains pinned by WXSS, independently of scroll events.
  if (!nativeSticky || toolProgress === 0 || toolProgress === TOOLS_HEIGHT) {
    applyToolsOffset(toolProgress, nativeSticky)
  }
  if (nextTop > TOOLS_HEIGHT + TOP_MARGIN && toolsOffset.value < TOOLS_HEIGHT) {
    idle = setTimeout(() => applyToolsOffset(TOOLS_HEIGHT, true), 1200)
  }
}

function toggleTools() {
  clearTimeout(idle)
  openedByButton.value = isCompact.value
  applyToolsOffset(openedByButton.value ? 0 : TOOLS_HEIGHT, true)
}

function restartReading() {
  if (!props.reading) return
  clearTimeout(idle)
  openedByButton.value = false
  applyToolsOffset(0, false)
  emit('resetScroll')
}

watch(() => props.readOffset ?? 0, scrollReading)
watch([filter, section, query, layout], restartReading)
onBeforeUnmount(() => clearTimeout(idle))
</script>
<template>
  <view class="library" :class="{ embedded, reading }">
    <view class="library-pin" :style="pinStyle">
      <view v-if="reading" class="reading-search">
        <view class="library-search">
          <AppIcon name="search" :size="17" />
          <input
            v-model="query"
            :adjust-position="false"
            aria-label="搜索知识与资讯"
            placeholder="搜索病害、症状或标题"
          />
        </view>
        <button
          v-if="showFilterToggle"
          class="reading-toggle"
          :class="{ 'native-filter-toggle': nativeSticky }"
          :aria-label="isCompact ? '展开作物筛选与资料工具' : '收起资料工具'"
          :aria-controls="toolsId"
          :aria-expanded="!isCompact"
          @click="toggleTools"
        >
          <text>{{ isCompact ? filterLabel : '收起' }}</text>
          <AppIcon name="chevron" :size="13" />
        </button>
      </view>

      <view
        :id="toolsId"
        class="library-controls"
        :aria-hidden="reading && toolsOffset >= TOOLS_HEIGHT"
        :inert="(reading && toolsOffset >= TOOLS_HEIGHT) || undefined"
      >
        <view
          class="library-toolbar"
          :class="{ settling }"
          :style="reading ? { transform: 'translateY(-' + toolsOffset + 'px)' } : undefined"
        >
          <view class="library-heading">
            <view v-if="!embedded && !reading">
              <text class="library-title">植保知识</text>
              <text class="library-subtitle">病虫害资料、种植管理与公开资讯</text>
            </view>
            <view class="layout-switch" aria-label="资料显示方式">
              <button
                aria-label="网格视图"
                :aria-pressed="layout === 'grid'"
                :class="{ active: layout === 'grid' }"
                @click="setLayout('grid')"
              >
                <AppIcon name="grid" :size="17" />
              </button>
              <button
                aria-label="列表视图"
                :aria-pressed="layout === 'list'"
                :class="{ active: layout === 'list' }"
                @click="setLayout('list')"
              >
                <AppIcon name="list" :size="17" />
              </button>
            </view>
          </view>
          <view v-if="!embedded" class="library-tabs" role="tablist" aria-label="知识栏目">
            <button
              role="tab"
              :aria-selected="section === 'library'"
              :class="{ active: section === 'library' }"
              @click="localSection = 'library'"
            >
              知识库<text v-if="!reading">{{ cards.length }}</text>
            </button>
            <button
              role="tab"
              :aria-selected="section === 'news'"
              :class="{ active: section === 'news' }"
              @click="localSection = 'news'"
            >
              农业资讯
            </button>
          </view>
          <view class="library-tools">
            <view class="library-filters" aria-label="按作物筛选">
              <button
                :class="{ active: filter === 'all' }"
                :aria-pressed="filter === 'all'"
                @click="filter = 'all'"
              >
                全部
              </button>
              <button
                v-for="crop in crops"
                :key="crop.id"
                :class="{ active: filter === crop.id }"
                :aria-pressed="filter === crop.id"
                @click="filter = crop.id"
              >
                {{ crop.name }}
              </button>
            </view>
            <view v-if="!reading" class="library-search">
              <AppIcon name="search" :size="16" />
              <input
                v-model="query"
                aria-label="搜索知识与资讯"
                placeholder="搜索病害、症状或标题"
              />
            </view>
          </view>
        </view>
      </view>
    </view>
    <view class="library-results">
      <view v-if="section === 'library'" class="library-items" :class="layout">
        <button
          v-for="card in filtered"
          :key="card.id"
          class="library-card"
          @click="emit('open', card)"
        >
          <view class="library-card-top"
            ><view class="library-card-icon"
              ><AppIcon :name="card.crop === 'general' ? 'camera' : card.crop" :size="23" /></view
            ><text>{{ card.category }}</text></view
          ><view class="library-copy"
            ><text class="library-card-title">{{ card.title }}</text
            ><text class="library-card-summary">{{ card.summary }}</text></view
          ><view class="library-card-footer"
            ><text>{{ card.sources.length ? '附参考来源' : '拍摄与操作指南' }}</text
            ><text>↗</text></view
          >
        </button>
      </view>
      <template v-else
        ><text class="news-note">精选公开资讯，点击查看原文。请按原文发布时间和本地农时参考。</text
        ><view class="library-items" :class="layout"
          ><button
            v-for="item in news"
            :key="item.id"
            class="library-card news-card"
            @click="emit('source', { title: item.title, url: item.url, date: item.date })"
          >
            <view class="library-card-top"
              ><text class="news-category">{{ item.category }}</text
              ><text>{{ item.date }}</text></view
            ><view class="library-copy"
              ><text class="library-card-title">{{ item.title }}</text
              ><text class="library-card-summary">{{ item.summary }}</text></view
            ><view class="library-card-footer"
              ><text>{{ item.source }}</text
              ><text>↗</text></view
            >
          </button></view
        ></template
      >
      <view v-if="section === 'library' ? !filtered.length : !news.length" class="library-empty"
        ><text>没有找到相关内容</text><text>试试其他关键词，或切换作物分类。</text></view
      >
    </view>
  </view>
</template>
<style scoped>
.library {
  max-width: 1050px;
  margin: 7px auto 0;
}
.library-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 25px;
}
.library-title {
  display: block;
  font-size: 26px;
  font-weight: 650;
  letter-spacing: -0.5px;
}
.library-subtitle {
  display: block;
  font-size: 12px;
  color: var(--muted);
  margin-top: 9px;
}
.layout-switch {
  display: flex;
  align-items: center;
  background: var(--subtle);
  padding: 4px;
  border-radius: 11px;
  gap: 3px;
  border: 1px solid var(--line);
}
.layout-switch > button {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 33px;
  height: 32px;
  border-radius: 8px;
  color: var(--muted);
}
.layout-switch > button.active {
  background: var(--surface);
  color: var(--ink);
  box-shadow: 0 1px 4px #0000000c;
}
.grid-symbol {
  display: grid;
  grid-template-columns: repeat(2, 6px);
  gap: 3px;
}
.grid-symbol > view {
  height: 6px;
  border: 1.4px solid currentColor;
  border-radius: 1.5px;
}
.list-symbol {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 16px;
}
.list-symbol > view {
  height: 1.5px;
  background: currentColor;
  border-radius: 1px;
}
.library-tabs {
  display: flex;
  gap: 28px;
  border-bottom: 1px solid var(--line);
}
.library-tabs > button {
  font-size: 14px;
  color: var(--muted);
  padding: 0 1px 13px;
  border-bottom: 2px solid transparent;
  min-height: 36px;
  display: flex;
  align-items: center;
  gap: 7px;
}
.library-tabs > button.active {
  font-weight: 600;
  color: var(--ink);
  border-color: var(--accent);
}
.library-tabs > button > text {
  font-size: 10px;
  border-radius: 6px;
  padding: 2px 5px;
  background: var(--subtle);
  color: var(--muted);
}
.library-tools {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin: 20px 0;
}
.library-filters {
  display: flex;
  align-items: center;
  gap: 6px;
}
.library-filters > button {
  padding: 7px 13px;
  font-size: 12px;
  min-height: 34px;
  color: var(--muted);
  border-radius: 9px;
}
.library-filters > button.active {
  color: var(--accent);
  background: var(--accent-soft);
}
.library-search {
  display: flex;
  align-items: center;
  gap: 9px;
  max-width: 285px;
  min-height: 39px;
  border: 1px solid var(--line);
  border-radius: 11px;
  padding: 8px 12px;
  background: var(--surface);
}
.library-search input {
  font-size: 12px;
  min-width: 0;
  width: 210px;
  color: var(--ink);
}
.library-items.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-content: start;
  gap: 17px;
}
.library-card {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  text-align: left;
  border: 1px solid var(--line);
  border-radius: 17px;
  background: var(--surface);
  padding: 22px;
  min-width: 0;
  width: 100%;
  transition:
    border-color 0.15s ease,
    background 0.15s ease;
}
.library-card:hover {
  border-color: var(--muted);
  background: var(--elevated);
}
.library-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--muted);
  font-size: 10px;
}
.library-card-icon {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 11px;
  background: var(--subtle);
}
.library-card-title {
  display: block;
  font-size: 17px;
  font-weight: 600;
  line-height: 1.6;
  margin: 17px 0 10px;
}
.library-card-summary {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-size: 12px;
  line-height: 1.9;
  color: var(--muted);
}
.library-card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 17px;
  font-size: 10px;
  color: var(--muted);
  margin-top: 20px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
}
.library-card-footer > text:first-child {
  flex: 1;
  min-width: 0;
}
.library-copy {
  flex: 1;
  min-width: 0;
}
.library-items.list {
  display: flex;
  flex-direction: column;
  gap: 11px;
}
.list .library-card {
  display: grid;
  grid-template-columns: 43px minmax(0, 1fr) 20px;
  gap: 16px;
  align-items: center;
  padding: 18px 20px;
}
.list .library-card-top > text {
  display: none;
}
.list .library-card-title {
  font-size: 15px;
  margin: 0 0 5px;
}
.list .library-card-summary {
  -webkit-line-clamp: 2;
}
.list .library-card-footer {
  border: 0;
  padding: 0;
  margin: 0;
  font-size: 15px;
}
.list .library-card-footer > text:first-child {
  display: none;
}
.list .news-card {
  grid-template-columns: minmax(0, 1fr) 20px;
}
.list .news-card .library-card-top {
  grid-column: 1;
  grid-row: 1;
}
.list .news-card .library-card-top > text {
  display: block;
}
.list .news-card .library-copy {
  grid-column: 1;
  grid-row: 2;
}
.list .news-card .library-card-footer {
  grid-column: 2;
  grid-row: 1/3;
}
.news-category {
  color: var(--accent);
}
.news-note {
  display: block;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.9;
  margin-bottom: 16px;
}
.library-empty {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: center;
  color: var(--muted);
  padding: 65px 15px;
  font-size: 14px;
}
.library-empty > text:last-child {
  font-size: 12px;
}
@media (max-width: 760px) {
  .library-heading {
    margin-bottom: 23px;
  }
  .library-title {
    font-size: 24px;
  }
  .library-subtitle {
    font-size: 11px;
    line-height: 1.8;
  }
  .library-tabs {
    gap: 26px;
  }
  .library-tools {
    flex-wrap: wrap;
    gap: 12px;
    margin: 17px 0;
  }
  .library-filters {
    width: 100%;
    justify-content: space-between;
  }
  .library-filters > button {
    flex: 1;
    min-height: 36px;
  }
  .library-search {
    max-width: none;
    width: 100%;
    min-height: 42px;
  }
  .library-search input {
    width: 100%;
    font-size: 13px;
  }
  .library-items.grid {
    gap: 11px;
  }
  .library-card {
    padding: 15px 13px;
    border-radius: 14px;
  }
  .library-card-title {
    font-size: 15px;
    margin-top: 13px;
  }
  .library-card-summary {
    font-size: 11px;
    line-height: 1.9;
    -webkit-line-clamp: 3;
  }
  .library-card-top {
    font-size: 9px;
    gap: 5px;
  }
  .library-card-icon {
    width: 31px;
    height: 31px;
  }
  .library-card-footer {
    font-size: 9px;
    margin-top: 14px;
    padding-top: 10px;
    gap: 6px;
  }
  .list .library-card {
    gap: 11px;
    padding: 16px 13px;
    grid-template-columns: 33px minmax(0, 1fr) 13px;
  }
  .list .library-card-title {
    font-size: 14px;
  }
  .list .news-card {
    grid-template-columns: minmax(0, 1fr) 13px;
  }
  .news-note {
    font-size: 11px;
  }
  .layout-switch > button {
    width: 31px;
    height: 31px;
  }
}
.embedded {
  margin-top: 12px;
}
.embedded:not(.reading) .library-toolbar {
  display: flex;
  flex-direction: row-reverse;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
.embedded:not(.reading) .library-heading,
.embedded:not(.reading) .library-tools {
  margin: 0;
}
.embedded:not(.reading) .library-tools {
  flex: 1;
}
.library.reading {
  --reading-search-height: 56px;
  --reading-tools-height: 46px;
  min-height: var(--dashboard-view-height, 0px);
  margin: 0;
}
.reading .library-pin {
  position: relative;
  z-index: 2;
  min-height: var(--reading-search-height);
  /* #ifdef H5 || MP-WEIXIN */
  position: sticky;
  top: 0;
  /* #endif */
}
.reading-search {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: var(--reading-search-height);
  position: relative;
  padding: 6px 0;
  background: var(--bg);
  border-bottom: 1px solid var(--line);
  z-index: 3;
}
.reading-search .library-search {
  flex: 1;
  width: auto;
  min-width: 0;
  min-height: 42px;
}
.reading-search input {
  width: 100%;
  flex: 1;
}
.reading-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  gap: 4px;
  min-height: 42px;
  min-width: 64px;
  padding: 6px 9px;
  border-radius: 10px;
  background: var(--subtle);
  color: var(--ink);
  font-size: 12px;
}
.native-filter-toggle {
  width: 66px;
}
.reading-toggle[aria-expanded='true'] :deep(.app-icon) {
  transform: rotate(180deg);
}
.reading .library-controls {
  position: absolute;
  z-index: 2;
  top: var(--reading-search-height);
  left: 0;
  right: 0;
  height: var(--reading-tools-height);
  overflow: hidden;
  pointer-events: none;
}
.reading .library-toolbar {
  display: flex;
  flex-direction: row-reverse;
  gap: 8px;
  align-items: center;
  height: var(--reading-tools-height);
  background: var(--bg);
  box-shadow: inset 0 -1px var(--line);
  pointer-events: auto;
}
.reading .library-toolbar.settling {
  transition: transform 0.2s ease-out;
}
.reading .library-heading {
  margin: 0;
  flex-shrink: 0;
}
.reading .layout-switch {
  padding: 2px;
}
.reading .library-tools {
  flex: 1;
  min-width: 0;
  margin: 0;
}
.reading .library-filters {
  width: 100%;
  padding: 0;
  gap: 2px;
}
.reading .library-filters > button {
  min-width: 0;
  min-height: 36px;
  padding: 4px 2px;
  white-space: nowrap;
}
.reading .library-results {
  padding-top: calc(var(--reading-tools-height) + 14px);
}
.reading .library-empty {
  padding: 24px 10px;
}
@media (prefers-reduced-motion: reduce) {
  .reading .library-toolbar.settling {
    transition: none;
  }
}
</style>
