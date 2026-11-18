<script lang="ts">
// #ifdef H5
import { installViewportMetrics } from './lib/viewport'
// #endif
export default {
  onLaunch() {
    // #ifdef H5
    const enhance = () => {
      document.querySelectorAll<HTMLElement>('uni-button').forEach((button) => {
        const disabled =
          button.hasAttribute('disabled') && button.getAttribute('disabled') !== 'false'
        if (!button.hasAttribute('role')) button.setAttribute('role', 'button')
        button.setAttribute('aria-disabled', String(disabled))
        button.tabIndex = disabled ? -1 : 0
      })
      document
        .querySelectorAll<HTMLElement>('uni-input[aria-label], uni-textarea[aria-label]')
        .forEach((wrapper) =>
          wrapper
            .querySelector('input,textarea')
            ?.setAttribute('aria-label', wrapper.getAttribute('aria-label') || ''),
        )
    }
    new MutationObserver(enhance).observe(document.documentElement, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['disabled'],
    })
    document.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return
      const button = (event.target as HTMLElement)?.closest<HTMLElement>('uni-button')
      if (button && button.tabIndex === 0) {
        event.preventDefault()
        button.click()
      }
    })
    installViewportMetrics()
    enhance()
    // #endif
  },
}
</script>
<style>
@import './styles/theme.css';
</style>
