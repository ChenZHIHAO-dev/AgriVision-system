/** 只滚动弹窗正文；禁止 scrollIntoView 连带滚动页面并触发 iOS 键盘再次避让。 */
export function revealDialogInput(root: HTMLElement | null, target: Element | null) {
  if (!root || !(target instanceof HTMLElement) || !target.matches('input,textarea,select')) return
  const body = root.querySelector<HTMLElement>('.dialog-body')
  if (!body?.contains(target) || body.clientHeight <= 0) return
  const bounds = body.getBoundingClientRect()
  const field = target.getBoundingClientRect()
  // 已完整可见时不为了留白再滚动；切换账号/密码不会产生额外的微小跳动。
  if (field.top >= bounds.top && field.bottom <= bounds.bottom) return
  const fieldHeight = field.bottom - field.top
  const padding = Math.min(12, Math.max(0, (body.clientHeight - fieldHeight) / 2))
  const delta =
    fieldHeight > body.clientHeight
      ? field.top - bounds.top
      : field.top < bounds.top + padding
        ? field.top - bounds.top - padding
        : field.bottom > bounds.bottom - padding
          ? field.bottom - bounds.bottom + padding
          : 0
  if (delta)
    body.scrollTop = Math.max(
      0,
      Math.min(body.scrollHeight - body.clientHeight, body.scrollTop + delta),
    )
}
