import type { CaseRecord, Message } from './api'

// 只展示服务端建议，不在客户端重新判断哪些农业信息是“必填”。
// 历史消息中的建议不会因保存字段而改写，因此显示前排除已填写/跳过的字段。
export function contextSuggestionFor(record: CaseRecord, message: Message) {
  const suggestion = message.context_suggestion
  if (!suggestion || record.skipped_context_fields?.includes(suggestion.field)) return undefined
  const value = record[suggestion.field]
  return value && value !== '不清楚' ? undefined : suggestion
}
