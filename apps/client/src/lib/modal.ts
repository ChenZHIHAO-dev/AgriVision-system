/** Prevent focus entering the dimmed parent, including when one sheet opens over another. */
export function syncModalInert() {
  // #ifdef H5
  if (typeof document === 'undefined') return
  const roots = Array.from(
    document.querySelectorAll<HTMLElement>(
      '.av-app > .dialog-backdrop,.av-app > .conversation-drawer-backdrop',
    ),
  )
  const choice = document.querySelector('[data-choice-layer]')
  const top = choice || roots[roots.length - 1]
  for (const element of Array.from(
    document.querySelectorAll<HTMLElement>(
      '.av-app > .global-rail,.av-app > .history-sidebar-panel,.av-app > .main-shell,.av-app > .dialog-backdrop,.av-app > .conversation-drawer-backdrop',
    ),
  )) {
    element.inert = !!top && element !== top
  }
  // #endif
}
