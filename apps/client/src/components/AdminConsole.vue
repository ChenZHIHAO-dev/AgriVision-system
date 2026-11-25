<script setup lang="ts">
import UiDialog from './UiDialog.vue'
import type { Meta } from '../lib/api'
defineProps<{ base: string; meta: Meta | null; busy?: boolean }>()
const emit = defineEmits<{ close: []; refresh: [] }>()
</script>
<template>
  <UiDialog
    title="管理员控制台"
    subtitle="查看服务部署与模型状态。普通用户不展示这些配置。"
    @close="emit('close')"
    ><view class="admin-section"
      ><text class="admin-heading">服务器</text><text class="admin-address">{{ base }}</text
      ><text class="fine-print"
        >服务地址在部署配置中维护。对话密钥由服务器读取，不下发客户端。</text
      ></view
    ><view class="admin-section"
      ><text class="admin-heading">当前服务</text
      ><view class="settings-row"
        ><text>对话服务</text
        ><text class="muted">{{
          meta?.deepseek_configured ? 'DeepSeek 已配置' : '未配置'
        }}</text></view
      ><view v-for="model in meta?.models" :key="model.crop" class="admin-model"
        ><view
          ><text>{{ model.name }}</text
          ><text>{{
            model.ready ? '已接入' + (model.experimental ? ' · 实验模型' : '') : '暂未接入'
          }}</text></view
        ><text v-if="model.ready" class="fine-print"
          >{{ model.classes }} 类 · {{ model.version }}</text
        ></view
      ><text class="fine-print admin-note"
        >当前仅开放管理员登录。登录后的识别和对话记录由服务端按账户保存，游客的识别信息仅在当前会话暂存。</text
      ></view
    ><template #footer
      ><button class="button primary full-width" :disabled="busy" @click="emit('refresh')">
        重新检查服务状态
      </button></template
    ></UiDialog
  >
</template>
<style scoped>
.admin-section {
  padding: 5px 0 22px;
}
.admin-heading {
  font-size: 14px;
  font-weight: 600;
  display: block;
  margin-bottom: 13px;
}
.admin-address {
  display: block;
  overflow-wrap: anywhere;
  background: var(--subtle);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 11px 12px;
  font-size: 12px;
  margin-bottom: 10px;
}
.admin-model {
  border-top: 1px solid var(--line);
  padding: 12px 0;
}
.admin-model > view {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  font-size: 12px;
}
.admin-model > view > text:last-child {
  color: var(--muted);
}
.admin-model > .fine-print {
  margin-top: 6px;
}
.admin-note {
  padding-top: 15px;
  border-top: 1px solid var(--line);
}
</style>
