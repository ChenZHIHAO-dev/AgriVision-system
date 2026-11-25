// #ifdef H5
import { defineComponent, h, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
// #endif

// Keep actual content between one and eight lines. A soft keyboard changes the
// available viewport, but must not change the text box's own sizing rules.
const LINE_HEIGHT = 24
const MAX_LINES = 8

// #ifdef H5
export default defineComponent({
  props: { modelValue: { type: String, default: '' }, disabled: Boolean },
  emits: ['update:modelValue', 'send', 'resize', 'limit'],
  setup(props, { emit, expose }) {
    const element = ref<HTMLTextAreaElement>()
    expose({ focus: () => element.value?.focus({ preventScroll: true }) })
    let lastHeight = 0
    let composing = false
    const resize = () => {
      const input = element.value
      if (!input) return
      const cap = LINE_HEIGHT * MAX_LINES
      input.style.height = '0px'
      // An empty textarea's scrollHeight can include a wrapped placeholder.
      // Placeholder copy must never make an empty composer taller.
      const contentHeight = input.value ? input.scrollHeight : LINE_HEIGHT
      const height = Math.min(cap, Math.max(LINE_HEIGHT, contentHeight))
      input.style.height = `${height}px`
      input.style.maxHeight = `${cap}px`
      input.style.overflowY = contentHeight > cap ? 'auto' : 'hidden'
      if (height !== lastHeight) {
        lastHeight = height
        emit('resize')
      }
    }
    onMounted(() => {
      resize()
      window.addEventListener('resize', resize)
    })
    onUnmounted(() => {
      window.removeEventListener('resize', resize)
    })
    watch(
      () => props.modelValue,
      () => nextTick(resize),
    )
    return () =>
      h('textarea', {
        ref: element,
        class: 'native-chat-input',
        rows: 1,
        value: props.modelValue,
        disabled: props.disabled,
        maxLength: 12000,
        'aria-label': '对话内容',
        placeholder: '描述问题，或添加照片…',
        onInput: (event: Event) => {
          emit('update:modelValue', (event.target as HTMLTextAreaElement).value)
          resize()
        },
        onPaste: (event: ClipboardEvent) => {
          const input = element.value
          const remaining =
            12000 -
            (props.modelValue.length - ((input?.selectionEnd || 0) - (input?.selectionStart || 0)))
          if ((event.clipboardData?.getData('text/plain').length || 0) > remaining) emit('limit')
          nextTick(resize)
        },
        onKeydown: (event: KeyboardEvent) => {
          if (
            window.innerWidth > 760 &&
            event.key === 'Enter' &&
            !event.shiftKey &&
            !event.isComposing &&
            !composing &&
            event.keyCode !== 229
          ) {
            event.preventDefault()
            emit('send')
          }
        },
        onCompositionstart: () => {
          composing = true
        },
        onCompositionend: () => {
          composing = false
          resize()
        },
      })
  },
})
// #endif
