import { defineComponent, h, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

// H5 uses a real textarea. The uni-app auto-height wrapper lets pasted content
// escape a CSS max-height; a bounded native scroll area avoids that failure.
export default defineComponent({
  props: { modelValue: { type: String, default: '' }, disabled: Boolean },
  emits: ['update:modelValue', 'send', 'resize', 'limit'],
  setup(props, { emit }) {
    const element = ref<HTMLTextAreaElement>()
    let lastHeight = 0
    let composing = false
    const resize = () => {
      const input = element.value
      if (!input) return
      const cap = Math.min(180, Math.max(64, (window.visualViewport?.height || window.innerHeight) * .28))
      input.style.height = '0px'
      const height = Math.min(cap, Math.max(30, input.scrollHeight))
      input.style.height = `${height}px`
      input.style.maxHeight = `${cap}px`
      input.style.overflowY = input.scrollHeight > height ? 'auto' : 'hidden'
      if (height !== lastHeight) { lastHeight = height; emit('resize') }
    }
    onMounted(() => { resize(); window.addEventListener('resize', resize); window.visualViewport?.addEventListener('resize', resize) })
    onUnmounted(() => { window.removeEventListener('resize', resize); window.visualViewport?.removeEventListener('resize', resize) })
    watch(() => props.modelValue, () => nextTick(resize))
    return () => h('textarea', {
      ref: element, class: 'native-chat-input', rows: 1, value: props.modelValue,
      disabled: props.disabled, maxLength: 12000, 'aria-label': '咨询内容',
      placeholder: '描述作物情况，或添加照片、资料继续问…',
      onInput: (event: Event) => { emit('update:modelValue', (event.target as HTMLTextAreaElement).value); resize() },
      onPaste: (event: ClipboardEvent) => {
        const input = element.value
        const remaining = 12000 - (props.modelValue.length - ((input?.selectionEnd || 0) - (input?.selectionStart || 0)))
        if ((event.clipboardData?.getData('text/plain').length || 0) > remaining) emit('limit')
        nextTick(resize)
      },
      onKeydown: (event: KeyboardEvent) => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && !composing && event.keyCode !== 229) { event.preventDefault(); emit('send') } },
      onCompositionstart: () => { composing = true },
      onCompositionend: () => { composing = false; resize() },
    })
  },
})
