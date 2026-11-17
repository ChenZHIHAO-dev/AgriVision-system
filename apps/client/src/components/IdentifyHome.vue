<script setup lang="ts">
import { computed } from 'vue'
import AppIcon from './AppIcon.vue'
import type { CaseRecord, Crop, Meta } from '../lib/api'
import { asset } from '../lib/assets'
import { dateLabel } from '../lib/options'
const props = defineProps<{
  crop: Crop
  records: CaseRecord[]
  loggedIn: boolean
  models: Meta['models']
  busy: boolean
}>()
const emit = defineEmits<{
  crop: [value: Crop]
  capture: [source: 'camera' | 'album']
  consult: [value: Crop]
  open: [id: string]
  history: []
  login: []
}>()
const choices: [Crop, string][] = [
  ['wheat', '小麦'],
  ['maize', '玉米'],
  ['peanut', '花生'],
]
const ready = computed(() => props.models.some((item) => item.crop === props.crop && item.ready))
const recent = computed(() => props.records.slice(0, 3))
</script>
<template>
  <view class="photo-home">
    <view class="photo-home-heading"
      ><text class="photo-home-title">拍照识别</text
      ><text class="photo-home-subtitle">选择作物，拍摄或上传症状照片。</text></view
    >
    <view class="photo-workbench">
      <view class="photo-main">
        <view class="crop-choices" role="group" aria-label="选择照片中的作物"
          ><button
            v-for="[id, name] in choices"
            :key="id"
            :class="{ selected: crop === id }"
            :aria-pressed="crop === id"
            @click="emit('crop', id)"
          >
            <image :src="asset('crops/' + id + '.png')" mode="aspectFit" /><text>{{ name }}</text>
          </button></view
        >
        <view class="camera-stage">
          <view class="camera-halo"
            ><button
              class="button primary camera-shutter"
              aria-label="拍摄作物照片"
              :disabled="busy"
              @click="emit('capture', 'camera')"
            >
              <AppIcon name="camera" white :size="39" /></button
          ></view>
          <text class="camera-title">拍摄作物照片</text
          ><text class="camera-description">对准有异常的叶片，保持画面清晰</text>
          <button class="album-button" :disabled="busy" @click="emit('capture', 'album')">
            <AppIcon name="upload" :size="17" /><text>从相册上传</text>
          </button>
        </view>
        <view class="recognition-scope"
          ><view class="scope-dot" :class="{ ready }" /><text>{{
            ready
              ? '小麦：条锈病、叶锈病、白粉病及健康参考'
              : crop === 'wheat'
                ? '图片识别服务暂不可用，可先进行文字咨询'
                : '该作物的图片识别尚未开放，可先进行文字咨询'
          }}</text></view
        >
      </view>
      <view class="photo-aside">
        <view class="shooting-guide"
          ><text class="aside-label">拍摄要点</text
          ><view><text>01</text><text>拍清叶片正面与背面</text></view
          ><view><text>02</text><text>需要时补充整株照片</text></view
          ><view><text>03</text><text>一次问诊可添加多张照片</text></view
          ><text class="file-note">JPG / PNG / WebP · 单张不超过 8MB</text></view
        >
        <view class="recent-observations"
          ><view class="recent-heading"
            ><text class="aside-label">最近问诊</text
            ><button v-if="loggedIn && recent.length" @click="emit('history')">全部 ↗</button></view
          >
          <template v-if="loggedIn && recent.length"
            ><button
              v-for="record in recent"
              :key="record.id"
              class="recent-observation"
              @click="emit('open', record.id)"
            >
              <view class="recent-icon"
                ><AppIcon :name="record.images.length ? 'camera' : 'chat'" :size="18" /></view
              ><view
                ><text>{{ record.title }}</text
                ><text>{{ record.crop_name }} · {{ dateLabel(record.updated_at) }}</text></view
              ><text>›</text>
            </button></template
          >
          <template v-else
            ><text class="recent-empty">{{
              loggedIn ? '还没有问诊记录。' : '登录后可保存问诊，随时继续对话。'
            }}</text
            ><button v-if="!loggedIn" class="recent-login" @click="emit('login')">
              登录保存记录 ↗
            </button></template
          >
        </view>
      </view>
    </view>
    <button class="text-consult" :disabled="busy" @click="emit('consult', crop)">
      <AppIcon name="chat" :size="18" /><text>不拍照，直接文字咨询</text><text>→</text>
    </button>
  </view>
</template>
<style scoped>
.photo-home {
  max-width: 1000px;
  margin: 8px auto 0;
}
.photo-home-heading {
  margin-bottom: 28px;
}
.photo-home-title {
  display: block;
  font-size: 26px;
  font-weight: 650;
  letter-spacing: -0.5px;
}
.photo-home-subtitle {
  display: block;
  font-size: 13px;
  color: var(--muted);
  margin-top: 9px;
}
.photo-workbench {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 36px;
}
.photo-main {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 22px;
  overflow: hidden;
}
.crop-choices {
  display: flex;
  gap: 6px;
  background: var(--subtle);
  padding: 5px;
  margin: 20px 22px 0;
  border-radius: 13px;
}
.crop-choices > button {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  min-height: 43px;
  border-radius: 10px;
  color: var(--muted);
  border: 1px solid transparent;
}
.crop-choices > button.selected {
  background: var(--surface);
  color: var(--ink);
  border-color: var(--line);
  box-shadow: 0 2px 5px #00000005;
}
.crop-choices image {
  width: 22px;
  height: 27px;
}
.camera-stage {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 29px 20px 24px;
}
.camera-halo {
  padding: 18px;
  background: var(--subtle);
  border-radius: 50%;
}
.camera-shutter {
  width: 92px;
  height: 92px;
  min-width: 92px;
  border-radius: 50%;
  padding: 0;
  box-shadow: 0 6px 18px #00000012;
}
.camera-title {
  font-size: 17px;
  font-weight: 600;
  margin-top: 21px;
}
.camera-description {
  font-size: 12px;
  color: var(--muted);
  margin-top: 8px;
}
.album-button {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 9px;
  font-size: 13px;
  margin-top: 22px;
  padding: 10px 19px;
  min-height: 42px;
  border: 1px solid var(--line);
  border-radius: 11px;
  background: var(--elevated);
  color: var(--ink);
}
.recognition-scope {
  display: flex;
  align-items: flex-start;
  justify-content: center;
  gap: 7px;
  border-top: 1px solid var(--line);
  padding: 13px 18px;
  font-size: 11px;
  line-height: 1.8;
  color: var(--muted);
  background: var(--elevated);
}
.scope-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--muted);
  margin-top: 7px;
  flex-shrink: 0;
}
.scope-dot.ready {
  background: var(--accent);
}
.photo-aside {
  padding-top: 3px;
}
.aside-label {
  font-size: 13px;
  font-weight: 600;
}
.shooting-guide > view {
  display: flex;
  gap: 13px;
  align-items: center;
  margin-top: 21px;
  font-size: 12px;
  color: var(--muted);
}
.shooting-guide > view > text:first-child {
  font-size: 10px;
  color: var(--muted);
}
.file-note {
  display: block;
  font-size: 10px;
  color: var(--muted);
  line-height: 1.8;
  margin-top: 22px;
}
.recent-observations {
  margin-top: 27px;
  padding-top: 22px;
  border-top: 1px solid var(--line);
}
.recent-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.recent-heading > button,
.recent-login {
  color: var(--accent);
  font-size: 11px;
}
.recent-observation {
  display: flex;
  gap: 10px;
  align-items: center;
  text-align: left;
  width: 100%;
  padding: 16px 0;
  border-bottom: 1px solid var(--line);
}
.recent-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 35px;
  height: 35px;
  border-radius: 10px;
  background: var(--subtle);
  flex-shrink: 0;
}
.recent-observation > view:nth-child(2) {
  min-width: 0;
  flex: 1;
}
.recent-observation > view:nth-child(2) > text:first-child {
  display: block;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.recent-observation > view:nth-child(2) > text:last-child {
  display: block;
  font-size: 10px;
  color: var(--muted);
  margin-top: 5px;
}
.recent-observation > text {
  color: var(--muted);
}
.recent-empty {
  display: block;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.9;
  margin: 17px 0 10px;
}
.text-consult {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  font-size: 13px;
  color: var(--muted);
  min-height: 44px;
  padding: 10px;
  margin: 19px 0 0;
  width: calc(100% - 316px);
}
@media (max-width: 900px) {
  .photo-workbench {
    grid-template-columns: minmax(0, 1fr) 230px;
    gap: 25px;
  }
  .text-consult {
    width: calc(100% - 255px);
  }
}
@media (max-width: 760px) {
  .photo-home {
    margin: 5px auto 10px;
  }
  .photo-home-heading {
    margin-bottom: 21px;
  }
  .photo-home-title {
    font-size: 24px;
  }
  .photo-home-subtitle {
    font-size: 12px;
    line-height: 1.8;
  }
  .photo-workbench {
    display: flex;
    flex-direction: column;
    gap: 23px;
  }
  .crop-choices {
    margin: 15px 15px 0;
  }
  .camera-stage {
    padding: 23px 15px;
  }
  .camera-halo {
    padding: 15px;
  }
  .camera-shutter {
    width: 85px;
    height: 85px;
    min-width: 85px;
  }
  .camera-title {
    margin-top: 17px;
    font-size: 16px;
  }
  .camera-description {
    font-size: 11px;
  }
  .album-button {
    margin-top: 18px;
  }
  .recognition-scope {
    font-size: 10px;
    padding: 11px 14px;
  }
  .shooting-guide {
    display: none;
  }
  .recent-observations {
    margin-top: 0;
    padding-top: 0;
    border-top: 0;
  }
  .recent-observation {
    padding: 13px 0;
  }
  .text-consult {
    width: 100%;
    margin-top: 12px;
  }
  .photo-aside {
    order: 2;
  }
  .recent-empty {
    font-size: 11px;
    margin-top: 12px;
  }
  .recent-heading > .aside-label {
    font-size: 12px;
  }
}
</style>
