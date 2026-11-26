import type { CaseRecord, DataMode, KnowledgeCard } from './api'

export function businessLoginRequired(mode: DataMode, loggedIn: boolean) {
  return mode === 'live' && !loggedIn
}

/** 启动元信息公开；真实业务资料仅在登录后读取。离线演示仍使用本地资料。 */
export async function loadPrivateWorkspace(
  fetch: <T>(path: string) => Promise<T>,
  mode: DataMode,
  loggedIn: boolean,
): Promise<{ records: CaseRecord[]; cards: KnowledgeCard[] }> {
  if (businessLoginRequired(mode, loggedIn)) return { records: [], cards: [] }
  const [history, knowledge] = await Promise.all([
    fetch<{ items: CaseRecord[] }>('/api/cases'),
    fetch<{ items: KnowledgeCard[] }>('/api/knowledge'),
  ])
  return { records: history.items, cards: knowledge.items }
}
