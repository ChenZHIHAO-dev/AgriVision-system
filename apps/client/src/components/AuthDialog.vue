<script setup lang="ts">
import { ref } from 'vue'
import UiDialog from './UiDialog.vue'
import { auth, type AuthSuccess } from '../lib/auth'
import { dataMode } from '../lib/api'
const props = withDefaults(defineProps<{ reason?: string; continueCaseId?: string }>(), {
  reason: '',
  continueCaseId: '',
})
const emit = defineEmits<{ close: []; success: [result: AuthSuccess] }>()
const preview = dataMode() === 'preview'
const focusTarget = ref('')
// H5 的焦点由浏览器管理，不把 @focus 再回绑成一次程序化聚焦。
let nativeAutoFocus = true
// #ifdef H5
nativeAutoFocus = false
// #endif
function blurField(field: string) {
  if (focusTarget.value === field) focusTarget.value = ''
}
function focusPassword() {
  focusTarget.value = 'auth-password'
  // #ifdef H5
  const field = document.getElementById('auth-password')
  const input =
    field instanceof HTMLInputElement ? field : field?.querySelector<HTMLInputElement>('input')
  input?.focus({ preventScroll: true })
  // #endif
}
const username = ref('')
const password = ref('')
const showPassword = ref(false)
const remember = ref(false)
const busy = ref(false)
const error = ref('')
const help = ref(false)
async function submit() {
  if (busy.value) return
  error.value = ''
  busy.value = true
  try {
    const result = await auth.login(
      username.value,
      password.value,
      remember.value,
      props.continueCaseId || undefined,
    )
    emit('success', result)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '操作未完成，请重试'
  } finally {
    busy.value = false
  }
}
function close() {
  if (!busy.value) emit('close')
}
async function usePreview() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    emit('success', await auth.previewLogin(props.continueCaseId || undefined))
  } catch (value) {
    error.value = value instanceof Error ? value.message : '演示登录未完成，请重试'
  } finally {
    busy.value = false
  }
}
</script>
<template>
  <UiDialog
    v-if="preview"
    title="离线预览登录"
    :subtitle="reason || '使用演示账号体验对话'"
    @close="close"
  >
    <view class="preview-account-note">
      <text class="muted">预览使用演示数据。刷新页面或退出后，本次照片和对话将清除。</text>
    </view>
    <view v-if="error" class="inline-alert danger-alert" role="alert">{{ error }}</view>
    <template #footer>
      <button class="button primary full-width auth-submit" :disabled="busy" @click="usePreview">
        {{ busy ? '正在接续…' : '使用演示账号' }}
      </button>
      <button class="text-button guest-link" :disabled="busy" @click="close">
        {{ continueCaseId ? '暂不登录，返回识别结果' : '暂不登录，返回页面' }}
      </button>
    </template>
  </UiDialog>
  <UiDialog
    v-else
    class="auth-dialog"
    :focus-target="focusTarget"
    title="管理员登录"
    :subtitle="reason || '当前测试版本仅开放管理员账号。'"
    @close="close"
  >
    <view v-if="error" class="inline-alert danger-alert" role="alert">{{ error }}</view>
    <view class="form-stack">
      <view class="form-field"
        ><text class="field-label">账号</text
        ><input
          v-model="username"
          id="auth-username"
          aria-label="账号"
          :focus="nativeAutoFocus && focusTarget === 'auth-username'"
          @focus="focusTarget = 'auth-username'"
          @blur="blurField('auth-username')"
          :adjust-position="false"
          :cursor-spacing="20"
          placeholder="请输入账号"
          :maxlength="24"
          autocomplete="username"
          confirm-type="next"
          @confirm="focusPassword"
      /></view>
      <view class="form-field"
        ><text class="field-label">密码</text
        ><view class="password-field"
          ><input
            v-model="password"
            id="auth-password"
            aria-label="密码"
            :focus="nativeAutoFocus && focusTarget === 'auth-password'"
            @focus="focusTarget = 'auth-password'"
            @blur="blurField('auth-password')"
            :adjust-position="false"
            :cursor-spacing="20"
            :password="!showPassword"
            placeholder="请输入密码"
            :maxlength="64"
            autocomplete="current-password"
            confirm-type="done"
            @confirm="submit"
          /><button
            class="password-toggle"
            :aria-label="showPassword ? '隐藏密码' : '显示密码'"
            @click="showPassword = !showPassword"
          >
            {{ showPassword ? '隐藏' : '显示' }}
          </button></view
        ></view
      >
    </view>
    <view class="auth-options"
      ><button class="check-button" :aria-pressed="remember" @click="remember = !remember">
        <text class="check-box" :class="{ checked: remember }">{{ remember ? '✓' : '' }}</text
        ><text>保持登录 7 天</text></button
      ><button class="text-button" @click="help = !help">忘记密码？</button></view
    >
    <view v-if="help" class="inline-alert">当前暂不提供短信或邮件找回，请联系管理员。</view>

    <text class="fine-print"
      >当前测试版本不开放注册，请使用管理员配置的账号。登录后的识别和对话会保存到该账户。</text
    >
    <template #footer
      ><button class="button primary full-width auth-submit" :disabled="busy" @click="submit">
        {{ busy ? '正在处理…' : '登录' }}</button
      ><button class="text-button guest-link" :disabled="busy" @click="close">
        {{ continueCaseId ? '暂不登录，返回识别结果' : '暂不登录，返回页面' }}
      </button></template
    >
  </UiDialog>
</template>

<style scoped>
/* #ifdef H5 */
@media (max-width: 760px) {
  /* 登录布局始终紧凑，不在 focus/blur 时切换高度，给小屏键盘留出输入区。 */
  .auth-dialog :deep(.dialog-heading) {
    padding: 12px 20px 8px;
  }
  .auth-dialog :deep(.dialog-title) {
    font-size: 20px;
  }
  .auth-dialog :deep(.dialog-body-inner) {
    padding: 0 20px 16px;
  }
  .auth-dialog :deep(.dialog-footer) {
    padding: 10px 20px;
  }
}
/* #endif */
.preview-account-note {
  line-height: 1.65;
}
.preview-account-note .muted {
  font-size: 13px;
}
</style>
