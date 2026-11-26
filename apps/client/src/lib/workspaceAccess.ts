import type { CaseRecord, DataMode, KnowledgeCard } from './api'

export function businessLoginRequired(mode: DataMode, loggedIn: boolean) {
  return mode === 'live' && !loggedIn
}

/** 资料可公开阅读；私人记录仅登录后获取。离线演示继续使用本地样例。 */
export async function loadPrivateWorkspace(
  fetch: <T>(path: string) => Promise<T>,
  mode: DataMode,
  loggedIn: boolean,
): Promise<{ records: CaseRecord[]; cards: KnowledgeCard[] }> {
  const [history, knowledge] = await Promise.all([
    businessLoginRequired(mode, loggedIn)
      ? Promise.resolve({ items: [] as CaseRecord[] })
      : fetch<{ items: CaseRecord[] }>('/api/cases'),
    fetch<{ items: KnowledgeCard[] }>('/api/knowledge'),
  ])
  return { records: history.items, cards: knowledge.items }
}
