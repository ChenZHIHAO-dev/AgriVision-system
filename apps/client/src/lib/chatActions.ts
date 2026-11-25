import type { CaseRecord, Message } from './api'
import { imageQuestion, recognitionFor } from './recognition'

/** Prepare an editable question; callers must never submit it automatically. */
export function questionForAnswer(record: CaseRecord, index: number): string {
  const answer = record.messages[index]
  if (!answer || answer.role !== 'assistant') return ''
  if (answer.provider === 'recognition' && record.images.length) return imageQuestion(record)
  for (let previous = index - 1; previous >= 0; previous--) {
    const message = record.messages[previous]
    if (message.role !== 'user') continue
    if (message.provider === 'photo') return record.images.length ? imageQuestion(record) : ''
    return message.text.trim()
  }
  return ''
}

export function suggestedQuestions(record: CaseRecord, answer: Message): string[] {
  if (answer.provider === 'clarification') return []
  if (/农药|用药|混配|药剂|标签/.test(answer.text))
    return ['怎么看农药标签？', '用药前需要核对什么？']
  if (recognitionFor(record)?.image_received) return ['如何拍清楚症状？', '需要补充什么信息？']
  return ['如何拍清楚症状？', '怎么看农药标签？']
}

export function answerCopyText(message: Message): string {
  return message.role === 'assistant' && message.provider === 'deepseek'
    ? 'AI 生成\n' + message.text
    : message.text
}

/** Plain content for explicit user copying, without private case/image links. */
export function answerShareText(answer: Message): string {
  const sources = answer.sources
    .filter((source) => /^https?:\/\//.test(source.url))
    .map((source) => source.title + '：' + source.url)
  return [
    '宛田观叶 · 作物问答',
    answerCopyText(answer),
    sources.length ? '参考资料\n' + sources.join('\n') : '',
  ]
    .filter(Boolean)
    .join('\n\n')
}
