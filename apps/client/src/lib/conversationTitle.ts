import type { CaseRecord } from './api'

export function conversationTitle(record: CaseRecord) {
  if (record.conversation_title) return record.conversation_title
  const question = record.messages.find(
    (message) =>
      message.role === 'user' &&
      message.provider !== 'photo' &&
      !/^(这次咨询的作物|目前处于|请结合刚刚|照片已上传)/.test(message.text),
  )
  if (question) {
    const words = Array.from(question.text.trim().replace(/\s+/g, ' '))
    return words.length > 32 ? words.slice(0, 32).join('') + '…' : words.join('')
  }
  if (record.images.length) return record.title
  return record.crop ? record.crop_name + '咨询' : '新咨询'
}
