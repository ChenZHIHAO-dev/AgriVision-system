<script lang="ts">
export default {
  onLaunch() {
    // #ifdef H5
    const enhance = () => document.querySelectorAll<HTMLElement>('uni-button').forEach(button => {
      const disabled = button.hasAttribute('disabled') && button.getAttribute('disabled') !== 'false'
      button.setAttribute('role', 'button')
      button.setAttribute('aria-disabled', String(disabled))
      button.tabIndex = disabled ? -1 : 0
    })
    const observer = new MutationObserver(enhance)
    observer.observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ['disabled'] })
    document.addEventListener('keydown', event => {
      if (event.key !== 'Enter' && event.key !== ' ') return
      const button = (event.target as HTMLElement)?.closest<HTMLElement>('uni-button')
      if (button && button.tabIndex === 0) { event.preventDefault(); button.click() }
    })
    enhance()
    // #endif
  },
}
</script>
<style>
page { background: #f5f7f4; color: #203b30; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; font-size: 15px; line-height: 1.65; }
view, text, button, input, textarea { box-sizing: border-box; }
button { margin: 0; padding: 0; border: 0; background: transparent; font: inherit; line-height: inherit; color: inherit; border-radius: 0; }
button::after { border: 0; }
input, textarea { font: inherit; color: inherit; }
button[disabled] { background: #e5ebe6 !important; color: #829087 !important; opacity: .75; }
/* #ifdef H5 */
html, body, #app { margin: 0; min-height: 100%; }
button, uni-button, a, .clickable { cursor: pointer; }
:focus-visible { outline: 3px solid #85b79a; outline-offset: 3px; }
/* #endif */
</style>
