<script setup lang="ts">
import { asset } from '../lib/assets'
withDefaults(defineProps<{ name: string; size?: number; white?: boolean }>(), {
  size: 22,
  white: false,
})
</script>
<template>
  <view
    v-if="name === 'home'"
    class="app-icon home-icon"
    :style="{ width: size + 'px', height: size + 'px' }"
    aria-hidden="true"
    ><view class="home-roof" /><view class="home-body" /><view class="home-door"
  /></view>
  <image
    v-else
    :src="asset('icons/' + name + (white ? '-white' : '') + '.png')"
    :style="{ width: size + 'px', height: size + 'px' }"
    mode="aspectFit"
    class="app-icon"
    :class="{ 'icon-adaptive': !white }"
    aria-hidden="true"
  />
</template>
<style scoped>
.home-icon {
  position: relative;
  color: inherit;
}
.home-roof {
  position: absolute;
  left: 19%;
  top: 7%;
  width: 62%;
  height: 62%;
  transform: rotate(45deg);
  border-left: 1.6px solid currentColor;
  border-top: 1.6px solid currentColor;
  border-radius: 2px;
}
.home-body {
  position: absolute;
  left: 18%;
  right: 18%;
  bottom: 0;
  height: 56%;
  border: 1.6px solid currentColor;
  border-top: 0;
  border-radius: 0 0 2px 2px;
}
.home-door {
  position: absolute;
  left: 42%;
  bottom: 0;
  width: 18%;
  height: 32%;
  border: 1.3px solid currentColor;
  border-bottom: 0;
  border-radius: 2px 2px 0 0;
}

.app-icon {
  flex-shrink: 0;
  display: inline-block;
  vertical-align: middle;
}
</style>
