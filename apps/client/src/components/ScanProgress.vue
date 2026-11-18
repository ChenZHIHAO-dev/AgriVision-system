<script setup lang="ts">
defineProps<{ src: string }>()
</script>
<template>
  <view class="scan-backdrop"
    ><view class="scan-card" role="status" aria-live="polite"
      ><view class="scan-preview"
        ><image :src="src" mode="aspectFit" /><view class="scan-vignette" /><view
          class="scan-line" /><view class="scan-corners" /></view
      ><view class="scan-label"><view class="spinner" /><text>正在识别照片</text></view
      ><text class="scan-description">正在检查画质并分析症状，请稍候。</text></view
    ></view
  >
</template>
<style scoped>
.scan-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1900;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #14171b80;
  backdrop-filter: blur(8px);
  padding: 24px;
  color: var(--ink);
}
.scan-card {
  width: 360px;
  max-width: 100%;
  border: 1px solid var(--line);
  background: var(--elevated);
  border-radius: 23px;
  padding: 15px 15px 23px;
  box-shadow: 0 18px 60px #0003;
}
.scan-preview {
  position: relative;
  height: 255px;
  border-radius: 14px;
  background: var(--subtle);
  overflow: hidden;
}
.scan-preview > image {
  width: 100%;
  height: 100%;
}
.scan-vignette {
  position: absolute;
  inset: 0;
  background: linear-gradient(0deg, #1113, transparent 45%, #1112);
}
.scan-line {
  position: absolute;
  left: 10px;
  right: 10px;
  height: 2px;
  top: 0;
  background: var(--scan-beam);
  box-shadow: 0 0 15px var(--scan-glow);
  animation: photo-scan 1.8s ease-in-out infinite alternate;
}
.scan-corners {
  position: absolute;
  inset: 15px;
  border: 1px solid #ffffff80;
  border-radius: 8px;
  opacity: 0.6;
}
.scan-label {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin: 21px 0 8px;
  font-size: 15px;
  font-weight: 600;
}
.scan-description {
  display: block;
  text-align: center;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.8;
}
@keyframes photo-scan {
  from {
    transform: translateY(15px);
  }
  to {
    transform: translateY(237px);
  }
}
@media (prefers-reduced-motion: reduce) {
  .scan-line {
    animation: none;
    top: 50%;
  }
}
</style>
