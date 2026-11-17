<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import AppIcon from '../../components/AppIcon.vue'
import UiDialog from '../../components/UiDialog.vue'
import AuthDialog from '../../components/AuthDialog.vue'
import SelectField from '../../components/SelectField.vue'
import ChatComposer from '../../components/ChatComposer.vue'
import ScanProgress from '../../components/ScanProgress.vue'
import PhotoCapture from '../../components/PhotoCapture.vue'
import DashboardHome from '../../components/DashboardHome.vue'
import NavigationDock from '../../components/NavigationDock.vue'
import KnowledgeLibrary from '../../components/KnowledgeLibrary.vue'
import { createDraftStore } from '../../lib/drafts'
import ConversationHistory from '../../components/ConversationHistory.vue'
import ConversationDrawer from '../../components/ConversationDrawer.vue'
import PhotoSourceSheet from '../../components/PhotoSourceSheet.vue'
import UserCenter from '../../components/UserCenter.vue'
import UserSettings from '../../components/UserSettings.vue'
import AdminConsole from '../../components/AdminConsole.vue'
import MarkdownMessage from '../../components/MarkdownMessage.vue'
import RecognitionResult from '../../components/RecognitionResult.vue'
import RecognitionSummary from '../../components/RecognitionSummary.vue'
import { recognitionFor, imageQuestion } from '../../lib/recognition'
import { appVersion } from '../../lib/appInfo'
import {
  apiBase,
  dataMode,
  request,
  upload,
  imageUrl,
  type Crop,
  type Meta,
  type CaseRecord,
  type KnowledgeCard,
  type Source,
  type DataMode,
} from '../../lib/api'
import { crops, stages, regions, dateLabel, statusLabel } from '../../lib/options'
import { auth, user } from '../../lib/auth'
import { clearGuestRecords } from '../../lib/preview'
import { asset } from '../../lib/assets'
import { resolvedTheme, observeSystemTheme } from '../../lib/theme'
import type { ChatModel, DocumentAttachment, FollowUp } from '../../lib/api'

type Tab = 'home' | 'identify' | 'history' | 'knowledge' | 'profile' | 'settings'
const tab = ref<Tab>('identify'),
  crop = ref<Crop>('wheat'),
  stage = ref('不清楚'),
  note = ref(''),
  photo = ref('')
const meta = ref<Meta | null>(null),
  online = ref(false),
  refreshing = ref(false),
  busy = ref(false),
  busyText = ref(''),
  error = ref('')
const records = ref<CaseRecord[]>([]),
  cards = ref<KnowledgeCard[]>([]),
  current = ref<CaseRecord | null>(null)
const resultTab = ref<'advice' | 'chat'>('advice'),
  chatText = ref(''),
  sending = ref(false),
  pendingMessage = ref(''),
  scrollAnchor = ref('')
const retainedCase = ref<CaseRecord | null>(null)
const drafts = createDraftStore(),
  sidebarExpanded = ref(true)
const query = ref(''),
  filter = ref('all'),
  selectedCard = ref<KnowledgeCard | null>(null)
const adminOpen = ref(false),
  regionOpen = ref(false),
  editOpen = ref(false),
  infoOpen = ref(false),
  deleteTarget = ref<CaseRecord | null>(null)
const authOpen = ref(false),
  authMode = ref<'login' | 'register'>('login'),
  authReason = ref('')
const mode = ref<DataMode>(dataMode())
const location = ref(''),
  province = ref('河南省'),
  city = ref('南阳市'),
  district = ref('暂不填写区县'),
  customLocation = ref(''),
  useCustom = ref(false)
const editStage = ref('不清楚'),
  editLocation = ref(''),
  editNote = ref(''),
  keyboardHeight = ref(0)
const historyDrawerOpen = ref(false),
  photoSourceOpen = ref(false),
  photoTarget = ref<'identify' | 'chat' | 'supplement'>('identify')
const isAdmin = computed(() => user.value?.role === 'admin')
let viewportBaseline = 0,
  viewportWidth = 0,
  nativeWindowHeight = 0
const scanPhoto = ref('')
const toast = ref('')
let toastTimer: ReturnType<typeof setTimeout> | undefined
const chatModel = ref<ChatModel>(
  uni.getStorageSync('agrivision.chat.model') === 'deepseek-v4-pro'
    ? 'deepseek-v4-pro'
    : 'deepseek-flash',
)
const chatThinking = ref(Boolean(uni.getStorageSync('agrivision.chat.thinking')))
const chatWebSearch = ref(
  chatModel.value === 'deepseek-flash' && Boolean(uni.getStorageSync('agrivision.chat.webSearch')),
)
const pendingDocuments = ref<DocumentAttachment[]>([]),
  pendingImages = ref<string[]>([])
const photoDialogOpen = ref(false),
  chatPhoto = ref(''),
  photoCrop = ref<Crop>('wheat'),
  photoStage = ref('不清楚'),
  photoVariety = ref('')
watch(chatModel, (value) => uni.setStorageSync('agrivision.chat.model', value))
watch(chatThinking, (value) => uni.setStorageSync('agrivision.chat.thinking', value))
watch(chatWebSearch, (value) => uni.setStorageSync('agrivision.chat.webSearch', value))
watch(chatModel, (value) => {
  if (value !== 'deepseek-flash') chatWebSearch.value = false
})
const provinces = Object.keys(regions)
const cities = computed(() => Object.keys(regions[province.value] || {}))
const districts = computed(() => regions[province.value]?.[city.value] || ['暂不填写区县'])
const chatMode = computed(() => !!current.value && resultTab.value === 'chat')
const pendingImagePreviews = computed(
  () =>
    current.value?.images
      .filter((image) => pendingImages.value.includes(image.id))
      .map((image) => ({ id: image.id, url: imageUrl(current.value!, image.id) })) || [],
)
const contextNeeded = computed<FollowUp | null>(() => {
  if (!current.value?.crop)
    return {
      field: 'crop',
      prompt: '这次咨询哪种作物？',
      options: crops.map((item) => ({ value: item.id, label: item.name })),
    }
  if (!current.value.stage || current.value.stage === '不清楚')
    return {
      field: 'stage',
      prompt: '目前处于哪个生育期？',
      options: stages[current.value.crop]
        .filter((value) => value !== '不清楚')
        .map((value) => ({ value, label: value === '暂不确定' ? '暂不确定' : value })),
    }
  return null
})
const currentReceipt = computed(() => (current.value ? recognitionFor(current.value) : undefined))
const title = computed(() =>
  current.value
    ? chatMode.value
      ? current.value.crop
        ? current.value.crop_name + '咨询'
        : '新咨询'
      : '识别结果'
    : {
        home: '首页',
        identify: '拍照问诊',
        history: '问诊记录',
        knowledge: '植保知识',
        profile: '我的',
        settings: '设置',
      }[tab.value],
)
const filteredRecords = computed(() =>
  records.value.filter(
    (record) =>
      (filter.value === 'all' || record.crop === filter.value) &&
      (record.title + record.note + record.crop_name).includes(query.value.trim()),
  ),
)
const filteredCards = computed(() =>
  cards.value.filter(
    (card) =>
      (filter.value === 'all' || card.crop === filter.value || card.crop === 'general') &&
      (card.title + card.summary + card.keywords.join('')).includes(query.value.trim()),
  ),
)
const appStyle = computed(() => {
  // #ifndef H5
  const height = (nativeWindowHeight || uni.getSystemInfoSync().windowHeight) - keyboardHeight.value
  return keyboardHeight.value ? { height: height + 'px', '--app-height': height + 'px' } : {}
  // #endif
  // #ifdef H5
  return {}
  // #endif
})
let stopTheme: (() => void) | undefined
function nativeKeyboard(event: { height: number }) {
  keyboardHeight.value = event.height
  if (!event.height) nativeWindowHeight = uni.getSystemInfoSync().windowHeight
}
function resizedChat() {
  // #ifdef H5
  const visible = window.visualViewport?.height || window.innerHeight
  if (viewportWidth !== window.innerWidth) {
    viewportWidth = window.innerWidth
    viewportBaseline = visible
  }
  const editing = document.activeElement?.matches('input,textarea')
  if (!editing && !keyboardHeight.value) viewportBaseline = visible
  viewportBaseline = Math.max(viewportBaseline, visible)
  keyboardHeight.value =
    window.innerWidth <= 760 &&
    (editing || keyboardHeight.value > 0) &&
    viewportBaseline - visible > 110
      ? viewportBaseline - visible
      : 0
  document.documentElement.classList.toggle('keyboard-open', keyboardHeight.value > 0)
  if (chatMode.value) requestAnimationFrame(() => scrollChat())
  // #endif
}
onMounted(() => {
  stopTheme = observeSystemTheme()
  auth.restore().then(refresh)
  // #ifndef H5
  nativeWindowHeight = uni.getSystemInfoSync().windowHeight
  uni.onKeyboardHeightChange(nativeKeyboard)
  // #endif
  // #ifdef H5
  window.visualViewport?.addEventListener('resize', resizedChat)
  window.addEventListener('focusin', resizedChat)
  window.addEventListener('focusout', resizedChat)
  resizedChat()
  // #endif
})
onUnmounted(() => {
  stopTheme?.()
  clearTimeout(toastTimer)
  // #ifdef H5
  window.visualViewport?.removeEventListener('resize', resizedChat)
  window.removeEventListener('focusin', resizedChat)
  window.removeEventListener('focusout', resizedChat)
  document.documentElement.classList.remove('keyboard-open')
  // #endif
  // #ifndef H5
  uni.offKeyboardHeightChange(nativeKeyboard)
  // #endif
})
function showToast(text: string) {
  toast.value = text
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => {
    toast.value = ''
  }, 2600)
}
function showError(value: unknown) {
  error.value = value instanceof Error ? value.message : '操作未完成，请重试'
}
async function refresh() {
  refreshing.value = true
  try {
    const [system, history, knowledge] = await Promise.all([
      request<Meta>('/api/meta'),
      request<{ items: CaseRecord[] }>('/api/cases'),
      request<{ items: KnowledgeCard[] }>('/api/knowledge'),
    ])
    meta.value = system
    records.value = history.items
    cards.value = knowledge.items
    online.value = true
  } catch (value) {
    online.value = false
    showError(value)
  } finally {
    refreshing.value = false
  }
}
function navigate(value: Tab) {
  rememberDraft()
  if (current.value) retainedCase.value = current.value
  current.value = null
  tab.value = value
  filter.value = 'all'
  query.value = ''
  error.value = ''
}
function chooseCrop(value: Crop) {
  crop.value = value
  stage.value = '不清楚'
}
function openAuth(reason = '', initial: 'login' | 'register' = 'login') {
  authReason.value = reason
  authMode.value = initial
  authOpen.value = true
}
async function signedIn() {
  authOpen.value = false
  try {
    clearGuestRecords()
    drafts.clear()
    clearComposer()
    current.value = null
    retainedCase.value = null
    records.value = []
    navigate('profile')
    await refresh()
    showToast('已登录，后续问诊将保存到你的账户。')
  } catch (value) {
    showError(value)
  }
}
async function signOut() {
  await auth.logout()
  clearGuestRecords()
  drafts.clear()
  clearComposer()
  current.value = null
  retainedCase.value = null
  records.value = []
  navigate('profile')
  photo.value = ''
  note.value = ''
  await refresh()
  showToast('已退出登录，仍可继续使用识别与咨询')
}
function changeProvince(value: string) {
  province.value = value
  city.value = cities.value[0]
  district.value = '暂不填写区县'
}
function changeCity(value: string) {
  city.value = value
  district.value = '暂不填写区县'
}
function confirmRegion() {
  if (useCustom.value && !customLocation.value.trim()) {
    showToast('可补充种植地区')
    return
  }
  location.value = useCustom.value
    ? customLocation.value.trim()
    : [province.value, city.value, district.value === '暂不填写区县' ? '' : district.value]
        .filter(Boolean)
        .join(' / ')
  if (editOpen.value) editLocation.value = location.value
  regionOpen.value = false
}
function choosePhoto(source: 'album' | 'camera' = 'album', supplement = false) {
  uni.chooseImage({
    count: 1,
    sizeType: ['compressed'],
    sourceType: [source],
    success: async (result) => {
      const files = result.tempFiles as { size: number }[]
      if (files?.[0]?.size > 8 * 1024 * 1024) {
        showToast('图片不能超过 8MB，请压缩后重试')
        return
      }
      if (supplement) await addPhoto(result.tempFilePaths[0])
      else {
        photo.value = result.tempFilePaths[0]
        error.value = ''
        await startCase()
      }
    },
    fail: (value) => {
      if (!value.errMsg?.includes('cancel')) showToast('未能打开相册或相机，请检查权限后重试')
    },
  })
}
async function startCase() {
  if (!photo.value || busy.value) return
  rememberDraft()
  scanPhoto.value = photo.value
  busy.value = true
  busyText.value = mode.value === 'preview' ? '正在保存本次观察…' : '正在上传并处理问诊…'
  error.value = ''
  try {
    current.value = await upload('/api/cases', photo.value, { crop: crop.value })
    clearComposer()
    resultTab.value = 'advice'
    photo.value = ''
    note.value = ''
    await refresh()
  } catch (value) {
    showError(value)
  } finally {
    busy.value = false
    scanPhoto.value = ''
  }
}
async function demo() {
  if (busy.value) return
  busy.value = true
  busyText.value = '正在打开演示样例…'
  error.value = ''
  try {
    current.value = await request<CaseRecord>('/api/cases/demo', 'POST', { crop: crop.value })
    resultTab.value = 'advice'
    await refresh()
  } catch (value) {
    showError(value)
  } finally {
    busy.value = false
  }
}
async function openCase(id: string) {
  rememberDraft()
  busy.value = true
  busyText.value = '正在读取记录…'
  error.value = ''
  try {
    current.value = await request<CaseRecord>('/api/cases/' + id)
    restoreComposer()
    resultTab.value =
      current.value.messages.length || !current.value.images.length ? 'chat' : 'advice'
  } catch (value) {
    showError(value)
  } finally {
    busy.value = false
  }
}
async function retryRecognition() {
  if (!current.value || busy.value) return
  busy.value = true
  busyText.value = '正在重新识别照片…'
  error.value = ''
  try {
    current.value = await request<CaseRecord>(
      '/api/cases/' + current.value.id + '/retry',
      'POST',
      {},
    )
    await refresh()
    showToast('逐张识别结果已更新')
  } catch (value) {
    showError(value)
  } finally {
    busy.value = false
  }
}
async function addPhoto(path: string) {
  if (!current.value || busy.value) return
  scanPhoto.value = path
  busy.value = true
  busyText.value = '正在保存补充照片…'
  try {
    current.value = await upload(`/api/cases/${current.value.id}/images`, path, {})
    await refresh()
    showToast('补充照片已保存')
  } catch (value) {
    showError(value)
  } finally {
    busy.value = false
    scanPhoto.value = ''
  }
}
async function scrollChat() {
  scrollAnchor.value = ''
  await nextTick()
  scrollAnchor.value = 'chat-end'
}
function openChat() {
  resultTab.value = 'chat'
  scrollChat()
}
async function startConsultation(selectedCrop: Crop | null = null) {
  if (busy.value) return
  rememberDraft()
  busy.value = true
  busyText.value = '正在建立咨询…'
  error.value = ''
  try {
    current.value = await request<CaseRecord>('/api/consultations', 'POST', {
      crop: selectedCrop,
      location: location.value,
      stage: '不清楚',
    })
    clearComposer()
    resultTab.value = 'chat'
    chatText.value = ''
    pendingDocuments.value = []
    pendingImages.value = []
    await refresh()
    scrollChat()
  } catch (value) {
    showError(value)
  } finally {
    busy.value = false
  }
}
async function chooseContext(value: FollowUp, choice: { value: string; label: string }) {
  if (!current.value || sending.value) return
  try {
    current.value = await request<CaseRecord>(
      '/api/cases/' + current.value.id + '/context',
      'POST',
      { [value.field]: choice.value },
    )
    showToast(
      value.field === 'crop'
        ? '作物已更新，请继续补充信息。'
        : '生育期已更新，发送问题后生成建议。',
    )
  } catch (value) {
    showError(value)
  }
}
function chooseChatPhoto(source: 'album' | 'camera' = 'album') {
  uni.chooseImage({
    count: 1,
    sizeType: ['compressed'],
    sourceType: [source],
    success: (result) => {
      if ((result.tempFiles as { size: number }[])[0]?.size > 8 * 1024 * 1024) {
        showToast('图片不能超过 8MB')
        return
      }
      chatPhoto.value = result.tempFilePaths[0]
      photoCrop.value = current.value?.crop || crop.value
      photoStage.value = current.value?.stage || '不清楚'
      photoVariety.value = current.value?.variety || ''
      if (current.value?.crop) {
        confirmChatPhoto()
      } else {
        photoDialogOpen.value = true
      }
    },
    fail: (error) => {
      if (!error.errMsg?.includes('cancel')) showToast('未能打开图片选择，请检查权限')
    },
  })
}
async function confirmChatPhoto() {
  if (!chatPhoto.value || busy.value) return
  if (!current.value || current.value.is_demo) await startConsultation(photoCrop.value)
  if (!current.value) return
  scanPhoto.value = chatPhoto.value
  busy.value = true
  busyText.value = '正在调用图片识别模型…'
  error.value = ''
  try {
    current.value = await upload(`/api/cases/${current.value.id}/images`, chatPhoto.value, {
      crop: photoCrop.value,
      stage: photoStage.value,
      variety: photoVariety.value,
    })
    pendingImages.value = [
      ...new Set([
        ...pendingImages.value,
        current.value.images[current.value.images.length - 1].id,
      ]),
    ]
    photoDialogOpen.value = false
    chatPhoto.value = ''
    resultTab.value = 'chat'
    await refresh()
  } catch (value) {
    showError(value)
    return
  } finally {
    busy.value = false
    scanPhoto.value = ''
  }
  showToast('照片已处理，可继续添加或发送咨询。')
}
async function acceptDocument(path: string, name: string, size: number) {
  if (size > 8 * 1024 * 1024) {
    showToast('文件不能超过 8MB')
    return
  }
  if (!current.value) await startConsultation()
  if (!current.value) return
  busy.value = true
  busyText.value = '正在读取资料文字…'
  error.value = ''
  try {
    const previous = new Set((current.value.documents || []).map((file) => file.id))
    current.value = await upload(`/api/cases/${current.value.id}/attachments`, path, {
      filename: name,
    })
    pendingDocuments.value.push(
      ...(current.value.documents || []).filter((file) => !previous.has(file.id)),
    )
    resultTab.value = 'chat'
    showToast('资料已添加，可继续提问')
    await refresh()
  } catch (value) {
    showError(value)
  } finally {
    busy.value = false
  }
}
function chooseDocument() {
  // #ifdef H5
  uni.chooseFile({
    count: 1,
    type: 'all',
    extension: ['.txt', '.md', '.pdf', '.docx'],
    success: (result) => {
      const file = (
        Array.isArray(result.tempFiles) ? result.tempFiles[0] : result.tempFiles
      ) as File & { path?: string }
      const path = file.path || (file instanceof File ? URL.createObjectURL(file) : '')
      if (path) acceptDocument(path, file.name, file.size)
      else showToast('资料文件未能读取，请重新选择')
    },
  })
  // #endif
  // #ifndef H5
  uni.chooseMessageFile({
    count: 1,
    type: 'file',
    extension: ['txt', 'md', 'pdf', 'docx'],
    success: (result) => {
      const file = result.tempFiles[0]
      acceptDocument(file.path, file.name, file.size)
    },
  })
  // #endif
}
async function removeAttachment(id: string) {
  if (!current.value) return
  try {
    await request(`/api/cases/${current.value.id}/attachments/${id}`, 'DELETE')
    pendingDocuments.value = pendingDocuments.value.filter((file) => file.id !== id)
    current.value = await request(`/api/cases/${current.value.id}`)
  } catch (value) {
    showError(value)
  }
}
async function removePendingImage(id: string) {
  if (!current.value || busy.value) return
  busy.value = true
  try {
    current.value = await request<CaseRecord>(
      '/api/cases/' + current.value.id + '/images/' + id,
      'DELETE',
    )
    pendingImages.value = pendingImages.value.filter((value) => value !== id)
    await refresh()
  } catch (value) {
    showError(value)
  } finally {
    busy.value = false
  }
}
function rememberDraft() {
  if (current.value)
    drafts.save(current.value.id, {
      text: chatText.value,
      documents: pendingDocuments.value.map((file) => file.id),
      images: pendingImages.value,
    })
}
function restoreComposer() {
  clearComposer()
  if (!current.value) return
  const draft = drafts.get(current.value.id)
  chatText.value = draft.text
  pendingDocuments.value = (current.value.documents || []).filter((file) =>
    draft.documents.includes(file.id),
  )
  pendingImages.value = current.value.images
    .filter((image) => draft.images.includes(image.id))
    .map((image) => image.id)
}
function navigateFromDrawer(value: Tab) {
  historyDrawerOpen.value = false
  navigate(value)
}
function toggleNavigation() {
  if (uni.getSystemInfoSync().windowWidth <= 760) historyDrawerOpen.value = true
  else sidebarExpanded.value = !sidebarExpanded.value
}
function clearComposer() {
  chatText.value = ''
  pendingDocuments.value = []
  pendingImages.value = []
}
function attach(kind: 'image' | 'document') {
  if (kind === 'image') openPhotoSources('chat')
  else chooseDocument()
}
async function sendMessage(raw = chatText.value) {
  if (
    !current.value ||
    sending.value ||
    (!raw.trim() && !pendingDocuments.value.length && !pendingImages.value.length)
  )
    return
  const text =
      raw.trim() ||
      (pendingImages.value.length
        ? imageQuestion(current.value) +
          (pendingDocuments.value.length ? '请同时结合刚添加的资料回答。' : '')
        : '请阅读刚添加的资料，提取与本次作物咨询相关的信息。'),
    id = current.value.id
  const sentDraft = raw === chatText.value
  sending.value = true
  pendingMessage.value = text
  if (sentDraft) chatText.value = ''
  error.value = ''
  scrollChat()
  try {
    await request(`/api/cases/${id}/messages`, 'POST', {
      text,
      model: chatModel.value,
      thinking: chatThinking.value,
      web_search: chatWebSearch.value,
      attachment_ids: pendingDocuments.value.map((file) => file.id),
      image_ids: pendingImages.value,
    })
    const updated = await request<CaseRecord>(`/api/cases/${id}`)
    if (current.value?.id === id) {
      current.value = updated
      pendingDocuments.value = []
      pendingImages.value = []
    }
    await refresh()
  } catch (value) {
    if (current.value?.id === id && sentDraft && !chatText.value) chatText.value = raw
    showError(value)
  } finally {
    sending.value = false
    pendingMessage.value = ''
    scrollChat()
  }
}
function editCase() {
  if (!current.value) return
  infoOpen.value = false
  editStage.value = current.value.stage
  editLocation.value = current.value.location
  editNote.value = current.value.note
  editOpen.value = true
}
async function saveCase() {
  if (!current.value) return
  busy.value = true
  try {
    current.value = await request(`/api/cases/${current.value.id}/context`, 'POST', {
      stage: editStage.value,
      location: editLocation.value.trim(),
      note: editNote.value,
    })
    editOpen.value = false
    await refresh()
    showToast('种植情况已更新')
  } catch (value) {
    showError(value)
  } finally {
    busy.value = false
  }
}
async function confirmDelete() {
  if (!deleteTarget.value) return
  busy.value = true
  try {
    const id = deleteTarget.value.id
    await request(`/api/cases/${id}`, 'DELETE')
    if (current.value?.id === id) current.value = null
    deleteTarget.value = null
    await refresh()
    showToast('问诊记录已删除')
  } catch (value) {
    showError(value)
  } finally {
    busy.value = false
  }
}
function openSource(source: Source) {
  // #ifdef H5
  window.open(source.url, '_blank', 'noopener,noreferrer')
  return
  // #endif
  // #ifndef H5
  uni.setClipboardData({ data: source.url })
  showToast('资料链接已复制')
  // #endif
}
function viewPhoto(id?: string) {
  if (current.value)
    uni.previewImage({
      urls: current.value.images.length
        ? current.value.images.map((image) => imageUrl(current.value!, image.id))
        : [imageUrl(current.value)],
      current: imageUrl(current.value, id),
    })
}
function copyText(text: string) {
  uni.setClipboardData({ data: text, showToast: false, success: () => showToast('回答已复制') })
}
function identifyFromKnowledge() {
  selectedCard.value = null
  navigate('identify')
}
function openSettings() {
  navigate('settings')
}
async function openAdmin() {
  if (!isAdmin.value) return
  adminOpen.value = true
  if (mode.value === 'live')
    try {
      await request('/api/admin/status')
    } catch (value) {
      adminOpen.value = false
      showError(value)
    }
}
async function refreshAdmin() {
  if (!isAdmin.value) return
  try {
    await request('/api/admin/status')
    await refresh()
    showToast('服务状态已更新')
  } catch (value) {
    showError(value)
  }
}
async function openConversation(id: string) {
  historyDrawerOpen.value = false
  await openCase(id)
  if (chatMode.value) scrollChat()
}
async function openConsultation() {
  if (current.value) {
    openChat()
    return
  }
  const previous =
    retainedCase.value?.id || records.value.find((record) => record.messages.length)?.id
  if (previous) {
    try {
      current.value = await request<CaseRecord>('/api/cases/' + previous)
      restoreComposer()
      openChat()
      return
    } catch {
      retainedCase.value = null
    }
  }
  await startConsultation()
}
function openPhotoSources(target: 'identify' | 'chat' | 'supplement' = 'identify') {
  if (busy.value) return
  photoTarget.value = target
  photoSourceOpen.value = true
}
function pickPhoto(source: 'album' | 'camera') {
  photoSourceOpen.value = false
  if (photoTarget.value === 'chat') chooseChatPhoto(source)
  else choosePhoto(source, photoTarget.value === 'supplement')
}
function loginFromDrawer() {
  historyDrawerOpen.value = false
  openAuth('登录后，后续咨询会保存到你的账户。')
}
function newFromDrawer() {
  historyDrawerOpen.value = false
  startConsultation()
}
</script>

<template>
  <view
    class="av-app"
    :class="[
      'theme-' + resolvedTheme,
      {
        'is-chat': chatMode,
        'keyboard-open': keyboardHeight > 0,
        'nav-collapsed': !sidebarExpanded,
      },
    ]"
    :style="appStyle"
  >
    <view class="sidebar">
      <button class="brand" @click="navigate('home')">
        <view class="brand-mark"><AppIcon name="leaf" :size="27" white /></view
        ><view
          ><text class="brand-name">AgriVision</text
          ><text class="brand-caption">宛农植保助手</text></view
        >
      </button>
      <text class="nav-caption">工作台</text>
      <button
        class="nav-item"
        :class="{ active: tab === 'home' && !current }"
        @click="navigate('home')"
      >
        <AppIcon name="home" /><text>首页</text>
      </button>
      <button class="nav-item" :class="{ active: chatMode }" @click="openConsultation">
        <AppIcon name="chat" /><text>咨询</text>
      </button>
      <button
        class="nav-item"
        :class="{ active: (tab === 'identify' && !current) || (current && !chatMode) }"
        @click="navigate('identify')"
      >
        <AppIcon name="camera" /><text>拍照识别</text>
      </button>
      <button
        class="nav-item"
        :class="{ active: ['profile', 'settings', 'knowledge'].includes(tab) && !current }"
        @click="navigate('profile')"
      >
        <text class="nav-user-avatar">{{ user?.name.slice(0, 1) || '我' }}</text
        ><text>我的</text>
      </button>
      <ConversationHistory
        :records="records"
        :user="user"
        :selected="current?.id"
        @open="openConversation"
        @new="startConsultation()"
        @login="openAuth('登录后，后续咨询会保存到你的账户。')"
      />
      <view class="sidebar-bottom"
        ><button class="nav-settings" @click="openSettings">
          <AppIcon name="settings" :size="18" /><text>设置</text></button
        ><text class="fine-print">AgriVision · {{ appVersion }}</text></view
      >
    </view>

    <view class="main-shell">
      <view class="topbar">
        <button
          class="icon-button navigation-toggle"
          aria-label="打开导航与问诊记录"
          @click="toggleNavigation"
        >
          ☰
        </button>
        <view class="breadcrumb"
          ><button class="desktop-only breadcrumb-home" @click="navigate('home')">工作台</button
          ><text class="desktop-only crumb-divider">/</text
          ><text class="topbar-title">{{ title }}</text></view
        >
        <view class="topbar-actions"
          ><button
            v-if="chatMode && current?.images.length"
            class="header-result-link"
            @click="resultTab = 'advice'"
          >
            识别结果</button
          ><button
            v-if="chatMode"
            class="icon-button"
            aria-label="问诊信息"
            @click="infoOpen = true"
          >
            <AppIcon name="info" :size="18" /></button
          ><button v-if="!user" class="login-button" @click="openAuth()">
            登录<text class="desktop-only"> / 注册</text></button
          ><button v-else class="account-button" aria-label="用户中心" @click="navigate('profile')">
            <text class="avatar">{{ user.name.slice(0, 1).toUpperCase() }}</text
            ><text class="account-name">{{ user.name }}</text>
          </button></view
        >
      </view>
      <view v-if="error" class="error-strip" role="alert"
        ><text class="flex-one">{{ error }}</text
        ><button v-if="!online" class="text-button" @click="refresh">重试</button
        ><button class="icon-button" aria-label="关闭提示" @click="error = ''">×</button></view
      >
      <view v-if="busy" class="loading-strip" role="status"
        ><view class="spinner" /><text>{{ busyText || '正在保存…' }}</text></view
      >

      <view class="workspace">
        <view v-if="current" class="case-area">
          <view v-if="!chatMode" class="case-toolbar">
            <button
              class="case-back icon-button"
              aria-label="返回拍照问诊"
              @click="navigate('identify')"
            >
              ←
            </button>
            <view class="case-heading flex-one"
              ><text class="strong">{{ current.crop_name }}</text
              ><text v-if="current.location" class="muted">{{ current.location }}</text></view
            >
            <button class="icon-button" aria-label="查看问诊资料" @click="infoOpen = true">
              <AppIcon name="info" :size="20" />
            </button>
          </view>

          <view v-if="chatMode" class="chat-workspace">
            <view v-if="mode === 'preview'" class="chat-mode-note"
              ><text>🌱 当前提供植保资料参考，智能服务暂未连接</text
              ><button v-if="!user" @click="openAuth('登录后，新的问诊与咨询会保存到你的账户。')">
                登录保存
              </button></view
            >
            <scroll-view
              scroll-y
              class="message-scroll"
              :scroll-into-view="scrollAnchor"
              :scroll-with-animation="true"
            >
              <view class="message-stream">
                <RecognitionSummary
                  v-if="
                    currentReceipt?.image_received &&
                    (!current.messages.length || pendingImages.length)
                  "
                  :result="currentReceipt"
                  compact
                />
                <view v-if="!current.messages.length && !sending" class="chat-welcome"
                  ><view class="welcome-mark">🌱</view
                  ><text class="welcome-title">这次田间观察，我们一起看看</text
                  ><text class="muted"
                    >可以补充症状出现的时间、范围和近期用药情况，或从下面的问题开始。</text
                  ><view class="welcome-topics"
                    ><button
                      v-for="text in [
                        '还需要补充什么信息？',
                        '如何拍清楚症状？',
                        '用药前需要核对什么？',
                      ]"
                      :key="text"
                      @click="sendMessage(text)"
                    >
                      {{ text }} <text>↗</text>
                    </button></view
                  ></view
                >
                <view
                  v-for="(message, index) in current.messages"
                  :key="index"
                  class="message-row"
                  :class="message.role"
                >
                  <view v-if="message.role === 'assistant'" class="assistant-avatar">🌱</view>
                  <view class="message-content"
                    ><text v-if="message.role === 'assistant'" class="message-author"
                      >宛农助手
                      <text>{{
                        message.provider === 'deepseek'
                          ? (message.model === 'deepseek-v4-pro'
                              ? 'DeepSeek V4 Pro'
                              : 'DeepSeek Flash') + (message.thinking ? ' · 深度思考' : '')
                          : message.provider === 'recognition'
                            ? '识别摘要'
                            : message.provider === 'clarification'
                              ? '信息补充'
                              : '资料参考'
                      }}</text></text
                    ><text v-if="message.web_search_used" class="web-used-label"
                      >↗ 已联网检索 · 来源见回答下方</text
                    ><RecognitionSummary
                      v-if="
                        message.role === 'assistant' &&
                        message.recognition &&
                        !['recognition', 'clarification'].includes(message.provider)
                      "
                      :result="message.recognition"
                      compact
                    /><MarkdownMessage
                      v-if="message.role === 'assistant'"
                      :content="message.text"
                    /><text v-else class="message-bubble" :selectable="true">{{
                      message.text
                    }}</text
                    ><view v-if="message.attachments?.length" class="message-attachments"
                      ><template v-for="file in message.attachments" :key="file.id"
                        ><button
                          v-if="file.kind === 'image'"
                          class="message-image"
                          :aria-label="'查看' + file.name"
                          @click="viewPhoto(file.id)"
                        >
                          <image :src="imageUrl(current, file.id)" mode="aspectFill" /></button
                        ><text v-else class="message-file">▤ {{ file.name }}</text></template
                      ></view
                    ><view
                      v-if="
                        index === current.messages.length - 1 &&
                        message.provider === 'clarification' &&
                        contextNeeded
                      "
                      class="context-choice"
                      ><text class="context-prompt">{{ contextNeeded!.prompt }}</text
                      ><view class="context-options"
                        ><button
                          v-for="choice in contextNeeded!.options"
                          :key="choice.value"
                          :disabled="sending"
                          @click="chooseContext(contextNeeded!, choice)"
                        >
                          {{ choice.label }}
                        </button></view
                      ></view
                    ><button
                      v-if="
                        index === current.messages.length - 1 &&
                        message.provider === 'clarification' &&
                        !contextNeeded
                      "
                      class="button secondary continue-question"
                      :disabled="sending"
                      @click="sendMessage('基础信息已补充，请回答刚才的问题。')"
                    >
                      继续回答 ↗
                    </button>
                    <view
                      v-if="message.role === 'assistant' && message.provider !== 'clarification'"
                      class="message-tools"
                      ><button
                        v-for="source in message.sources"
                        :key="source.url"
                        class="source-chip"
                        @click="openSource(source)"
                      >
                        ↗ {{ source.title }}</button
                      ><button
                        class="copy-button"
                        aria-label="复制回答"
                        @click="copyText(message.text)"
                      >
                        复制
                      </button></view
                    ><text v-if="message.notice" class="fine-print">{{
                      message.notice
                    }}</text></view
                  >
                </view>
                <view v-if="sending" class="message-row user"
                  ><text class="message-bubble pending-bubble">{{ pendingMessage }}</text></view
                >
                <view v-if="sending" class="responding"
                  ><view class="spinner" /><text>正在整理资料…</text></view
                >
                <view id="chat-end" class="chat-end" />
              </view>
            </scroll-view>
            <view class="composer-dock"
              ><view class="composer-wrap"
                ><ChatComposer
                  v-model="chatText"
                  v-model:model="chatModel"
                  v-model:thinking="chatThinking"
                  v-model:web-search="chatWebSearch"
                  :attachments="pendingDocuments"
                  :images="pendingImagePreviews"
                  :disabled="sending || busy"
                  :preview="mode === 'preview'"
                  @send="sendMessage()"
                  @attach="attach"
                  @remove="removeAttachment"
                  @remove-image="removePendingImage"
                  @resize="resizedChat"
                  @limit="showToast('单条消息最多 12000 字，较长资料可作为文件上传')"
                  @keyboard="keyboardHeight = $event" /></view
            ></view>
          </view>

          <scroll-view v-else scroll-y class="page-scroll"
            ><RecognitionResult
              :record="current"
              :receipt="currentReceipt"
              :busy="busy"
              @photo="viewPhoto"
              @source="openSource"
              @edit="editCase"
              @retry="retryRecognition"
          /></scroll-view>
          <view v-if="!chatMode" class="result-actions"
            ><button
              v-if="!current.is_demo"
              class="button secondary"
              :disabled="busy || current.images.length >= 6"
              @click="openPhotoSources('supplement')"
            >
              补充照片</button
            ><button class="button primary" @click="openChat">
              <AppIcon name="chat" white :size="18" /><text>继续对话</text>
            </button></view
          >
        </view>

        <scroll-view v-else scroll-y class="page-scroll">
          <view class="page-content">
            <template v-if="tab === 'home'"
              ><DashboardHome
                :records="records"
                :logged-in="!!user"
                @capture="navigate('identify')"
                @open="openCase"
                @history="navigate('history')"
                @login="openAuth('登录后，后续问诊会保存到你的账户。')"
            /></template>
            <template v-else-if="tab === 'identify'"
              ><PhotoCapture
                :crop="crop"
                :models="meta?.models || []"
                :busy="busy"
                :loading="refreshing || !meta"
                @crop="chooseCrop"
                @capture="choosePhoto"
                @resume="openConsultation"
            /></template>

            <template v-else-if="tab === 'history'">
              <view class="page-heading"
                ><view
                  ><text class="eyebrow">FIELD NOTES</text
                  ><text class="page-title">把田间变化，记录下来</text
                  ><text class="muted">{{
                    user
                      ? '照片、建议和对话，都在同一条记录里。'
                      : '登录后，随时回看上次的问诊与咨询。'
                  }}</text></view
                ><button v-if="user" class="button primary" @click="navigate('identify')">
                  ＋ 新建问诊
                </button></view
              >
              <view v-if="!user" class="panel empty-state login-empty"
                ><view class="empty-icon">🌾</view
                ><text class="section-title">登录，让观察有迹可循</text
                ><text class="muted"
                  >保存症状照片和咨询记录，下次不用重新说起。未登录也可以继续识别问诊、咨询和浏览知识。</text
                ><button
                  class="button primary"
                  @click="openAuth('登录后，即可保存并查看你的问诊记录。')"
                >
                  登录 / 注册</button
                ><button class="text-button" @click="navigate('identify')">
                  先去问一问 →
                </button></view
              >
              <view v-else class="panel history-panel"
                ><view class="list-toolbar"
                  ><view class="filter-tabs"
                    ><button :class="{ active: filter === 'all' }" @click="filter = 'all'">
                      全部</button
                    ><button
                      v-for="option in crops"
                      :key="option.id"
                      :class="{ active: filter === option.id }"
                      @click="filter = option.id"
                    >
                      {{ option.name }}
                    </button></view
                  ><view class="search-field"
                    ><AppIcon name="search" :size="18" /><input
                      v-model="query"
                      aria-label="搜索问诊记录"
                      placeholder="搜索作物、症状或备注" /></view></view
                ><view v-if="!filteredRecords.length" class="empty-state"
                  ><view class="empty-icon">🌱</view
                  ><text class="section-title">{{
                    records.length ? '没有匹配的记录' : '从第一次田间观察开始'
                  }}</text
                  ><text class="muted">{{
                    records.length
                      ? '试试其他关键词，或切换作物筛选。'
                      : '上传一张照片，或先体验一条演示问诊。'
                  }}</text
                  ><button v-if="!records.length" class="button soft" @click="demo">
                    体验演示问诊 ↗
                  </button></view
                ><view v-for="record in filteredRecords" :key="record.id" class="history-row"
                  ><button class="history-main" @click="openCase(record.id)">
                    <image :src="imageUrl(record)" mode="aspectFill" /><view class="flex-one"
                      ><text class="history-title">{{ record.title }}</text
                      ><text class="muted small"
                        >{{ record.crop_name }} · {{ dateLabel(record.updated_at) }}</text
                      ></view
                    ><text class="badge">{{ statusLabel(record.status) }}</text></button
                  ><button
                    class="icon-button"
                    aria-label="删除问诊记录"
                    @click="deleteTarget = record"
                  >
                    <AppIcon name="trash" :size="18" /></button></view
              ></view>
            </template>

            <template v-else-if="tab === 'profile'"
              ><UserCenter
                :user="user"
                :admin="isAdmin"
                @login="openAuth()"
                @register="openAuth('', 'register')"
                @settings="openSettings"
                @resources="navigate('knowledge')"
                @admin="openAdmin"
                @logout="signOut"
            /></template>
            <template v-else-if="tab === 'settings'"
              ><UserSettings @back="navigate('profile')"
            /></template>
            <template v-else
              ><KnowledgeLibrary :cards="cards" @open="selectedCard = $event" @source="openSource"
            /></template>
          </view>
        </scroll-view>
      </view>
      <NavigationDock
        :active="chatMode ? 'chat' : tab"
        :keyboard-open="keyboardHeight > 0"
        @navigate="navigate"
      />
    </view>

    <ScanProgress v-if="busy && scanPhoto" :src="scanPhoto" />
    <ConversationDrawer
      v-if="historyDrawerOpen"
      :records="records"
      :user="user"
      :selected="current?.id"
      @close="historyDrawerOpen = false"
      @navigate="navigateFromDrawer"
      @open="openConversation"
      @new="newFromDrawer"
      @login="loginFromDrawer"
    />
    <PhotoSourceSheet
      :crop="crop"
      :allow-crop="photoTarget === 'identify'"
      @crop="chooseCrop"
      v-if="photoSourceOpen"
      @close="photoSourceOpen = false"
      @choose="pickPhoto"
    />
    <view v-if="toast" class="toast" role="status">{{ toast }}</view>
    <AuthDialog
      v-if="authOpen"
      :initial-mode="authMode"
      :reason="authReason"
      @close="authOpen = false"
      @success="signedIn"
    />

    <UiDialog
      v-if="photoDialogOpen"
      title="照片中的作物是什么？"
      subtitle="选择作物后立即识别，生育期和地区可在咨询时补充。"
      @close="photoDialogOpen = false"
      ><image :src="chatPhoto" mode="aspectFit" class="chat-photo-preview" /><view
        class="photo-crop-choices"
        ><button
          v-for="option in crops"
          :key="option.id"
          :class="{ active: photoCrop === option.id }"
          @click="photoCrop = option.id"
        >
          {{ option.name }}
        </button></view
      ><text class="fine-print">请添加同种作物、同次田间观察的照片。原图不发送给对话模型。</text
      ><template #footer
        ><button class="button primary full-width" :disabled="busy" @click="confirmChatPhoto">
          识别并继续咨询
        </button></template
      ></UiDialog
    >
    <UiDialog
      v-if="selectedCard"
      :title="selectedCard.title"
      :subtitle="selectedCard.category"
      wide
      @close="selectedCard = null"
      ><text class="article-summary">{{ selectedCard.summary }}</text
      ><text class="section-title">建议检查与补充</text
      ><view v-for="(action, index) in selectedCard.actions" :key="action" class="action-row"
        ><text class="action-index">{{ index + 1 }}</text
        ><text>{{ action }}</text></view
      ><template v-if="selectedCard.sources.length"
        ><text class="section-title">资料来源</text
        ><button
          v-for="source in selectedCard.sources"
          :key="source.url"
          class="source-button"
          @click="openSource(source)"
        >
          <view class="flex-one"
            ><text>{{ source.title }}</text
            ><text class="muted">{{ source.date }}</text></view
          ><text>↗</text>
        </button></template
      ><template #footer
        ><button class="button primary full-width" @click="identifyFromKnowledge">
          带着照片，开始问诊 →
        </button></template
      ></UiDialog
    >
    <UiDialog
      v-if="regionOpen"
      title="作物长在哪里？"
      subtitle="选择种植地区，帮助了解田间环境。"
      @close="regionOpen = false"
      ><view class="form-stack"
        ><template v-if="!useCustom"
          ><view
            ><text class="field-label">省份</text
            ><SelectField
              :model-value="province"
              :options="provinces"
              label="省份"
              @update:model-value="changeProvince" /></view
          ><view
            ><text class="field-label">城市</text
            ><SelectField
              :model-value="city"
              :options="cities"
              label="城市"
              @update:model-value="changeCity" /></view
          ><view
            ><text class="field-label">区县</text
            ><SelectField v-model="district" :options="districts" label="区县" /></view></template
        ><view v-else class="form-field"
          ><text class="field-label">种植地区</text
          ><input
            v-model="customLocation"
            aria-label="手动填写地区"
            placeholder="输入省、市、县或乡镇"
            :maxlength="120" /></view></view
      ><button class="text-button manual-region" @click="useCustom = !useCustom">
        {{ useCustom ? '返回地区选择' : '其他地区，手动填写' }}</button
      ><template #footer
        ><button class="button primary full-width" @click="confirmRegion">
          确认地区
        </button></template
      ></UiDialog
    >
    <AdminConsole
      v-if="adminOpen && isAdmin"
      :base="apiBase()"
      :meta="meta"
      :busy="busy"
      @close="adminOpen = false"
      @refresh="refreshAdmin"
    />
    <UiDialog v-if="editOpen && current" title="补充种植情况" @close="editOpen = false"
      ><view class="form-stack"
        ><view
          ><text class="field-label">生育期</text
          ><SelectField
            v-model="editStage"
            :options="stages[current.crop || crop]"
            label="问诊生育期" /></view
        ><view class="form-field"
          ><text class="field-label">地区</text
          ><input v-model="editLocation" aria-label="问诊地区" :maxlength="120" /></view
        ><view
          ><text class="field-label">症状与近期用药</text
          ><textarea
            v-model="editNote"
            aria-label="补充症状"
            class="note-input"
            placeholder="补充出现时间、分布或近期用药…"
            :maxlength="2000"
          /></view></view
      ><template #footer
        ><button class="button primary full-width" :disabled="busy" @click="saveCase">
          保存情况
        </button></template
      ></UiDialog
    >
    <UiDialog
      v-if="infoOpen && current"
      title="本次问诊资料"
      :subtitle="current.crop_name + ' · ' + current.location"
      @close="infoOpen = false"
      ><view class="settings-row"
        ><text>生育期</text><text>{{ current.stage }}</text></view
      ><view class="settings-row"
        ><text>建立时间</text><text>{{ dateLabel(current.created_at) }}</text></view
      ><text v-if="current.note" class="article-summary">{{ current.note }}</text
      ><view class="info-photos"
        ><button
          v-for="image in current.images"
          :key="image.id"
          aria-label="查看补充图片"
          @click="viewPhoto(image.id)"
        >
          <image :src="imageUrl(current, image.id)" mode="aspectFill" /></button
        ><image v-if="!current.images.length" :src="imageUrl(current)" mode="aspectFit" /></view
      ><button
        v-if="!current.is_demo"
        class="button secondary full-width"
        :disabled="current.images.length >= 6 || busy"
        @click="openPhotoSources('supplement')"
      >
        ＋ 补充照片</button
      ><template #footer
        ><button class="button primary full-width" @click="editCase">编辑种植情况</button></template
      ></UiDialog
    >
    <UiDialog
      v-if="deleteTarget"
      title="删除这条问诊？"
      subtitle="关联的照片与对话会一起删除，删除后无法恢复。"
      @close="deleteTarget = null"
      ><text class="article-summary">{{ deleteTarget.title }}</text
      ><template #footer
        ><view class="confirm-actions"
          ><button class="button secondary" :disabled="busy" @click="deleteTarget = null">
            保留记录</button
          ><button class="button danger" :disabled="busy" @click="confirmDelete">
            确认删除
          </button></view
        ></template
      ></UiDialog
    >
  </view>
</template>

<style scoped>
.continue-question {
  font-size: 12px;
  margin: 13px 0;
  min-height: 40px;
}

.result-actions {
  display: flex;
  gap: 11px;
  justify-content: flex-end;
  border-top: 1px solid var(--line);
  padding: 13px 28px;
  background: var(--surface);
  flex-shrink: 0;
}
.result-actions > .button.primary {
  min-width: 190px;
}
.result-actions > .button {
  font-size: 12px;
  min-height: 44px;
}
@media (max-width: 760px) {
  .result-actions {
    padding: 11px 16px;
    gap: 10px;
  }
  .result-actions > .button.primary {
    min-width: 0;
    flex: 1;
  }
  .result-actions > .button {
    font-size: 12px;
  }
}

.result-score {
  display: flex;
  align-items: center;
  gap: 13px;
  margin: 0 0 20px;
}
.result-score > text {
  font-size: 31px;
  line-height: 1.1;
  font-weight: 600;
  letter-spacing: -1px;
}
.result-score > text > text {
  font-size: 15px;
  letter-spacing: 0;
  margin-left: 2px;
}
.result-score > view > text:first-child {
  display: block;
  font-size: 11px;
  color: var(--ink);
}
.result-score > view > text:last-child {
  display: block;
  font-size: 10px;
  color: var(--muted);
  margin-top: 4px;
}

.breadcrumb-home {
  font-size: 12px;
  color: var(--muted);
  padding: 7px 0;
}
.breadcrumb-home:hover {
  color: var(--ink);
  text-decoration: underline;
  text-underline-offset: 4px;
}

.navigation-toggle {
  display: inline-flex;
  flex-shrink: 0;
  font-size: 21px;
}
.nav-collapsed .sidebar {
  display: none;
}
.header-result-link {
  font-size: 11px;
  color: var(--accent);
  padding: 7px 9px;
  border-radius: 8px;
  white-space: nowrap;
}
.case-toolbar {
  grid-template-columns: 36px minmax(0, 1fr) 36px !important;
}
.case-heading {
  grid-column: 2 !important;
  grid-row: 1 !important;
}
.case-toolbar > .icon-button:last-child {
  grid-column: 3 !important;
  grid-row: 1 !important;
}

.sidebar {
  width: 230px;
  flex-shrink: 0;
  background: var(--surface);
  border-right: 1px solid var(--line);
  display: flex;
  flex-direction: column;
  padding: 28px 20px 23px;
}
.brand {
  display: flex;
  gap: 12px;
  align-items: center;
  text-align: left;
  margin: 4px 0 42px;
}
.brand-mark {
  width: 43px;
  height: 43px;
  border-radius: 14px;
  background: #216b4b;
  display: flex;
  align-items: center;
  justify-content: center;
}
.brand-name {
  display: block;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.8px;
}
.brand-caption {
  display: block;
  font-size: 10px;
  letter-spacing: 2px;
  color: var(--muted);
  margin-top: 1px;
}
.nav-caption {
  font-size: 10px;
  color: var(--muted);
  letter-spacing: 1px;
  margin: 0 13px 12px;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 13px;
  padding: 13px 15px;
  border-radius: 12px;
  font-size: 14px;
  margin: 3px 0;
  color: var(--muted);
  min-height: 48px;
}
.nav-item.active {
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 550;
}
.sidebar-bottom {
  border-top: 1px solid var(--line);
  padding: 16px 10px 0;
}
.nav-settings {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  min-height: 38px;
}
.sidebar-bottom .fine-print {
  font-size: 9px;
  margin-top: 8px;
}
.main-shell {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
}
.topbar {
  height: 76px;
  min-height: 76px;
  padding: 0 32px;
  border-bottom: 1px solid var(--line);
  background: var(--glass);
  backdrop-filter: blur(20px);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  z-index: 40;
  flex-shrink: 0;
}
.breadcrumb {
  display: flex;
  align-items: center;
  gap: 15px;
  font-size: 12px;
  min-width: 0;
}
.crumb-divider {
  color: var(--line);
}
.topbar-title {
  font-weight: 550;
  font-size: 13px;
  white-space: nowrap;
}
.topbar-actions {
  display: flex;
  align-items: center;
  gap: 16px;
}
.login-button {
  font-size: 12px;
  font-weight: 550;
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 7px 14px;
  background: var(--surface);
  white-space: nowrap;
  min-height: 37px;
}
.account-button {
  display: flex;
  align-items: center;
  gap: 9px;
  min-height: 40px;
}
.avatar {
  width: 31px;
  height: 31px;
  background: var(--accent-soft);
  color: var(--accent);
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 13px;
  font-weight: 600;
}
.account-name {
  font-size: 12px;
  max-width: 75px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.workspace {
  flex: 1;
  min-height: 0;
  position: relative;
  display: flex;
  overflow: hidden;
}
.page-scroll {
  flex: 1;
  min-height: 0;
  height: 100%;
  width: 100%;
}
.page-content {
  max-width: 1320px;
  margin: 0 auto;
  padding: 30px 34px 20px;
}
.selected .crop-radio {
  color: var(--accent);
}
.page-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 15px;
  color: var(--muted);
  font-size: 9px;
  padding: 27px 2px 8px;
}
.page-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 20px;
  margin: 6px 0 30px;
}
.page-title {
  font-size: 28px;
  font-weight: 650;
  letter-spacing: -0.6px;
  display: block;
  line-height: 1.6;
  margin: 7px 0 5px;
}
.page-heading .muted {
  font-size: 12px;
}
.list-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 14px;
}
.filter-tabs {
  display: flex;
  gap: 6px;
}
.filter-tabs > button {
  font-size: 12px;
  padding: 7px 13px;
  border-radius: 9px;
  color: var(--muted);
  min-height: 35px;
}
.filter-tabs > button.active {
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 550;
}
.search-field {
  display: flex;
  gap: 9px;
  align-items: center;
  padding: 8px 12px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 11px;
  width: 270px;
  max-width: 100%;
}
.search-field input {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  height: 25px;
}
.history-panel {
  padding: 22px 25px;
}
.history-row {
  border-top: 1px solid var(--line);
  padding: 19px 0;
  display: flex;
  gap: 10px;
  align-items: center;
}
.history-main {
  display: flex;
  align-items: center;
  gap: 17px;
  text-align: left;
  flex: 1;
  min-width: 0;
}
.history-main > image {
  width: 64px;
  height: 64px;
  background: var(--subtle);
  border-radius: 13px;
  flex-shrink: 0;
}
.history-title {
  display: block;
  font-size: 14px;
  font-weight: 550;
  margin-bottom: 5px;
}
.history-main .small {
  font-size: 11px;
}
.case-area {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  min-width: 0;
}
.case-toolbar {
  display: grid;
  grid-template-columns: 40px minmax(0, 1fr) auto 40px;
  align-items: center;
  gap: 14px;
  padding: 15px 29px;
  background: var(--surface);
  border-bottom: 1px solid var(--line);
  flex-shrink: 0;
}
.case-heading > .strong {
  display: block;
  font-size: 13px;
}
.case-heading > .muted {
  display: block;
  font-size: 11px;
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.result-content {
  width: 100%;
  padding-top: 15px;
}
.result-grid {
  display: grid;
  grid-template-columns: minmax(220px, 0.65fr) minmax(0, 1.35fr);
  gap: 23px;
  align-items: start;
}
.photo-panel {
  padding: 22px;
}
.photo-panel .section-title {
  font-size: 15px;
}
.case-photo {
  display: block;
  width: 100%;
  height: 245px;
  background: var(--subtle);
  border-radius: 13px;
  margin: 18px 0;
}
.case-photo > image {
  width: 100%;
  height: 100%;
}
.case-context {
  margin-top: 21px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.case-note {
  font-size: 12px;
  line-height: 1.9;
}
.case-context > .text-button {
  font-size: 11px;
}
.result-panel {
  padding: 28px;
}
.result-title {
  font-size: 25px;
  font-weight: 650;
  letter-spacing: -0.4px;
  line-height: 1.65;
  display: block;
  margin: 12px 0;
}
.result-summary {
  display: block;
  font-size: 14px;
  line-height: 1.95;
  color: var(--muted);
  margin-bottom: 27px;
}
.subheading {
  display: block;
  font-size: 14px;
  font-weight: 650;
  margin: 24px 0 12px;
}
.product-section {
  border-top: 1px solid var(--line);
  margin-top: 23px;
}
.product-section .muted {
  display: block;
  line-height: 1.9;
  font-size: 12px;
}
.product-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 12px;
  margin: 13px 0;
}
.result-sources,
.candidate-section {
  border-top: 1px solid var(--line);
  margin-top: 23px;
}
.candidate-section {
  padding-top: 18px;
}
.continue-button {
  margin-top: 27px;
  justify-content: space-between;
}
.guest-save {
  display: flex;
  justify-content: center;
  width: 100%;
  margin-top: 9px;
  font-size: 11px;
}
.chat-workspace {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.chat-mode-note {
  flex-shrink: 0;
  text-align: center;
  font-size: 10px;
  color: var(--muted);
  padding: 8px 15px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
}
.chat-mode-note > button {
  color: var(--accent);
  font-size: 10px;
  text-decoration: underline;
  text-underline-offset: 3px;
  white-space: nowrap;
}
.message-scroll {
  flex: 1;
  min-height: 0;
  height: 0;
  width: 100%;
}
.message-stream {
  max-width: 840px;
  width: 100%;
  margin: 0 auto;
  padding: 25px 27px 10px;
}
.chat-welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  max-width: 510px;
  margin: 35px auto 22px;
  gap: 14px;
}
.welcome-mark {
  font-size: 29px;
  width: 70px;
  height: 70px;
  border-radius: 23px;
  background: var(--accent-soft);
  display: flex;
  align-items: center;
  justify-content: center;
}
.welcome-title {
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -0.5px;
  margin-top: 4px;
}
.chat-welcome > .muted {
  font-size: 13px;
  line-height: 1.9;
  max-width: 390px;
}
.welcome-topics {
  width: 100%;
  max-width: 380px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 15px 0;
}
.welcome-topics > button {
  width: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 13px;
  padding: 12px 17px;
  font-size: 12px;
  text-align: left;
}
.welcome-topics > button > text {
  color: var(--muted);
}
.message-row {
  display: flex;
  align-items: flex-start;
  gap: 11px;
  margin: 0 0 30px;
  max-width: 94%;
}
.assistant-avatar {
  width: 31px;
  height: 31px;
  border-radius: 10px;
  background: var(--accent-soft);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 17px;
  flex-shrink: 0;
  margin-top: 1px;
}
.message-content {
  min-width: 0;
  max-width: 100%;
}
.message-author {
  font-size: 12px;
  font-weight: 550;
  display: block;
  margin: 3px 0 10px;
}
.message-author > text {
  font-weight: 400;
  font-size: 10px;
  color: var(--muted);
  margin-left: 8px;
}
.message-bubble {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: 14px;
  line-height: 1.95;
  display: block;
  user-select: text;
}
.message-row.user {
  margin-left: auto;
  justify-content: flex-end;
  max-width: 83%;
  margin-bottom: 29px;
}
.user .message-bubble {
  background: var(--accent-soft);
  color: var(--ink);
  border: 1px solid var(--line);
  border-radius: 19px 19px 4px 19px;
  padding: 12px 17px;
}
.message-tools {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}
.source-chip {
  font-size: 10px;
  border: 1px solid var(--line);
  border-radius: 7px;
  padding: 4px 8px;
  color: var(--muted);
  text-align: left;
}
.copy-button {
  font-size: 10px;
  color: var(--muted);
  padding: 5px 8px;
}
.responding {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--muted);
  font-size: 12px;
  padding: 10px 0 25px 40px;
}
.chat-end {
  height: 1px;
}
.composer-dock {
  flex-shrink: 0;
  z-index: 10;
  background: var(--bg);
  padding: 12px 25px max(13px, env(safe-area-inset-bottom));
  border-top: 1px solid transparent;
}
.composer-wrap {
  max-width: 790px;
  margin: 0 auto;
  width: 100%;
}
.manual-region {
  margin-top: 18px;
}
.info-photos {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin: 15px 0 20px;
}
.info-photos > button,
.info-photos > image {
  width: 95px;
  height: 95px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--subtle);
  overflow: hidden;
}
.info-photos image {
  width: 95px;
  height: 95px;
}
.confirm-actions {
  display: flex;
  gap: 12px;
}
.confirm-actions > .button {
  flex: 1;
}
@media (min-width: 1550px) {
  .page-content {
    padding-top: 37px;
  }
}
@media (max-width: 1190px) {
  .sidebar {
    width: 205px;
    padding-left: 15px;
    padding-right: 15px;
  }
  .brand-name {
    font-size: 20px;
  }
  .brand-mark {
    width: 39px;
    height: 39px;
  }
  .brand {
    gap: 9px;
  }
  .topbar {
    padding: 0 24px;
  }
  .page-content {
    padding: 25px;
  }
  .result-grid {
    grid-template-columns: 230px minmax(0, 1fr);
    gap: 18px;
  }
  .result-panel {
    padding: 23px;
  }
  .photo-panel {
    padding: 18px;
  }
  .case-toolbar {
    padding-left: 20px;
    padding-right: 20px;
  }
  .message-stream {
    padding-left: 30px;
    padding-right: 30px;
  }
}
@media (max-width: 1000px) and (min-width: 761px) {
  .sidebar {
    width: 78px;
    padding: 28px 10px;
  }
  .brand {
    justify-content: center;
    margin-bottom: 35px;
  }
  .brand > view:last-child,
  .nav-caption,
  .nav-item > text,
  .sidebar-bottom {
    display: none;
  }
  .nav-item {
    justify-content: center;
    padding: 12px;
  }
  .topbar-actions {
    gap: 9px;
  }
}
@media (max-width: 760px) {
  .desktop-only,
  .sidebar {
    display: none !important;
  }
  .topbar {
    height: 62px;
    min-height: 62px;
    padding: 0 16px;
    gap: 10px;
    background: var(--glass);
  }
  .topbar-title {
    font-size: 15px;
  }
  .breadcrumb {
    gap: 8px;
    min-width: 0;
  }
  .topbar-actions {
    gap: 6px;
  }
  .login-button {
    font-size: 12px;
    padding: 5px 12px;
    min-height: 34px;
    border-radius: 9px;
  }
  .account-button {
    gap: 4px;
  }
  .account-name {
    display: none;
  }
  .account-button .avatar {
    width: 30px;
    height: 30px;
  }
  .account-button .app-icon {
    display: none;
  }
  .page-content {
    padding: 17px 16px 10px;
  }
  .page-footer {
    font-size: 8px;
    gap: 8px;
    padding: 24px 2px 15px;
  }
  .page-heading {
    margin: 5px 0 24px;
    align-items: center;
    gap: 10px;
  }
  .page-title {
    font-size: 24px;
    margin: 7px 0 6px;
    line-height: 1.6;
  }
  .page-heading .muted {
    font-size: 12px;
    line-height: 1.9;
    display: block;
  }
  .page-heading > .button {
    font-size: 11px;
    padding: 7px 11px;
    min-height: 39px;
    white-space: nowrap;
  }
  .page-heading > .badge {
    font-size: 9px;
    padding: 4px 6px;
    flex-shrink: 0;
  }
  .history-panel {
    padding: 17px;
  }
  .list-toolbar {
    flex-direction: column;
    align-items: stretch;
    gap: 15px;
    margin-bottom: 15px;
  }
  .filter-tabs {
    justify-content: space-between;
    gap: 8px;
  }
  .filter-tabs > button {
    font-size: 12px;
    padding: 6px 14px;
  }
  .search-field {
    width: 100%;
    padding: 9px 12px;
  }
  .search-field input {
    font-size: 13px;
  }
  .history-row {
    padding: 18px 0;
    gap: 6px;
  }
  .history-main {
    gap: 11px;
    flex-wrap: wrap;
    position: relative;
  }
  .history-main > image {
    width: 52px;
    height: 59px;
    border-radius: 10px;
  }
  .history-title {
    font-size: 13px;
    line-height: 1.8;
    margin-bottom: 4px;
  }
  .history-main .small {
    font-size: 10px;
  }
  .history-main > .badge {
    font-size: 8px;
    margin-left: 63px;
    margin-top: -7px;
    display: none;
  }
  .history-row > .icon-button {
    width: 32px;
    min-width: 32px;
  }
  .case-toolbar {
    grid-template-columns: 36px minmax(0, 1fr) 36px;
    padding: 11px 15px 12px;
    gap: 8px;
  }
  .case-back {
    grid-column: 1;
    grid-row: 1;
    min-width: 36px;
    width: 36px;
    height: 36px;
  }
  .case-heading {
    grid-column: 2;
    grid-row: 1;
  }
  .case-heading > .strong {
    font-size: 12px;
  }
  .case-heading > .muted {
    font-size: 10px;
    max-width: 240px;
  }
  .case-toolbar > .icon-button:last-child {
    grid-column: 3;
    grid-row: 1;
    min-width: 36px;
    width: 36px;
    height: 36px;
  }
  .chat-mode-note {
    font-size: 9px;
    line-height: 1.6;
    padding: 9px 12px;
    gap: 8px;
    justify-content: space-between;
  }
  .chat-mode-note > button {
    font-size: 9px;
  }
  .message-stream {
    padding: 20px 17px 10px;
  }
  .chat-welcome {
    margin: 14px auto 5px;
    gap: 12px;
  }
  .welcome-mark {
    width: 58px;
    height: 58px;
    border-radius: 20px;
    font-size: 26px;
  }
  .welcome-title {
    font-size: 20px;
    line-height: 1.6;
    margin: 5px 0;
  }
  .chat-welcome > .muted {
    font-size: 12px;
    max-width: 280px;
    line-height: 1.9;
  }
  .welcome-topics {
    margin: 9px 0 15px;
    gap: 9px;
  }
  .welcome-topics > button {
    font-size: 12px;
    padding: 11px 14px;
  }
  .message-row {
    gap: 8px;
    max-width: 100%;
    margin-bottom: 25px;
  }
  .assistant-avatar {
    width: 26px;
    height: 26px;
    border-radius: 9px;
    font-size: 14px;
  }
  .message-content {
    max-width: calc(100% - 34px);
  }
  .message-author {
    font-size: 11px;
    margin: 2px 0 8px;
  }
  .message-author > text {
    font-size: 9px;
    margin-left: 6px;
  }
  .message-bubble {
    font-size: 14px;
    line-height: 1.95;
  }
  .user .message-bubble {
    padding: 11px 14px;
  }
  .message-row.user {
    max-width: 90%;
  }
  .user .message-content {
    max-width: 100%;
  }
  .message-tools {
    gap: 6px;
  }
  .source-chip {
    font-size: 9px;
    line-height: 1.8;
    padding: 4px 7px;
  }
  .copy-button {
    font-size: 10px;
  }
  .composer-dock {
    padding: 10px 12px calc(12px + env(safe-area-inset-bottom));
    border-top-color: var(--line);
  }
  .result-content {
    padding-top: 0;
  }
  .result-content .inline-alert {
    margin-top: 15px;
    margin-bottom: 15px;
    font-size: 11px;
  }
  .result-grid {
    display: flex;
    flex-direction: column;
    gap: 17px;
  }
  .photo-panel {
    order: 2;
    width: 100%;
    padding: 21px;
  }
  .result-panel {
    order: 1;
    width: 100%;
    padding: 23px 21px;
  }
  .result-title {
    font-size: 23px;
    line-height: 1.6;
  }
  .result-summary {
    font-size: 13px;
    line-height: 2;
  }
  .subheading {
    font-size: 14px;
  }
  .action-row {
    font-size: 13px;
  }
  .product-section .muted {
    font-size: 12px;
  }
  .source-button {
    font-size: 11px;
    line-height: 1.9;
  }
  .case-photo {
    height: 240px;
  }
  .case-context {
    margin-top: 18px;
  }
  .case-note {
    font-size: 13px;
  }
  .guest-save {
    font-size: 12px;
  }
  .is-chat .toast {
    bottom: 125px;
  }
  .info-photos {
    gap: 8px;
  }
  .info-photos > button,
  .info-photos > image,
  .info-photos image {
    width: 90px;
    height: 90px;
  }
}
/* #ifdef MP-WEIXIN */
.topbar {
  padding-top: calc(var(--status-bar-height) + 42px);
  min-height: calc(104px + var(--status-bar-height));
  height: calc(104px + var(--status-bar-height));
}
/* #endif */
.context-choice {
  margin: 17px 0 8px;
  padding: 15px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 14px;
}
.context-prompt {
  font-size: 12px;
  font-weight: 550;
  display: block;
  margin-bottom: 11px;
}
.context-options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.context-options > button {
  padding: 7px 11px;
  border: 1px solid var(--line);
  border-radius: 9px;
  color: var(--ink);
  background: var(--subtle);
  font-size: 12px;
  min-height: 35px;
}
.context-options > button:hover {
  border-color: var(--focus);
}
.message-attachments {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 12px;
}
.message-image,
.message-image > image {
  width: 120px;
  height: 110px;
  border-radius: 12px;
  overflow: hidden;
}
.message-file {
  font-size: 11px;
  padding: 7px 10px;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: var(--subtle);
  overflow-wrap: anywhere;
}
.chat-photo-preview {
  width: 100%;
  height: 180px;
  border-radius: 13px;
  background: var(--subtle);
  margin: 0 0 20px;
}
.photo-crop-choices {
  display: flex;
  gap: 9px;
  margin-bottom: 22px;
}
.photo-crop-choices > button {
  flex: 1;
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 10px;
  text-align: center;
  font-size: 13px;
  background: var(--subtle);
}
.photo-crop-choices > button.active {
  border-color: var(--focus);
  background: var(--accent-soft);
  color: var(--ink);
}
.experiment-badge {
  margin-left: 8px;
  font-size: 9px;
}
@media (max-width: 760px) {
  .context-choice {
    padding: 12px;
  }
  .context-options {
    gap: 7px;
  }
  .context-options > button {
    font-size: 11px;
    padding: 7px 9px;
  }
  .experiment-badge {
    display: flex;
    margin: 9px 0 0;
    font-size: 9px;
  }
  .message-image,
  .message-image > image {
    width: 110px;
    height: 100px;
  }
}
.result-photo-thumbs {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin: 11px 0 15px;
}
.result-photo-thumbs > button {
  position: relative;
  width: 62px;
  height: 62px;
  overflow: hidden;
  border-radius: 9px;
}
.result-photo-thumbs image {
  width: 100%;
  height: 100%;
}
.result-photo-thumbs text {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  font-size: 9px;
  background: #0008;
  color: #fff;
  text-align: center;
}
@media (max-width: 760px) {
}
</style>
