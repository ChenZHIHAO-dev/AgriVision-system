export function resolveConnection(options: {
  href?: string
  savedMode?: unknown
  savedBase?: unknown
  environmentMode?: string
  environmentBase?: string
}) {
  let local = false,
    explicit = false,
    origin = ''
  try {
    const url = new URL(options.href || '')
    local =
      ['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname) &&
      ['http:', 'https:'].includes(url.protocol)
    origin = url.origin
    explicit = local && url.searchParams.get('mode') === 'live'
    local = local && url.port === '8000' && url.pathname === '/'
  } catch {}
  const mode = explicit
    ? 'live'
    : options.savedMode === 'live' || options.savedMode === 'preview'
      ? options.savedMode
      : options.environmentMode === 'live' || options.environmentMode === 'preview'
        ? options.environmentMode
        : local
          ? 'live'
          : 'preview'
  const base = explicit
    ? origin
    : typeof options.savedBase === 'string' && options.savedBase
      ? options.savedBase
      : local && mode === 'live'
        ? origin
        : options.environmentBase || 'http://127.0.0.1:8000'
  return { mode: mode as 'preview' | 'live', base, explicit }
}
