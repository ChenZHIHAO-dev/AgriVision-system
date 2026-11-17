<script setup lang="ts">
import { ref } from 'vue'
import UiDialog from './UiDialog.vue'
import { auth } from '../lib/auth'
const props = withDefaults(defineProps<{ initialMode?: 'login' | 'register'; reason?: string }>(), {
  initialMode: 'login',
  reason: '',
})
const emit = defineEmits<{ close: []; success: [] }>()
const mode = ref(props.initialMode)
const focusTarget = ref('')
const username = ref('')
const password = ref('')
const confirm = ref('')
const name = ref('')
const showPassword = ref(false)
const remember = ref(true)
const busy = ref(false)
const error = ref('')
const help = ref(false)
function changeMode() {
  mode.value = mode.value === 'login' ? 'register' : 'login'
  error.value = ''
  help.value = false
  password.value = ''
  confirm.value = ''
}
async function submit() {
  if (busy.value) return
  error.value = ''
  busy.value = true
  try {
    if (mode.value === 'register') {
      if (password.value !== confirm.value) throw new Error('两次输入的密码不一致')
      await auth.register(name.value, username.value, password.value)
    } else await auth.login(username.value, password.value, remember.value)
    emit('success')
  } catch (e) {
    error.value = e instanceof Error ? e.message : '操作未完成，请重试'
  } finally {
    busy.value = false
  }
}
</script>
<template>
  <UiDialog
    :focus-target="focusTarget"
    :title="mode === 'login' ? '欢迎回来 🌱' : '创建你的账户'"
    :subtitle="reason || '登录后，保存后续问诊，接着上次的咨询。'"
    @close="emit('close')"
  >
    <view class="auth-tabs segmented"
      ><button :class="{ active: mode === 'login' }" @click="mode !== 'login' && changeMode()">
        登录</button
      ><button
        :class="{ active: mode === 'register' }"
        @click="mode !== 'register' && changeMode()"
      >
        注册
      </button></view
    >
    <view v-if="error" class="inline-alert danger-alert" role="alert">{{ error }}</view>
    <view class="form-stack">
      <view v-if="mode === 'register'" class="form-field"
        ><text class="field-label">怎么称呼你</text
        ><input
          v-model="name"
          id="auth-name"
          aria-label="称呼"
          :focus="focusTarget === 'auth-name'"
          @focus="focusTarget = 'auth-name'"
          :adjust-position="false"
          :cursor-spacing="20"
          confirm-type="next"
          @confirm="focusTarget = 'auth-username'"
          placeholder="例如：王师傅"
          :maxlength="20"
          autocomplete="nickname"
      /></view>
      <view class="form-field"
        ><text class="field-label">账号</text
        ><input
          v-model="username"
          id="auth-username"
          aria-label="账号"
          :focus="focusTarget === 'auth-username'"
          @focus="focusTarget = 'auth-username'"
          :adjust-position="false"
          :cursor-spacing="20"
          placeholder="请输入账号"
          :maxlength="24"
          autocomplete="username"
          confirm-type="next"
          @confirm="focusTarget = 'auth-password'"
      /></view>
      <view class="form-field"
        ><text class="field-label">密码</text
        ><view class="password-field"
          ><input
            v-model="password"
            id="auth-password"
            aria-label="密码"
            :focus="focusTarget === 'auth-password'"
            @focus="focusTarget = 'auth-password'"
            :adjust-position="false"
            :cursor-spacing="20"
            :password="!showPassword"
            :placeholder="mode === 'register' ? '至少 6 位，请使用测试密码' : '请输入密码'"
            :maxlength="64"
            :autocomplete="mode === 'register' ? 'new-password' : 'current-password'"
            :confirm-type="mode === 'register' ? 'next' : 'done'"
            @confirm="mode === 'register' ? (focusTarget = 'auth-confirm') : submit()"
          /><button
            class="password-toggle"
            :aria-label="showPassword ? '隐藏密码' : '显示密码'"
            @click="showPassword = !showPassword"
          >
            {{ showPassword ? '隐藏' : '显示' }}
          </button></view
        ></view
      >
      <view v-if="mode === 'register'" class="form-field"
        ><text class="field-label">确认密码</text
        ><input
          v-model="confirm"
          id="auth-confirm"
          aria-label="确认密码"
          :focus="focusTarget === 'auth-confirm'"
          @focus="focusTarget = 'auth-confirm'"
          :adjust-position="false"
          :cursor-spacing="20"
          :password="!showPassword"
          placeholder="再输入一次密码"
          :maxlength="64"
          autocomplete="new-password"
          @confirm="submit"
      /></view>
    </view>
    <view v-if="mode === 'login'" class="auth-options"
      ><button class="check-button" :aria-pressed="remember" @click="remember = !remember">
        <text class="check-box" :class="{ checked: remember }">{{ remember ? '✓' : '' }}</text
        ><text>保持登录 7 天</text></button
      ><button class="text-button" @click="help = !help">忘记密码？</button></view
    >
    <view v-if="help" class="inline-alert">当前暂不提供短信或邮件找回，请联系管理员。</view>

    <text class="fine-print"
      >当前处于开发测试阶段，请使用测试信息。登录后新的问诊会保存到你的账户。</text
    >
    <template #footer
      ><button class="button primary full-width auth-submit" :disabled="busy" @click="submit">
        {{ busy ? '正在处理…' : mode === 'login' ? '登录' : '注册并登录' }}</button
      ><button class="text-button guest-link" @click="emit('close')">
        暂时不登录，继续使用
      </button></template
    >
  </UiDialog>
</template>
