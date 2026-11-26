<script setup lang="ts">
import AppIcon from './AppIcon.vue'
import type { User } from '../lib/auth'
import { appVersion } from '../lib/appInfo'
withDefaults(defineProps<{ user: User | null; admin: boolean; capsuleInset?: number }>(), {
  capsuleInset: 0,
})
const emit = defineEmits<{
  login: []
  settings: []
  admin: []
  logout: []
}>()
</script>
<template>
  <view class="user-center">
    <!-- #ifndef MP-WEIXIN -->
    <text class="page-eyebrow">ACCOUNT</text>
    <text class="center-title">我的</text>
    <view class="profile-card panel">
      <view class="profile-avatar">{{ user ? user.name.slice(0, 1) : '我' }}</view>
      <view class="profile-copy">
        <text class="profile-name">{{ user ? user.name : '未登录' }}</text>
        <text class="profile-description">{{
          user?.preview
            ? '离线演示账号：记录只在当前页面保留，不连接真实账户或云端。'
            : user
              ? '新的识别和对话会保存到此账户。'
              : '登录后使用在线识别、AI 对话、资料和历史记录。'
        }}</text>
      </view>
      <view v-if="!user" class="profile-actions">
        <button class="button primary" @click="emit('login')">登录</button>
      </view>
      <text v-else class="profile-account">@{{ user.username }}</text>
    </view>
    <!-- #endif -->
    <!-- #ifdef MP-WEIXIN -->
    <view class="mini-profile-identity" :style="{ paddingRight: capsuleInset + 'px' }">
      <view class="mini-profile-avatar">
        <text v-if="user">{{ user.name.slice(0, 1) }}</text>
        <AppIcon v-else name="user" :size="24" />
      </view>
      <view v-if="user" class="mini-profile-copy">
        <text class="mini-profile-name">{{ user.name }}</text>
        <text class="mini-profile-status">{{
          user.preview ? '演示账号' : '@' + user.username
        }}</text>
      </view>
      <button
        v-else
        class="mini-profile-copy mini-profile-login"
        aria-label="登录"
        @click="emit('login')"
      >
        <text class="mini-profile-name">访客</text>
        <text class="mini-profile-status">点击登录</text>
      </button>
    </view>
    <!-- #endif -->
    <view class="panel profile-menu">
      <button @click="emit('settings')">
        <AppIcon name="settings" :size="22" />
        <view><text>设置</text><text>外观、记录与隐私、关于</text></view>
        <AppIcon name="right" :size="17" />
      </button>
      <button v-if="admin" @click="emit('admin')">
        <AppIcon name="shield" :size="22" />
        <view><text>管理员控制台</text><text>服务配置与模型状态</text></view>
        <AppIcon name="right" :size="17" />
      </button>
      <view class="profile-version">
        <text>宛田观叶</text><text>版本 {{ appVersion }}</text>
      </view>
    </view>
    <button v-if="user" class="button secondary profile-logout" @click="emit('logout')">
      <AppIcon name="logout" :size="19" /><text>退出登录</text>
    </button>
    <!-- #ifndef MP-WEIXIN -->
    <text class="profile-footnote">退出后，使用在线功能时需重新登录。</text>
    <!-- #endif -->
  </view>
</template>
<style scoped>
.user-center {
  max-width: 760px;
  margin: 5px auto 30px;
}
.page-eyebrow {
  font-size: 10px;
  letter-spacing: 2px;
  color: var(--muted);
}
.center-title {
  display: block;
  font-size: 28px;
  font-weight: 650;
  margin: 5px 0 24px;
}
.profile-card {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 26px;
  flex-wrap: wrap;
}
.profile-avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  border-radius: 23px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 27px;
  font-weight: 600;
}
.profile-copy {
  flex: 1;
  min-width: 180px;
}
.profile-name {
  display: block;
  font-size: 20px;
  font-weight: 600;
}
.profile-description {
  display: block;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.9;
  margin-top: 7px;
}
.profile-actions {
  display: flex;
  gap: 9px;
}
.profile-account {
  font-size: 12px;
  color: var(--muted);
}
.profile-menu {
  margin-top: 19px;
  padding: 5px 22px;
}
.profile-menu > button {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  text-align: left;
  padding: 20px 2px;
  border-bottom: 1px solid var(--line);
}
.profile-menu > button > view > text:first-child {
  display: block;
  font-size: 14px;
  font-weight: 550;
}
.profile-menu > button > view > text:last-child {
  display: block;
  font-size: 11px;
  color: var(--muted);
  margin-top: 4px;
}
.profile-menu > button > text {
  font-size: 24px;
  color: var(--muted);
}
.profile-version {
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px 14px;
  font-size: 11px;
  line-height: 1.5;
  padding: 14px 12px;
  color: var(--muted);
}
.profile-logout {
  width: 100%;
  margin-top: 22px;
}
.profile-footnote {
  display: block;
  font-size: 10px;
  text-align: center;
  color: var(--muted);
  margin-top: 13px;
}
@media (max-width: 760px) {
  .center-title {
    font-size: 25px;
  }
  .profile-card {
    padding: 21px;
    gap: 14px;
  }
  .profile-copy {
    min-width: 170px;
  }
  .profile-name {
    font-size: 18px;
  }
  .profile-actions {
    width: 100%;
    margin-top: 5px;
  }
  .profile-actions > .button {
    flex: 1;
  }
  .profile-menu {
    padding: 4px 19px;
  }
}
.profile-menu > button {
  gap: 14px;
  border-bottom: 0;
  border-radius: 12px;
  padding: 18px 12px;
  margin: 4px 0;
}
.profile-menu > button > view {
  flex: 1;
}
.profile-menu {
  padding: 7px;
}
.profile-logout {
  color: var(--danger);
  background: var(--danger-soft);
  border-color: transparent;
  min-height: 46px;
}
/* #ifdef MP-WEIXIN */
.user-center {
  width: 100%;
  min-width: 0;
  margin: 0 auto 24px;
}
.mini-profile-identity {
  display: flex;
  align-items: center;
  min-height: 54px;
  gap: 12px;
  margin-bottom: 18px;
}
.mini-profile-avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 44px;
  height: 44px;
  border-radius: 15px;
  background: var(--subtle);
  color: var(--ink);
  font-size: 19px;
  font-weight: 600;
}
.mini-profile-copy {
  flex: 1 1 auto;
  min-width: 0;
}
.mini-profile-login {
  min-height: 44px;
  padding: 4px 8px;
  margin-left: -8px;
  border-radius: 10px;
  text-align: left;
}
.mini-profile-login:active,
.profile-menu > button:active {
  background: var(--pressed);
}
.mini-profile-name,
.mini-profile-status {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mini-profile-name {
  color: var(--ink);
  font-size: 17px;
  font-weight: 640;
  line-height: 1.35;
}
.mini-profile-status {
  margin-top: 2px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.4;
}
.mini-profile-login .mini-profile-status {
  color: var(--accent);
}
.profile-menu {
  margin-top: 0;
}
/* #endif */
/* #ifdef H5 */
@media (max-width: 760px) {
  .page-eyebrow,
  .center-title {
    display: none;
  }
}
/* #endif */
</style>
