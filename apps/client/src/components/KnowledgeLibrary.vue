<script setup lang="ts">
import { computed, ref } from 'vue'
import AppIcon from './AppIcon.vue'
import type { KnowledgeCard, Source } from '../lib/api'
import { crops } from '../lib/options'
import newsData from '../../../../knowledge/news.json'
const props = defineProps<{ cards: KnowledgeCard[]; embedded?: boolean }>()
const emit = defineEmits<{ open: [card: KnowledgeCard]; source: [source: Source] }>()
const section = ref<'library' | 'news'>('library'),
  filter = ref('all'),
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
</script>
<template>
  <view class="library" :class="{ embedded }">
    <view class="library-controls">
      <view class="library-heading"
        ><view
          ><text class="library-title">{{ embedded ? '参考资料' : '植保知识' }}</text
          ><text class="library-subtitle">病虫害资料、种植管理与公开资讯</text></view
        ><view class="layout-switch" aria-label="资料显示方式"
          ><button
            aria-label="网格视图"
            :aria-pressed="layout === 'grid'"
            :class="{ active: layout === 'grid' }"
            @click="setLayout('grid')"
          >
            <AppIcon name="grid" :size="17" /></button
          ><button
            aria-label="列表视图"
            :aria-pressed="layout === 'list'"
            :class="{ active: layout === 'list' }"
            @click="setLayout('list')"
          >
            <AppIcon name="list" :size="17" /></button></view
      ></view>
      <view class="library-tabs" role="tablist" aria-label="知识栏目"
        ><button
          role="tab"
          :aria-selected="section === 'library'"
          :class="{ active: section === 'library' }"
          @click="section = 'library'"
        >
          知识库<text>{{ cards.length }}</text></button
        ><button
          role="tab"
          :aria-selected="section === 'news'"
          :class="{ active: section === 'news' }"
          @click="section = 'news'"
        >
          农业资讯
        </button></view
      >
      <view class="library-tools"
        ><view class="library-filters"
          ><button :class="{ active: filter === 'all' }" @click="filter = 'all'">全部</button
          ><button
            v-for="crop in crops"
            :key="crop.id"
            :class="{ active: filter === crop.id }"
            @click="filter = crop.id"
          >
            {{ crop.name }}
          </button></view
        ><view class="library-search"
          ><AppIcon name="search" :size="16" /><input
            v-model="query"
            aria-label="搜索知识与资讯"
            placeholder="搜索病害、症状或标题" /></view
      ></view>
    </view>
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
.embedded .library-title {
  font-size: 17px;
}
.embedded .library-subtitle {
  font-size: 11px;
}
.embedded {
  margin-top: 22px;
}
@media (max-width: 760px) {
  .library-controls {
    position: sticky;
    top: 0;
    z-index: 12;
    padding: 10px 0 9px;
    background: var(--bg);
    border-bottom: 1px solid var(--line);
    margin-bottom: 16px;
  }
  .library-heading {
    margin-bottom: 10px;
    align-items: center;
  }
  .library-heading > view:first-child {
    display: none;
  }
  .library-heading .layout-switch {
    margin-left: auto;
  }
  .library-tabs {
    margin-top: -43px;
    margin-right: 90px;
    border-bottom: 0;
    min-height: 40px;
  }
  .library-tools {
    margin-top: 9px;
    margin-bottom: 0;
    gap: 9px;
  }
  .library-search {
    min-height: 36px;
  }
}
</style>
