<script setup lang="ts">
import AppIcon from './AppIcon.vue'
import type { User } from '../lib/auth'
import { appVersion } from '../lib/appInfo'
defineProps<{ user: User | null; admin: boolean }>()
const emit = defineEmits<{
  login: []
  register: []
  settings: []
  admin: []
  logout: []
}>()
</script>
<template>
  <view class="user-center"
    ><text class="page-eyebrow">ACCOUNT</text><text class="center-title">我的</text
    ><view class="profile-card panel"
      ><view class="profile-avatar">{{ user ? user.name.slice(0, 1) : '我' }}</view
      ><view class="profile-copy"
        ><text class="profile-name">{{ user ? user.name : '未登录' }}</text
        ><text class="profile-description">{{
          user ? '新的问诊与咨询会保存到此账户。' : '访客会话不保存历史；登录后保存后续问诊。'
        }}</text></view
      ><view v-if="!user" class="profile-actions"
        ><button class="button primary" @click="emit('login')">登录</button
        ><button class="button secondary" @click="emit('register')">注册</button></view
      ><text v-else class="profile-account">@{{ user.username }}</text></view
    ><view class="panel profile-menu"
      ><button @click="emit('settings')">
        <AppIcon name="settings" :size="22" /><view
          ><text>设置</text><text>外观、记录与隐私、关于</text></view
        ><AppIcon name="right" :size="17" /></button
      ><button v-if="admin" @click="emit('admin')">
        <AppIcon name="shield" :size="22" /><view
          ><text>管理员控制台</text><text>服务配置与模型状态</text></view
        ><AppIcon name="right" :size="17" /></button
      ><view class="profile-version"
        ><text>AgriVision</text><text>{{ appVersion }}</text></view
      ></view
    ><button v-if="user" class="button secondary profile-logout" @click="emit('logout')">
      <AppIcon name="logout" :size="19" /><text>退出登录</text></button
    ><text class="profile-footnote">退出后仍可进行临时问诊和咨询。</text></view
  >
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
  font-size: 11px;
  padding: 18px 2px;
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
</style>
