/** Main sections own their state; temporary views only push or pop one level. */
export type MainPage = 'home' | 'identify' | 'profile' | 'settings' | 'history' | 'knowledge'
export type CaseLayer = 'result' | 'chat' | 'inspector'
export interface ViewPath {
  page: MainPage
  caseId: string | null
  layers: CaseLayer[]
}
export function initialPath(page: MainPage = 'identify'): ViewPath {
  return { page, caseId: null, layers: [] }
}
export function selectPage(path: ViewPath, page: MainPage): ViewPath {
  if (path.page === page) return path
  return { ...path, page, layers: [] }
}
export function showResult(path: ViewPath, caseId: string): ViewPath {
  return { page: 'identify', caseId, layers: ['result'] }
}
export function showChat(path: ViewPath, caseId: string): ViewPath {
  if (path.caseId === caseId && path.layers.includes('chat')) return path
  const parent =
    path.caseId === caseId && path.layers[path.layers.length - 1] === 'result'
      ? ['result' as const]
      : []
  return { ...path, caseId, layers: [...parent, 'chat'] }
}
export function showInspector(path: ViewPath): ViewPath {
  if (path.layers[path.layers.length - 1] !== 'chat') return path
  return { ...path, layers: [...path.layers, 'inspector'] }
}
export function popView(path: ViewPath): ViewPath {
  return { ...path, layers: path.layers.slice(0, -1) }
}
export function openHistory(path: ViewPath, caseId: string): ViewPath {
  return { ...path, caseId, layers: ['chat'] }
}
