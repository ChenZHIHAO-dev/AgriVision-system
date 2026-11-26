<script setup lang="ts">
import {
  computed,
  defineAsyncComponent,
  nextTick,
  onMounted,
  onUnmounted,
  ref,
  watch,
  type Component,
} from 'vue'
import AppIcon from '../../components/AppIcon.vue'
import { businessLoginRequired, loadPrivateWorkspace } from '../../lib/workspaceAccess'
// #ifndef MP-WEIXIN
import MobileHeader from '../../components/MobileHeader.vue'
// #endif
// #ifdef MP-WEIXIN
import WeChatHeader from '../../components/WeChatHeader.vue'

// #endif
import { conversationTitle } from '../../lib/conversationTitle'
import { useWorkspaceViewport } from '../../lib/viewport'
import { usePlatformChrome } from '../../lib/platformChrome'
import { chatPhotoContext } from '../../lib/chatPhoto'
import ChatPhotoDialog from '../../components/ChatPhotoDialog.vue'
import ContentReference from '../../components/ContentReference.vue'
// #ifdef H5
import GlobalNavigation from '../../components/GlobalNavigation.vue'
import HistorySidebar from '../../components/HistorySidebar.vue'
import WebWorkspaceHeader from '../../components/WebWorkspaceHeader.vue'
// #endif
import {
  initialPath,
  selectPage,
  showResult,
  showChat,
  showInspector,
  popView,
  openHistory,
  type MainPage,
  type ViewPath,
} from '../../lib/navigation'
import UiDialog from '../../components/UiDialog.vue'
import AuthDialog from '../../components/AuthDialog.vue'
import SelectField from '../../components/SelectField.vue'
import ChatComposer from '../../components/ChatComposer.vue'
import ChatSuggestions from '../../components/ChatSuggestions.vue'
import { contextSuggestionFor } from '../../lib/chatSuggestions'
import {
  answerCopyText,
  answerShareText,
  questionForAnswer,
  suggestedQuestions,
} from '../../lib/chatActions'
import ScanProgress from '../../components/ScanProgress.vue'
import PhotoCapture from '../../components/PhotoCapture.vue'
import CropIdentificationDialog from '../../components/CropIdentificationDialog.vue'
import DashboardHome from '../../components/DashboardHome.vue'
import NavigationDock from '../../components/NavigationDock.vue'
import KnowledgeLibrary from '../../components/KnowledgeLibrary.vue'
import { createDraftStore, type Draft } from '../../lib/drafts'
import ConversationDrawer from '../../components/ConversationDrawer.vue'
import PhotoSourceSheet from '../../components/PhotoSourceSheet.vue'
import UserCenter from '../../components/UserCenter.vue'
import UserSettings from '../../components/UserSettings.vue'
import AdminConsole from '../../components/AdminConsole.vue'
// #ifndef H5
import NativeMarkdownMessage from '../../components/MarkdownMessage.vue'
// #endif
import RecognitionResult from '../../components/RecognitionResult.vue'
import RecognitionSummary from '../../components/RecognitionSummary.vue'
import { recognitionFor, imageQuestion } from '../../lib/recognition'
import {
  ApiError,
  apiBase,
  dataMode,
  request,
  upload,
  identifyCrop,
  imageUrl,
  type Crop,
  type CropIdentification,
  type Meta,
  type CaseRecord,
  type KnowledgeCard,
  type Source,
  type DataMode,
} from '../../lib/api'
import { crops, stages, regions, dateLabel, statusLabel } from '../../lib/options'
import { auth, user, type AuthSuccess } from '../../lib/auth'
import { clearGuestRecords } from '../../lib/preview'
import { resolvedTheme, observeSystemTheme } from '../../lib/theme'
import type { ChatModel, DocumentAttachment, ContextSuggestion, ContextField } from '../../lib/api'

let MarkdownMessage: Component
// #ifdef H5
MarkdownMessage = defineAsyncComponent(() => import('../../components/MarkdownMessage.vue'))
// #endif
// #ifndef H5
MarkdownMessage = NativeMarkdownMessage
// #endif

const { isMobile, nativeWindow, keyboardHeight, keyboardDuration, receiveNativeKeyboard } =
  useWorkspaceViewport()

type Tab = MainPage
let startPage: MainPage = 'home'
// #ifdef MP-WEIXIN
startPage = 'identify'
// #endif
const viewPath = ref(initialPath(startPage))
const tab = computed({
  get: () => viewPath.value.page,
  set: (value: Tab) => {
    viewPath.value = selectPage(viewPath.value, value)
  },
})
const crop = ref<Crop>('wheat'),
  stage = ref('不清楚'),
  note = ref('')
const selectedPhoto = ref<{ path: string; crop: Crop } | null>(null)
const cropLookup = ref<{
  busy: boolean
  photo: string
  result: CropIdentification | null
  error: string
} | null>(null)
function openCropLookup() {
  if (businessLoginRequired(mode.value, !!user.value)) {
    requestBusinessLogin('crop')
    return
  }
  cropLookup.value = { busy: false, photo: '', result: null, error: '' }
}
function useCropLookup(value: Crop) {
  chooseCrop(value)
  cropLookup.value = null
}
async function lookUpCrop(state: NonNullable<typeof cropLookup.value>, path: string) {
  state.busy = true
  state.photo = path
  state.result = null
  state.error = ''
  try {
    state.result = await identifyCrop(path)
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) showError(error)
    else state.error = error instanceof Error ? error.message : '作物识别暂时失败，请重试'
  } finally {
    state.busy = false
  }
}
const waitingForNetwork = ref(false)
const pausedUpload = computed(() =>
  waitingForNetwork.value && selectedPhoto.value
    ? crops.find((item) => item.id === selectedPhoto.value?.crop)?.name || ''
    : '',
)
const meta = ref<Meta | null>(null),
  online = ref(false),
  refreshing = ref(false),
  busy = ref(false),
  busyText = ref(''),
  error = ref('')
const records = ref<CaseRecord[]>([]),
  cards = ref<KnowledgeCard[]>([]),
  current = ref<CaseRecord | null>(null)
const composer = ref<{ focus: () => void }>()
const chatText = ref(''),
  sending = ref(false),
  pendingMessage = ref(''),
  scrollAnchor = ref('')
const retainedCase = ref<CaseRecord | null>(null)
const drafts = createDraftStore(),
  sidebarExpanded = ref(uni.getSystemInfoSync().windowWidth > 1050)
const query = ref(''),
  filter = ref('all'),
  selectedCard = ref<KnowledgeCard | null>(null)
const adminOpen = ref(false),
  regionOpen = ref(false),
  editOpen = ref(false),
  infoOpen = ref(false),
  chatOptions = ref<'actions' | 'rename' | null>(null),
  renameValue = ref(''),
  renaming = ref(false),
  renameError = ref(''),
  deleteTarget = ref<CaseRecord | null>(null)
type ConsultationLoginIntent = {
  action: 'new' | 'continue' | 'history' | 'photo' | 'crop' | 'library' | 'demo'
  photoSource?: 'album' | 'camera'
  photoTarget?: 'identify' | 'supplement' | 'crop'
  crop?: Crop | null
  record?: CaseRecord | null
  targetId?: string
  path: ViewPath
  draft: Draft
}
type ContinuedCaseRecovery = { id: string; path: ViewPath; draft: Draft }
const pendingCaseRecovery = ref<ContinuedCaseRecovery | null>(null)
const authIntent = ref<ConsultationLoginIntent | null>(null)
const authOpen = ref(false),
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
  editNote = ref('')
const homeSection = ref<'recent' | 'resources' | 'news'>('recent')
const leavingChat = ref(false)
let backTimer: ReturnType<typeof setTimeout> | undefined
function mobileBack() {
  if (chatMode.value) backView()
  else navigate(tab.value === 'history' ? 'home' : 'profile')
}
const historyDrawerOpen = ref(false),
  photoSourceOpen = ref(false),
  photoTarget = ref<'identify' | 'chat' | 'supplement'>('identify')
const isAdmin = computed(() => user.value?.role === 'admin')
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
  photoCrop = ref<Crop | null>(null),
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
const chatMode = computed(() => !!current.value && viewPath.value.layers.includes('chat'))
const {
  mobileSafeTop,
  nativeBottomInset,
  nativeWeChatTitle,
  wechatFrame,
  wechatCapsuleInset,
  profilePageStyle,
  drawerSafeTop,
  desktopCapture,
  compactHeader,
} = usePlatformChrome(nativeWindow, isMobile, tab, chatMode)
const resultOpen = computed(() =>
  ['result', 'inspector'].includes(viewPath.value.layers[viewPath.value.layers.length - 1] || ''),
)
const inspecting = computed(
  () => viewPath.value.layers[viewPath.value.layers.length - 1] === 'inspector',
)
const backLabel = computed(() =>
  viewPath.value.layers.includes('result')
    ? '返回结果'
    : {
        home: '返回首页',
        identify: '返回拍照',
        profile: '返回我的',
        settings: '返回设置',
        history: '返回记录',
        knowledge: '返回资料',
      }[tab.value],
)
const lastPhotoCase = ref<CaseRecord | null>(null)
let messageAttempt: { id: string; text: string; caseId: string } | null = null
const pendingImagePreviews = computed(
  () =>
    current.value?.images
      .filter((image) => pendingImages.value.includes(image.id))
      .map((image) => ({ id: image.id, url: imageUrl(current.value!, image.id) })) || [],
)
const currentReceipt = computed(() => (current.value ? recognitionFor(current.value) : undefined))
const title = computed(() =>
  chatMode.value && current.value
    ? conversationTitle(current.value)
    : {
        home: '工作台',
        identify: '拍照识别',
        history: '历史记录',
        knowledge: '参考资料',
        profile: '我的',
        settings: '设置',
      }[tab.value],
)
// #ifdef MP-WEIXIN
const wechatTitle = computed(() =>
  !chatMode.value && tab.value === 'home' ? '宛田观叶' : title.value,
)
const wechatBack = computed(
  () => chatMode.value || tab.value === 'history' || tab.value === 'settings',
)
const wechatProfile = computed(() => !chatMode.value && tab.value === 'profile')
const wechatSearch = computed(() =>
  !chatMode.value && tab.value === 'history' && user.value ? query.value : undefined,
)
const wechatBackLabel = computed(() =>
  chatMode.value ? backLabel.value : tab.value === 'settings' ? '返回我的' : '返回首页',
)
// #endif
const emptyChat = computed(
  () => !current.value?.messages.length && !currentReceipt.value?.image_received && !sending.value,
)
const cleanRename = computed(() => renameValue.value.trim().replace(/\s+/g, ' '))
const filteredRecords = computed(() =>
  records.value.filter(
    (record) =>
      (filter.value === 'all' || record.crop === filter.value) &&
      (conversationTitle(record) + record.title + record.note + record.crop_name)
        .toLowerCase()
        .includes(query.value.trim().toLowerCase()),
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
  const height = nativeWindow.value.windowHeight
  return {
    height: height + 'px',
    '--app-height': height + 'px',
    '--visual-height': Math.max(160, height - keyboardHeight.value) + 'px',
    '--dialog-safe-top': drawerSafeTop.value + 'px',
    '--dialog-safe-bottom': (keyboardHeight.value > 0 ? 0 : nativeBottomInset.value) + 'px',
    '--mobile-safe-top': mobileSafeTop.value + 'px',
    '--mobile-safe-bottom': nativeBottomInset.value + 'px',
  }
  // #endif
  // #ifdef H5
  return {
    '--mobile-safe-top': mobileSafeTop.value
      ? mobileSafeTop.value + 'px'
      : 'env(safe-area-inset-top, 0px)',
  }
  // #endif
})
watch(current, (value) => {
  if (value?.images.length && (!lastPhotoCase.value || lastPhotoCase.value.id === value.id))
    lastPhotoCase.value = value
})
const chatWorkspaceStyle = computed(() => {
  // #ifndef H5
  return {
    paddingBottom: keyboardHeight.value + 'px',
    '--chat-keyboard-duration': keyboardDuration.value + 'ms',
    '--chat-safe-bottom': (keyboardHeight.value ? 0 : nativeBottomInset.value) + 'px',
  }
  // #endif
})
let stopTheme: (() => void) | undefined
let stopNativeNavigation: (() => void) | undefined
onMounted(() => {
  stopTheme = observeSystemTheme()
  auth.restore().then(refresh)
  // #ifdef MP-WEIXIN
  stopNativeNavigation = watch(
    [wechatTitle, resolvedTheme, nativeWeChatTitle],
    ([label, theme, nativeTitle]) => {
      const backgroundColor = theme === 'dark' ? '#111111' : '#e9edeb'
      if (nativeTitle) uni.setNavigationBarTitle({ title: label })
      uni.setNavigationBarColor({
        frontColor: theme === 'dark' ? '#ffffff' : '#000000',
        backgroundColor,
      })
      uni.setBackgroundColor({ backgroundColor })
    },
    { immediate: true },
  )
  // #endif
  // #ifdef H5
  window.addEventListener('keydown', pageKeyboard)
  // #endif
})
onUnmounted(() => {
  stopTheme?.()
  stopNativeNavigation?.()
  clearTimeout(backTimer)
  clearTimeout(toastTimer)
  // #ifdef H5
  window.removeEventListener('keydown', pageKeyboard)
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
  if (value instanceof ApiError && value.status === 401 && mode.value === 'live') {
    // 只恢复页面与未发送草稿；重新登录不能自动重复付费提问。
    const targetId = current.value?.id
    const wasCropLookup = !!cropLookup.value
    rememberDraft()
    const draft = targetId
      ? drafts.get(targetId)
      : { text: chatText.value, documents: [], images: [] }
    const path = { ...viewPath.value, layers: [...viewPath.value.layers] }
    auth.expire()
    records.value = []
    current.value = null
    retainedCase.value = null
    lastPhotoCase.value = null
    cropLookup.value = null
    selectedCard.value = null
    photoDialogOpen.value = false
    editOpen.value = false
    regionOpen.value = false
    adminOpen.value = false
    openAuth('登录已过期，请重新登录后继续。', {
      action: wasCropLookup
        ? 'crop'
        : selectedPhoto.value
          ? 'photo'
          : targetId
            ? 'continue'
            : 'library',
      targetId,
      draft,
      path,
    })
  }
}
async function refresh() {
  refreshing.value = true
  try {
    meta.value = await request<Meta>('/api/meta')
    online.value = true
    const workspace = await loadPrivateWorkspace(request, mode.value, !!user.value)
    records.value = workspace.records
    cards.value = workspace.cards
  } catch (value) {
    // 401 表示需要登录，不能显示为服务离线或丢弃已取得的启动信息。
    if (!(value instanceof ApiError && value.status === 401)) online.value = false
    showError(value)
  } finally {
    refreshing.value = false
  }
}
function navigate(value: Tab) {
  if (value === 'history' && !user.value) {
    requestConsultationLogin('history')
    return
  }
  const next =
    chatMode.value && tab.value === value
      ? { ...viewPath.value, layers: [] }
      : selectPage(viewPath.value, value)
  if (next === viewPath.value) return
  rememberDraft()
  if (current.value) retainedCase.value = current.value
  viewPath.value = next
  filter.value = 'all'
  query.value = ''
  error.value = ''
}
function backView() {
  if (leavingChat.value) return
  rememberDraft()
  const top = viewPath.value.layers[viewPath.value.layers.length - 1]
  if (top === 'chat' && isMobile.value) {
    leavingChat.value = true
    backTimer = setTimeout(() => {
      viewPath.value = popView(viewPath.value)
      leavingChat.value = false
    }, 130)
  } else viewPath.value = popView(viewPath.value)
}
function inspectResult() {
  viewPath.value = showInspector(viewPath.value)
}
function restoreResult() {
  if (!lastPhotoCase.value) return
  rememberDraft()
  current.value = lastPhotoCase.value
  restoreComposer()
  viewPath.value = showResult(viewPath.value, current.value.id)
}
function pageKeyboard(event: KeyboardEvent) {
  if (event.defaultPrevented) return
  // #ifdef H5
  if (
    event.key !== 'Escape' ||
    document.querySelector(
      '[data-modal-id],[data-choice-layer],.conversation-drawer-backdrop,.attachment-menu',
    )
  )
    return
  if (viewPath.value.layers.length) {
    event.preventDefault()
    backView()
  }
  // #endif
}
function chooseCrop(value: Crop) {
  crop.value = value
  stage.value = '不清楚'
}
function openAuth(reason = '', intent: ConsultationLoginIntent | null = null) {
  authReason.value = reason
  authIntent.value = intent
  authOpen.value = true
}
function cancelAuth() {
  authOpen.value = false
  authIntent.value = null
}
function requestBusinessLogin(
  action: 'photo' | 'crop' | 'library' | 'demo',
  photoSource: 'album' | 'camera' = 'album',
  photoTarget: 'identify' | 'supplement' | 'crop' = 'identify',
) {
  openAuth('登录后可使用拍照识别、AI 对话和资料服务。', {
    action,
    photoSource,
    photoTarget,
    path: { ...viewPath.value, layers: [...viewPath.value.layers] },
    draft: { text: '', documents: [], images: [] },
  })
}
function requestConsultationLogin(
  action: ConsultationLoginIntent['action'],
  selectedCrop: Crop | null = null,
  targetId?: string,
  selectedRecord?: CaseRecord | null,
) {
  rememberDraft()
  // Only an explicit continuation of the current guest photo grants permission
  // to move that photo into the account. New consultations and history do not.
  const record =
    action === 'continue' &&
    selectedRecord?.id === current.value?.id &&
    selectedRecord?.persistence === 'temporary' &&
    selectedRecord.images.length > 0
      ? selectedRecord
      : null
  const intent: ConsultationLoginIntent = {
    action,
    crop: selectedCrop,
    record,
    targetId,
    path: { ...viewPath.value, layers: [...viewPath.value.layers] },
    draft: record
      ? drafts.get(record.id)
      : { text: action === 'continue' ? chatText.value : '', documents: [], images: [] },
  }
  const reason =
    action === 'new'
      ? '登录后可询问 AI，了解种植问题或药品作用。'
      : action === 'history'
        ? '登录后可打开历史记录并继续对话。'
        : record
          ? '登录后将这次照片与识别结果保存到账户，继续对话。'
          : '登录后即可询问 AI。'
  openAuth(reason, intent)
}
async function loadContinuedCase(recovery: ContinuedCaseRecovery) {
  // Fetch fresh account-owned image links before rendering the transferred case.
  const continued = await request<CaseRecord>('/api/cases/' + recovery.id)
  current.value = continued
  retainedCase.value = continued
  lastPhotoCase.value = continued.images.length ? continued : null
  drafts.save(continued.id, recovery.draft)
  restoreComposer()
  viewPath.value = { ...recovery.path, layers: [...recovery.path.layers] }
  pendingCaseRecovery.value = null
  openChat()
}
async function retryContinuedCase() {
  const recovery = pendingCaseRecovery.value
  if (!recovery || busy.value) return
  busy.value = true
  busyText.value = '正在重新载入本次识别…'
  error.value = ''
  try {
    await loadContinuedCase(recovery)
    await refresh()
  } catch (value) {
    showError(value)
  } finally {
    busy.value = false
  }
}
async function signedIn(result: AuthSuccess) {
  const intent = authIntent.value
  authOpen.value = false
  authIntent.value = null
  try {
    clearGuestRecords()
    drafts.clear()
    clearComposer()
    records.value = []
    current.value = null
    retainedCase.value = null
    lastPhotoCase.value = null
    pendingCaseRecovery.value = null
    if (!intent) {
      viewPath.value = initialPath()
      navigate('profile')
      await refresh()
      showToast(
        result.preview
          ? '已进入离线演示，记录仅在当前页面保留。'
          : '已登录，后续记录将保存到你的账户。',
      )
      return
    }
    viewPath.value = { ...intent.path, caseId: null, layers: [] }
    if (intent.record && result.continuedCaseId === intent.record.id) {
      const recovery = { id: intent.record.id, path: intent.path, draft: intent.draft }
      pendingCaseRecovery.value = recovery
      await loadContinuedCase(recovery)
    } else if (intent.action === 'photo') {
      await refresh()
      if (selectedPhoto.value) await startCase()
      else choosePhoto(intent.photoSource || 'album', intent.photoTarget || 'identify')
    } else if (intent.action === 'crop') {
      await refresh()
      openCropLookup()
    } else if (intent.action === 'library') {
      navigate(intent.path.page === 'home' ? 'home' : 'knowledge')
    } else if (intent.action === 'demo') {
      await demo()
    } else if (intent.action === 'continue' && intent.targetId) {
      await openCase(intent.targetId)
      drafts.save(intent.targetId, intent.draft)
      restoreComposer()
      openChat()
    } else if (intent.action === 'history') {
      if (intent.targetId) await openCase(intent.targetId)
      else navigate('history')
    } else {
      await startConsultation(intent.crop || null)
      const opened = current.value as CaseRecord | null
      if (opened && intent.draft.text) {
        drafts.save(opened.id, intent.draft)
        restoreComposer()
      }
    }
    await refresh()
    showToast(result.preview ? '已进入离线演示，可继续使用。' : '已登录，可继续使用。')
  } catch (value) {
    showError(value)
  }
}
async function signOut() {
  pendingCaseRecovery.value = null
  await auth.logout()
  clearGuestRecords()
  drafts.clear()
  clearComposer()
  current.value = null
  retainedCase.value = null
  lastPhotoCase.value = null
  viewPath.value = initialPath()
  records.value = []
  navigate('profile')
  selectedPhoto.value = null
  waitingForNetwork.value = false
  note.value = ''
  await refresh()
  showToast('已退出登录，使用在线功能时请重新登录。')
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
function choosePhoto(
  source: 'album' | 'camera' = 'album',
  target: 'identify' | 'supplement' | 'crop' = 'identify',
) {
  if (businessLoginRequired(mode.value, !!user.value)) {
    requestBusinessLogin('photo', source, target)
    return
  }
  const lookup = target === 'crop' ? cropLookup.value : null
  if (
    busy.value ||
    (target === 'crop' && (!lookup || lookup.busy || !meta.value?.crop_recognition?.ready))
  )
    return
  const selectedCrop = crop.value
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
      const path = result.tempFilePaths[0]
      if (target === 'crop') {
        if (lookup && lookup === cropLookup.value) await lookUpCrop(lookup, path)
      } else if (target === 'supplement') await addPhoto(path)
      else {
        selectedPhoto.value = { path, crop: selectedCrop }
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
  if (businessLoginRequired(mode.value, !!user.value)) {
    requestBusinessLogin('photo')
    return
  }
  const selected = selectedPhoto.value
  if (!selected?.path || busy.value) return
  // #ifdef H5
  if (mode.value === 'live' && navigator.onLine === false) {
    waitingForNetwork.value = true
    return
  }
  // #endif
  waitingForNetwork.value = false
  rememberDraft()
  scanPhoto.value = selected.path
  busy.value = true
  busyText.value = mode.value === 'preview' ? '正在保存本次观察…' : '正在上传并识别照片…'
  error.value = ''
  try {
    current.value = await upload('/api/cases', selected.path, { crop: selected.crop })
    clearComposer()
    lastPhotoCase.value = current.value
    viewPath.value = showResult(viewPath.value, current.value.id)
    selectedPhoto.value = null
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
  if (businessLoginRequired(mode.value, !!user.value)) {
    requestBusinessLogin('demo')
    return
  }
  if (busy.value) return
  busy.value = true
  busyText.value = '正在打开演示样例…'
  error.value = ''
  try {
    current.value = await request<CaseRecord>('/api/cases/demo', 'POST', { crop: crop.value })
    lastPhotoCase.value = current.value
    viewPath.value = showResult(viewPath.value, current.value.id)
    await refresh()
  } catch (value) {
    showError(value)
  } finally {
    busy.value = false
  }
}
async function openCase(id: string) {
  if (!user.value) {
    requestConsultationLogin('history', null, id)
    return
  }
  rememberDraft()
  busy.value = true
  busyText.value = '正在读取记录…'
  error.value = ''
  try {
    current.value = await request<CaseRecord>('/api/cases/' + id)
    restoreComposer()
    viewPath.value = openHistory(viewPath.value, current.value.id)
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
  if (emptyChat.value) return
  await nextTick()
  scrollAnchor.value = 'chat-end'
}
function openChat() {
  if (!current.value) return
  if (!user.value) {
    requestConsultationLogin('continue', null, undefined, current.value)
    return
  }
  viewPath.value = showChat(viewPath.value, current.value.id)
  scrollChat()
}
async function startConsultation(selectedCrop: Crop | null = null) {
  if (!user.value) {
    requestConsultationLogin('new', selectedCrop)
    return
  }
  if (busy.value) return
  rememberDraft()
  busy.value = true
  busyText.value = '正在新建对话…'
  error.value = ''
  try {
    current.value = await request<CaseRecord>('/api/consultations', 'POST', {
      crop: selectedCrop,
      location: location.value,
      stage: '不清楚',
    })
    clearComposer()
    if (!user.value) lastPhotoCase.value = null
    viewPath.value = openHistory(viewPath.value, current.value.id)
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
async function resumeQuestion() {
  const record = current.value
  if (!record?.pending_question || sending.value) return
  if (!user.value) {
    requestConsultationLogin('continue', null, undefined, current.value)
    return
  }
  const id = record.id,
    question = record.pending_question.id
  sending.value = true
  error.value = ''
  try {
    await request('/api/cases/' + id + '/resume', 'POST', {
      question_id: question,
      model: chatModel.value,
      thinking: chatThinking.value,
      web_search: chatWebSearch.value,
    })
    const updated = await request<CaseRecord>('/api/cases/' + id)
    if (current.value?.id === id) current.value = updated
    await refresh()
  } catch (value) {
    showError(value)
  } finally {
    sending.value = false
    scrollChat()
  }
}
async function chooseContext(value: ContextSuggestion, choice: { value: string; label: string }) {
  if (!current.value || sending.value) return
  const origin = current.value.id
  sending.value = true
  try {
    const id = current.value.id
    const updated = await request<CaseRecord>('/api/cases/' + id + '/context', 'POST', {
      [value.field]: choice.value,
    })
    if (current.value?.id === id) current.value = updated
  } catch (value) {
    showError(value)
  } finally {
    sending.value = false
  }
  if (current.value?.id !== origin) return
  showToast('种植信息已更新，后续回答会参考这些信息')
}
async function skipContext(field: ContextField) {
  if (!current.value || sending.value) return
  const id = current.value.id
  sending.value = true
  try {
    const updated = await request<CaseRecord>('/api/cases/' + id + '/context', 'POST', {
      skip_context_fields: [field],
    })
    if (current.value?.id === id) current.value = updated
  } catch (value) {
    showError(value)
  } finally {
    sending.value = false
  }
}
function chooseChatPhoto(source: 'album' | 'camera' = 'album') {
  if (!user.value) {
    requestConsultationLogin('continue', null, undefined, current.value)
    return
  }
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
      const context = chatPhotoContext(current.value)
      photoCrop.value = context.crop
      photoStage.value = context.stage
      photoVariety.value = context.variety
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
async function confirmChatPhoto(selectedCrop: Crop | null = photoCrop.value) {
  if (!user.value) {
    requestConsultationLogin('continue', null, undefined, current.value)
    return
  }
  if (!chatPhoto.value || busy.value || !selectedCrop) return
  photoCrop.value = selectedCrop
  if (!current.value || current.value.is_demo) await startConsultation(selectedCrop)
  if (!current.value) return
  scanPhoto.value = chatPhoto.value
  busy.value = true
  busyText.value = '正在调用图片识别模型…'
  error.value = ''
  try {
    current.value = await upload(`/api/cases/${current.value.id}/images`, chatPhoto.value, {
      crop: selectedCrop,
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
    viewPath.value = showChat(viewPath.value, current.value.id)
    await refresh()
  } catch (value) {
    showError(value)
    return
  } finally {
    busy.value = false
    scanPhoto.value = ''
  }
  showToast('照片已处理，可继续添加或发送问题。')
}
async function acceptDocument(path: string, name: string, size: number) {
  if (!user.value) {
    requestConsultationLogin('continue', null, undefined, current.value)
    return
  }
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
    viewPath.value = showChat(viewPath.value, current.value.id)
    showToast('资料已添加，可继续提问')
    await refresh()
  } catch (value) {
    showError(value)
  } finally {
    busy.value = false
  }
}
function chooseDocument() {
  if (!user.value) {
    requestConsultationLogin('continue', null, undefined, current.value)
    return
  }
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
  // #ifdef MP-WEIXIN
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
function openHistoryDrawer() {
  historyDrawerOpen.value = true
}
watch(isMobile, (mobile) => {
  if (!mobile) historyDrawerOpen.value = false
})
function clearComposer() {
  chatText.value = ''
  pendingDocuments.value = []
  pendingImages.value = []
}
function attach(kind: 'image' | 'document') {
  if (!user.value) {
    requestConsultationLogin('continue', null, undefined, current.value)
    return
  }
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
  if (!user.value) {
    requestConsultationLogin('continue', null, undefined, current.value)
    return
  }
  const text =
      raw.trim() ||
      (pendingImages.value.length
        ? imageQuestion(current.value) +
          (pendingDocuments.value.length ? '请同时结合刚添加的资料回答。' : '')
        : '请阅读刚添加的资料，提取与本次作物问题相关的信息。'),
    id = current.value.id
  const sentDraft = raw === chatText.value
  if (!messageAttempt || messageAttempt.text !== text || messageAttempt.caseId !== id)
    messageAttempt = {
      id: 'question-' + Date.now() + '-' + Math.random().toString(36).slice(2),
      text,
      caseId: id,
    }
  const requestId = messageAttempt.id
  sending.value = true
  pendingMessage.value = text
  if (sentDraft) chatText.value = ''
  error.value = ''
  scrollChat()
  try {
    await request(`/api/cases/${id}/messages`, 'POST', {
      text,
      request_id: requestId,
      model: chatModel.value,
      thinking: chatThinking.value,
      web_search: chatWebSearch.value,
      attachment_ids: pendingDocuments.value.map((file) => file.id),
      image_ids: pendingImages.value,
    })
    const updated = await request<CaseRecord>(`/api/cases/${id}`)
    messageAttempt = null
    drafts.save(id, {
      text: current.value?.id === id ? chatText.value : drafts.get(id).text,
      documents: [],
      images: [],
    })
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
function prepareQuestion(text: string) {
  if (!text || sending.value || busy.value) return
  if (chatText.value.trim()) {
    showToast('输入框已有草稿，请先发送或清空后再选择。')
    return
  }
  chatText.value = text
  rememberDraft()
  nextTick(() => composer.value?.focus())
  showToast('问题已放入输入框，可修改后发送。')
}
function askAgain(index: number) {
  if (current.value) prepareQuestion(questionForAnswer(current.value, index))
}
function shareAnswer(index: number) {
  const message = current.value?.messages[index]
  if (!message || message.role !== 'assistant') return
  uni.setClipboardData({
    data: answerShareText(message),
    showToast: false,
    success: () => showToast('回答和来源已复制，可粘贴到微信或其他应用分享。'),
    fail: () => showToast('暂时无法复制分享，请重试。'),
  })
}
function beginRename() {
  if (!current.value) return
  renameValue.value = conversationTitle(current.value)
  renameError.value = ''
  chatOptions.value = 'rename'
}
async function renameConversation() {
  const id = current.value?.id
  if (!id || !cleanRename.value || renaming.value) return
  renaming.value = true
  renameError.value = ''
  try {
    const updated = await request<CaseRecord>(`/api/cases/${id}/context`, 'POST', {
      conversation_title: cleanRename.value,
    })
    if (current.value?.id === id) current.value = updated
    if (retainedCase.value?.id === id) retainedCase.value = updated
    if (lastPhotoCase.value?.id === id) lastPhotoCase.value = updated
    chatOptions.value = null
    showToast('对话已重命名')
    await refresh()
  } catch (value) {
    renameError.value = value instanceof Error ? value.message : '保存失败，请重试'
  } finally {
    renaming.value = false
  }
}
async function openChatDetails(kind: 'info' | 'result') {
  chatOptions.value = null
  await nextTick()
  if (kind === 'result') inspectResult()
  else infoOpen.value = true
}
function copyConversation() {
  const record = current.value
  if (!record?.messages.length) return
  const transcript = record.messages.map(
    (message) => (message.role === 'user' ? '我' : '观叶助手') + '：' + answerCopyText(message),
  )
  chatOptions.value = null
  uni.setClipboardData({
    data: [conversationTitle(record), ...transcript].join('\n\n'),
    showToast: false,
    success: () => showToast('对话文字已复制'),
    fail: () => showToast('暂时无法复制，请重试'),
  })
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
    if (current.value?.id === id) {
      current.value = null
      viewPath.value = { ...viewPath.value, layers: [] }
    }
    if (lastPhotoCase.value?.id === id) lastPhotoCase.value = null
    deleteTarget.value = null
    await refresh()
    showToast('记录已删除')
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
function openPhotoConsultation() {
  startConsultation()
}
async function openConsultation() {
  if (!user.value) {
    requestConsultationLogin('new')
    return
  }
  if (current.value) {
    if (!viewPath.value.layers.length)
      viewPath.value = openHistory(viewPath.value, current.value.id)
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
  else choosePhoto(source, photoTarget.value)
}
function loginFromDrawer() {
  historyDrawerOpen.value = false
  requestConsultationLogin('history')
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
        'drawer-open': historyDrawerOpen,
      },
    ]"
    :style="appStyle"
  >
    <!-- #ifdef H5 -->
    <GlobalNavigation
      v-if="!isMobile"
      :active="tab"
      :chat="chatMode"
      @navigate="navigate"
      @consult="openConsultation"
    />
    <HistorySidebar
      v-if="!isMobile"
      :expanded="sidebarExpanded"
      :records="records"
      :user="user"
      :selected="current?.id"
      @open="openConversation"
      @new="startConsultation()"
      @login="requestConsultationLogin('history')"
      @toggle="sidebarExpanded = !sidebarExpanded"
    />

    <!-- #endif -->
    <view class="main-shell">
      <!-- #ifndef MP-WEIXIN -->
      <MobileHeader
        v-if="isMobile && (chatMode || tab !== 'profile')"
        :title="!chatMode && tab === 'home' ? '宛田观叶' : title"
        :page="tab"
        :compact="compactHeader"
        :chat="chatMode"
        :back-label="backLabel"
        :history-open="historyDrawerOpen"
        :safe-top="mobileSafeTop"
        :search="!chatMode && tab === 'history' && user ? query : undefined"
        :chat-options-open="!!chatOptions"
        @search="query = $event"
        @options="chatOptions = 'actions'"
        @home="navigate('home')"
        @back="mobileBack"
        @history="openHistoryDrawer"
      />
      <!-- #endif -->
      <!-- #ifdef H5 -->
      <WebWorkspaceHeader
        v-if="!isMobile"
        :title="title"
        :chat="chatMode"
        :back-label="backLabel"
        :options-open="!!chatOptions"
        :account-name="user?.name"
        @back="backView"
        @options="chatOptions = 'actions'"
        @login="openAuth()"
        @profile="navigate('profile')"
      />
      <!-- #endif -->
      <!-- #ifdef MP-WEIXIN -->
      <WeChatHeader
        v-if="!wechatProfile"
        :frame="wechatFrame"
        :compact="compactHeader"
        :title="wechatTitle"
        :native-title="nativeWeChatTitle"
        :chat="chatMode"
        :show-back="wechatBack"
        :back-label="wechatBackLabel"
        :show-history="chatMode || compactHeader"
        :search="wechatSearch"
        @search="query = $event"
        :history-open="historyDrawerOpen"
        :options-open="!!chatOptions"
        @home="navigate('home')"
        @back="mobileBack"
        @history="openHistoryDrawer"
        @options="chatOptions = 'actions'"
      />
      <!-- #endif -->
      <view v-if="error" class="error-strip" role="alert"
        ><text class="flex-one">{{ error }}</text
        ><button v-if="pendingCaseRecovery" class="text-button" @click="retryContinuedCase">
          重新载入本次识别</button
        ><button v-else-if="!online" class="text-button" @click="refresh">重试</button
        ><button class="icon-button" aria-label="关闭提示" @click="error = ''">×</button></view
      >
      <view v-if="busy" class="loading-strip" role="status"
        ><view class="spinner" /><text>{{ busyText || '正在保存…' }}</text></view
      >

      <view class="workspace">
        <view v-if="chatMode && current" class="case-area" :class="{ 'is-leaving': leavingChat }">
          <view class="chat-workspace" :style="chatWorkspaceStyle">
            <scroll-view
              scroll-y
              class="message-scroll"
              :scroll-into-view="scrollAnchor"
              :scroll-with-animation="true"
            >
              <view class="message-stream" :class="{ 'is-empty': emptyChat }">
                <RecognitionSummary
                  v-if="
                    currentReceipt?.image_received &&
                    (!current.messages.length || pendingImages.length)
                  "
                  :result="currentReceipt"
                  compact
                />
                <view v-if="emptyChat" class="chat-welcome"
                  ><view class="welcome-mark">🌱</view><text class="welcome-title">询问 AI</text
                  ><text class="muted">描述症状、询问种植管理，或添加照片进行识别。</text
                  ><view class="welcome-topics"
                    ><button
                      v-for="text in ['如何拍清楚症状？', '怎么看农药标签？', '生育期是什么意思？']"
                      :key="text"
                      @click="sendMessage(text)"
                    >
                      {{ text }} <text>↗</text>
                    </button></view
                  ><text v-if="mode === 'preview'" class="welcome-preview"
                    >离线演示使用本地资料，不连接 DeepSeek 或云端账户</text
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
                      >观叶助手
                      <text>{{
                        message.provider === 'deepseek'
                          ? 'AI 生成 · ' +
                            (message.model === 'deepseek-v4-pro'
                              ? 'DeepSeek V4 Pro'
                              : 'DeepSeek Flash') +
                            (message.thinking ? ' · 深度思考' : '')
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
                    ><ContentReference
                      v-if="message.role === 'assistant'"
                      :kind="
                        message.provider === 'deepseek'
                          ? 'ai'
                          : message.provider === 'recognition'
                            ? 'recognition'
                            : 'reference'
                      "
                    /><view v-if="message.attachments?.length" class="message-attachments"
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
                    ><ChatSuggestions
                      v-if="index === current.messages.length - 1 && message.role === 'assistant'"
                      :key="current.id + ':' + index"
                      :context="contextSuggestionFor(current, message)"
                      :photo="message.photo_suggestion"
                      :disabled="sending || busy"
                      @select="chooseContext"
                      @skip="skipContext"
                      @photo="openPhotoSources('chat')"
                    />
                    <button
                      v-if="
                        index === current.messages.length - 1 &&
                        message.provider === 'clarification' &&
                        current.pending_question &&
                        !sending
                      "
                      class="button secondary continue-question"
                      :disabled="sending"
                      @click="resumeQuestion"
                    >
                      继续回答原问题
                    </button>
                    <view v-if="message.role === 'assistant'" class="message-tools">
                      <button
                        v-for="source in message.sources"
                        :key="source.url"
                        class="source-chip"
                        @click="openSource(source)"
                      >
                        ↗ {{ source.title }}
                      </button>
                      <view class="answer-actions">
                        <button
                          class="message-action"
                          aria-label="复制回答"
                          @click="copyText(answerCopyText(message))"
                        >
                          <AppIcon name="copy" :size="15" /><text>复制</text>
                        </button>
                        <button
                          class="message-action"
                          aria-label="复制回答与来源以分享"
                          @click="shareAnswer(index)"
                        >
                          <AppIcon name="external" :size="15" /><text>复制分享</text>
                        </button>
                        <button
                          v-if="
                            message.provider !== 'clarification' &&
                            questionForAnswer(current, index)
                          "
                          class="message-action"
                          :disabled="sending || busy"
                          @click="askAgain(index)"
                        >
                          <text>再问一次</text>
                        </button>
                      </view>
                    </view>
                    <view
                      v-if="
                        index === current.messages.length - 1 &&
                        message.role === 'assistant' &&
                        !sending &&
                        suggestedQuestions(current, message).length
                      "
                      class="suggested-questions"
                    >
                      <text>继续了解</text>
                      <button
                        v-for="question in suggestedQuestions(current, message)"
                        :key="question"
                        :disabled="busy"
                        @click="prepareQuestion(question)"
                      >
                        {{ question }}<AppIcon name="plus" :size="13" />
                      </button>
                    </view>
                    <text v-if="message.notice" class="fine-print">{{ message.notice }}</text></view
                  >
                </view>
                <view v-if="sending && pendingMessage" class="message-row user"
                  ><text class="message-bubble pending-bubble">{{ pendingMessage }}</text></view
                >
                <view v-if="sending" class="responding"
                  ><view class="spinner" /><text>正在整理资料…</text></view
                >
                <view v-if="!emptyChat" id="chat-end" class="chat-end" />
              </view>
            </scroll-view>
            <view class="composer-dock"
              ><view class="composer-wrap"
                ><ChatComposer
                  ref="composer"
                  v-model="chatText"
                  :dark="resolvedTheme === 'dark'"
                  v-model:model="chatModel"
                  v-model:thinking="chatThinking"
                  v-model:web-search="chatWebSearch"
                  :attachments="pendingDocuments"
                  :images="pendingImagePreviews"
                  :disabled="sending || busy"
                  @send="sendMessage()"
                  @attach="attach"
                  @remove="removeAttachment"
                  @remove-image="removePendingImage"
                  @keyboard-height="receiveNativeKeyboard"
                  @limit="showToast('单条消息最多 12000 字，较长资料可作为文件上传')" /></view
            ></view>
          </view>
        </view>

        <DashboardHome
          v-if="tab === 'home'"
          v-show="!chatMode"
          v-model:section="homeSection"
          :mobile="isMobile"
          @consult="startConsultation()"
          :records="records"
          :cards="cards"
          :logged-in="!!user"
          @card="selectedCard = $event"
          @source="openSource"
          @capture="navigate('identify')"
          @open="openConversation"
          @history="navigate('history')"
          @login="requestConsultationLogin('history')"
        />
        <scroll-view v-if="tab !== 'home'" v-show="!chatMode" scroll-y class="page-scroll">
          <view :key="tab" class="page-content" :style="profilePageStyle">
            <template v-if="tab === 'identify'"
              ><PhotoCapture
                :crop="crop"
                :models="meta?.models || []"
                :busy="busy"
                :loading="refreshing || !meta"
                :last-result="lastPhotoCase"
                :desktop-web="desktopCapture"
                :paused-upload="pausedUpload"
                @retry-upload="startCase"
                @result="restoreResult"
                @crop="chooseCrop"
                @capture="choosePhoto"
                @identify-crop="openCropLookup"
                @resume="openPhotoConsultation"
            /></template>

            <template v-else-if="tab === 'history'">
              <view v-if="!user" class="panel empty-state login-empty"
                ><view class="empty-icon">🌾</view><text class="section-title">登录后查看记录</text
                ><text class="muted">登录后可拍照识别、询问 AI、查阅资料并保存记录。</text
                ><button
                  class="button primary"
                  @click="openAuth('登录后可保存并查看你的历史记录。')"
                >
                  登录</button
                ><button class="text-button" @click="navigate('identify')">去拍照 →</button></view
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
                  >
                  <!-- #ifdef H5 -->
                  <view v-if="!isMobile" class="history-tools">
                    <view class="search-field">
                      <AppIcon name="search" :size="18" />
                      <input
                        v-model="query"
                        aria-label="搜索历史记录"
                        placeholder="搜索作物、问题或备注"
                      />
                    </view>
                    <button class="button quiet" @click="startConsultation()">
                      <AppIcon name="new" :size="17" />新建对话
                    </button>
                  </view>
                  <!-- #endif -->
                </view>
                <view v-if="!filteredRecords.length" class="empty-state"
                  ><view class="empty-icon">🌱</view
                  ><text class="section-title">{{
                    records.length ? '没有匹配的记录' : '从第一次田间观察开始'
                  }}</text
                  ><text class="muted">{{
                    records.length
                      ? '试试其他关键词，或切换作物筛选。'
                      : '上传一张照片，或先体验一条演示记录。'
                  }}</text
                  ><button v-if="!records.length" class="button soft" @click="demo">
                    查看演示结果 ↗
                  </button></view
                ><view v-for="record in filteredRecords" :key="record.id" class="history-row"
                  ><button class="history-main" @click="openCase(record.id)">
                    <image :src="imageUrl(record)" mode="aspectFill" /><view class="flex-one"
                      ><text class="history-title">{{ conversationTitle(record) }}</text
                      ><text class="muted small"
                        >{{ record.crop_name }} · {{ dateLabel(record.updated_at) }}</text
                      ></view
                    ><text class="badge">{{ statusLabel(record.status) }}</text></button
                  ><button class="icon-button" aria-label="删除记录" @click="deleteTarget = record">
                    <AppIcon name="trash" :size="18" /></button></view
              ></view>
            </template>

            <template v-else-if="tab === 'profile'"
              ><UserCenter
                :user="user"
                :admin="isAdmin"
                :capsule-inset="wechatCapsuleInset"
                @login="openAuth()"
                @settings="openSettings"
                @admin="openAdmin"
                @logout="signOut"
            /></template>
            <template v-else-if="tab === 'settings'"
              ><UserSettings :show-back="!isMobile" @back="navigate('profile')"
            /></template>
            <template v-else
              ><KnowledgeLibrary :cards="cards" @open="selectedCard = $event" @source="openSource"
            /></template>
          </view>
        </scroll-view>
      </view>
      <NavigationDock
        v-if="isMobile && !chatMode"
        :active="tab"
        :keyboard-open="keyboardHeight > 0"
        @navigate="navigate"
      />
    </view>

    <UiDialog
      v-if="resultOpen && current && !authOpen"
      :title="inspecting ? '图片识别结果' : '本次识别'"
      :subtitle="current.crop_name"
      wide
      floating
      @close="backView"
    >
      <RecognitionResult
        :record="current"
        :receipt="currentReceipt"
        :busy="busy"
        @photo="viewPhoto"
        @source="openSource"
        @edit="editCase"
        @retry="retryRecognition"
      />
      <template #footer>
        <view v-if="!inspecting" class="result-footer">
          <button
            class="button quiet"
            :disabled="busy || current.images.length >= 6"
            @click="openPhotoSources('supplement')"
          >
            <AppIcon name="plus" :size="17" /><text>补充照片</text>
          </button>
          <button class="button primary" @click="openChat">
            <AppIcon name="chat" white :size="18" /><text>继续对话</text>
          </button>
        </view>
        <button v-else class="button quiet full-width" @click="backView">
          <AppIcon name="back" :size="17" /><text>返回对话</text>
        </button>
      </template>
    </UiDialog>
    <CropIdentificationDialog
      v-if="cropLookup"
      :ready="!!meta?.crop_recognition?.ready"
      :diagnosis-models="meta?.models || []"
      :desktop-web="desktopCapture"
      :busy="cropLookup.busy"
      :photo="cropLookup.photo"
      :result="cropLookup.result"
      :error="cropLookup.error"
      @close="cropLookup = null"
      @photo="choosePhoto($event, 'crop')"
      @select="useCropLookup"
    />
    <ScanProgress v-if="busy && scanPhoto" :src="scanPhoto" />
    <ConversationDrawer
      v-if="historyDrawerOpen"
      :records="records"
      :safe-top="drawerSafeTop"
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
      :reason="authReason"
      :continue-case-id="authIntent?.record?.id"
      @close="cancelAuth"
      @success="signedIn"
    />

    <ChatPhotoDialog
      v-if="photoDialogOpen"
      :photo="chatPhoto"
      :busy="busy"
      @close="photoDialogOpen = false"
      @confirm="confirmChatPhoto"
    />
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
          带着照片，开始对话 →
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
            label="作物生育期" /></view
        ><view class="form-field"
          ><text class="field-label">地区</text
          ><input v-model="editLocation" aria-label="种植地区" :maxlength="120" /></view
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
      v-if="chatMode && chatOptions && current"
      :title="chatOptions === 'rename' ? '重命名对话' : '对话选项'"
      floating
      :focus-target="chatOptions === 'rename' ? 'conversation-name-field' : ''"
      @close="!renaming && (chatOptions = null)"
    >
      <view v-if="chatOptions === 'actions'" class="chat-action-list">
        <button @click="beginRename"><AppIcon name="file" :size="18" /><text>重命名</text></button>
        <button @click="openChatDetails('info')">
          <AppIcon name="info" :size="18" /><text>种植信息</text>
        </button>
        <button v-if="current.images.length" @click="openChatDetails('result')">
          <AppIcon name="image" :size="18" /><text>识别结果</text>
        </button>
        <button v-if="current.messages.length" @click="copyConversation">
          <AppIcon name="copy" :size="18" /><text>复制对话文字</text>
        </button>
      </view>
      <view v-else id="conversation-name-field" class="conversation-name-field">
        <text class="field-label">对话名称</text>
        <input
          v-model="renameValue"
          aria-label="对话名称"
          type="text"
          :maxlength="50"
          :disabled="renaming"
          :adjust-position="false"
          confirm-type="done"
          @confirm="renameConversation"
        />
        <text v-if="renameError" class="form-error" role="alert">{{ renameError }}</text>
      </view>
      <template v-if="chatOptions === 'rename'" #footer>
        <button
          class="button primary full-width"
          :disabled="!cleanRename || renaming"
          @click="renameConversation"
        >
          {{ renaming ? '正在保存…' : '保存名称' }}
        </button>
      </template>
    </UiDialog>
    <UiDialog
      v-if="infoOpen && current"
      title="本次种植信息"
      :subtitle="conversationTitle(current)"
      @close="infoOpen = false"
      ><view class="settings-row"
        ><text>作物</text><text>{{ current.crop ? current.crop_name : '未填写' }}</text></view
      ><view class="settings-row"
        ><text>生育期</text
        ><text>{{
          !current.stage || current.stage === '不清楚' ? '未填写' : current.stage
        }}</text></view
      ><view v-if="current.location" class="settings-row"
        ><text>种植地区</text><text>{{ current.location }}</text></view
      ><view class="settings-row"
        ><text>建立时间</text><text>{{ dateLabel(current.created_at) }}</text></view
      ><text v-if="current.note" class="article-summary">{{ current.note }}</text
      ><view v-if="current.images.length" class="info-photos"
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
      title="删除这条记录？"
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
.main-shell {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
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
/* #ifdef H5 */
.history-tools {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 10px;
}
.history-tools > .button {
  flex-shrink: 0;
  white-space: nowrap;
}
/* #endif */
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
.message-stream.is-empty {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.welcome-preview {
  font-size: 11px;
  color: var(--muted);
}
.chat-action-list {
  display: grid;
  gap: 5px;
}
.chat-action-list > button {
  display: flex;
  align-items: center;
  min-height: 44px;
  gap: 11px;
  text-align: left;
  padding: 9px 12px;
  border-radius: 10px;
  color: var(--ink);
}
.chat-action-list > button:hover {
  background: var(--hover);
}
.chat-action-list > button:active {
  background: var(--pressed);
}
.conversation-name-field {
  display: grid;
  gap: 8px;
}
.conversation-name-field input {
  box-sizing: border-box;
  width: 100%;
  min-height: 44px;
  padding: 10px 12px;
  border: 1px solid var(--control-line);
  border-radius: 10px;
  background: var(--subtle);
  color: var(--ink);
}
.chat-welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  max-width: 510px;
  width: 100%;
  margin: 12px auto 25px;
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
.answer-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 3px;
  width: 100%;
}
.message-action {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  min-height: 40px;
  padding: 0 9px;
  border-radius: 9px;
  color: var(--muted);
  font-size: 11px;
}
.message-action:hover {
  background: var(--hover);
}
.message-action:active {
  background: var(--pressed);
  color: var(--ink);
}
.suggested-questions {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 7px;
  margin-top: 10px;
}
.suggested-questions > text {
  color: var(--muted);
  font-size: 10px;
}
.suggested-questions > button {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 40px;
  padding: 7px 11px;
  border-radius: 11px;
  background: var(--subtle);
  color: var(--muted);
  font-size: 12px;
  text-align: left;
}
.suggested-questions > button:hover {
  background: var(--hover);
}
.suggested-questions > button:active {
  background: var(--pressed);
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
  .page-content {
    padding: 25px;
  }
  .message-stream {
    padding-left: 30px;
    padding-right: 30px;
  }
}
@media (max-width: 760px) {
  .page-content {
    padding: 17px 16px 10px;
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
  .action-row {
    font-size: 13px;
  }
  .source-button {
    font-size: 11px;
    line-height: 1.9;
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
.experiment-badge {
  margin-left: 8px;
  font-size: 9px;
}
@media (max-width: 760px) {
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
.user .message-bubble {
  border-color: transparent;
  background: var(--subtle);
}
.source-chip {
  border-color: transparent;
  background: var(--surface);
}
.message-tools .copy-button {
  border-radius: 8px;
}
@media (max-width: 760px) {
  .main-shell {
    transition: transform 0.2s ease;
  }
  .drawer-open > .main-shell {
    transform: translateX(24px);
  }
  /* #ifdef H5 */
  .keyboard-open .composer-dock {
    transform: translateY(calc(-1 * var(--keyboard-inset, 0px)));
  }
  /* #endif */
  .composer-dock {
    padding: 8px 12px max(8px, env(safe-area-inset-bottom));
  }
  /* #ifdef H5 */
  .message-stream {
    padding-bottom: calc(14px + var(--keyboard-inset, 0px));
  }
  /* #endif */
  .case-area.is-leaving {
    opacity: 0;
    transform: translateX(9px);
    transition:
      opacity 0.13s ease,
      transform 0.13s ease;
    pointer-events: none;
  }
  .chat-workspace {
    animation: mobile-page-enter 0.16s ease;
  }
  .page-content {
    padding-top: 14px;
    animation: mobile-page-enter 0.16s ease;
  }
}
@keyframes mobile-page-enter {
  from {
    opacity: 0.5;
    transform: translateY(5px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
@media (prefers-reduced-motion: reduce) {
  .main-shell {
    transition: none;
  }
  .chat-workspace,
  .page-content {
    animation: none;
  }
  .case-area.is-leaving {
    transition: none;
  }
}
/* #ifndef H5 */
.chat-workspace {
  animation: none;
}
.composer-dock {
  position: relative;
  padding-bottom: calc(8px + var(--chat-safe-bottom, 0px));
}
.chat-workspace,
.composer-dock {
  transition: padding-bottom var(--chat-keyboard-duration, 0ms) ease-out;
}
.keyboard-open .composer-dock {
  padding-bottom: 8px;
}
@media (prefers-reduced-motion: reduce) {
  .chat-workspace,
  .composer-dock {
    transition: none;
  }
}
.main-shell {
  padding-top: 0;
  width: 100%;
}
/* #endif */
</style>
