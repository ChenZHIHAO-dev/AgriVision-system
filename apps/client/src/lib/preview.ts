import type { CaseRecord, Crop, KnowledgeCard, Message, Meta } from './api'
import { user } from './auth'
import { asset } from './assets'
import knowledgeData from './knowledge.json'

export const previewCards = knowledgeData as KnowledgeCard[]
const cropNames = { wheat: '小麦', maize: '玉米', peanut: '花生' }
const exampleIds = { wheat: 'wheat_stripe_rust', maize: 'maize_southern_rust', peanut: 'peanut_leaf_spot' }
let guestRecords: CaseRecord[] = []
const stamp = () => new Date().toISOString()
const makeId = () => `preview_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`
function key() { return `agrivision.preview.records.${user.value?.id || 'guest'}` }
function read(): CaseRecord[] { return user.value ? uni.getStorageSync(key()) || [] : guestRecords }
function save(records: CaseRecord[]) {
  if (user.value) {
    try { uni.setStorageSync(key(), records.slice(0, 50)) }
    catch { throw new Error('此设备的存储空间不足，请先删除不需要的图片记录') }
  } else guestRecords = records
}
function clone<T>(value: T): T { return JSON.parse(JSON.stringify(value)) }
function put(record: CaseRecord) { save([record, ...read().filter(item => item.id !== record.id)]); return clone(record) }
function get(id: string) { const found = read().find(item => item.id === id); if (!found) throw new Error('这条记录已不存在，请返回列表刷新'); return clone(found) }
export function claimGuestRecords() {
  if (!user.value || !guestRecords.length) return
  save([...guestRecords, ...read()].filter((item, index, all) => all.findIndex(other => other.id === item.id) === index))
  guestRecords = []
}
export function clearGuestRecords() { guestRecords = [] }

function create(data: Record<string, string>, demo = false): CaseRecord {
  const crop = (data.crop || 'wheat') as Crop
  const card = demo ? previewCards.find(item => item.id === exampleIds[crop]) : null
  return {
    id: makeId(), crop, crop_name: cropNames[crop], location: data.location || '河南省 / 南阳市', stage: data.stage || '不清楚', note: data.note || '',
    created_at: stamp(), updated_at: stamp(), is_demo: demo, status: demo ? 'demo' : 'needs_model',
    title: card ? `${card.title} · 演示样例` : '图片已保存，等待模型接入', disease_id: card?.id || null, model_version: null,
    candidates: [], images: [], messages: [], versions: [],
    advice: { summary: card ? `这是演示样例的资料说明。${card.summary}` : '已记录这次田间观察。前端体验暂未连接图片识别服务，你可以继续描述症状并查阅相关资料。', actions: card?.actions || ['补充症状近照和整株照片', '记录出现时间、生育期和田间分布', '保留近期用药信息，便于后续核对'], sources: card?.sources || [], products: [] },
  }
}
function reply(record: CaseRecord, text: string): Message {
  let card = previewCards.find(item => item.id === record.disease_id)
  const scoped = previewCards.filter(item => item.crop === record.crop || item.crop === 'general')
  card = scoped.find(item => item.title.includes(text) || item.keywords.some(word => word.length > 2 && text.includes(word))) || card
  if (/拍照|拍摄|照片|拍清/.test(text)) card = previewCards.find(item => item.id === 'photo_guide')
  const medicine = /用药|药物|配方|剂量|用量|混配|农药|打药|喷什么|用什么药/.test(text)
  let answer: string
  if (medicine) answer = '目前还没有录入公司的产品标签资料。请先核对产品名称、有效成分和含量、剂型、适用作物与防治对象，以及标签用法。\n\n准备好完整标签、生育期和近期施药记录后，再由农技人员确认用量与混配方案。你可以先查看这次问诊中的田间检查建议。'
  else if (card) answer = `${record.is_demo ? '这是一条演示问诊。' : '目前还没有自动识别结论。'}以下是「${card.title}」的资料参考：\n\n${card.summary}\n\n${card.actions.map(action => '• ' + action).join('\n')}\n\n症状大约出现了多久？是零星发生还是成片出现？`
  else answer = '先把田间情况记录清楚 🌱\n\n• 症状出现在叶片、麦穗还是根茎部？\n• 大约出现了多久，是零星还是成片发生？\n• 近期是否施过药、灌过水或遇到连续降雨？\n\n可以再补一张症状近照和整株照片。前端体验中的回答来自本地资料，正式识别和智能对话服务后续接入。'
  return { role: 'assistant', text: answer, created_at: stamp(), provider: 'preview', sources: medicine ? [] : card?.sources || [], products: [] }
}
export async function previewRequest(path: string, method: string, raw?: unknown): Promise<unknown> {
  const data = (raw || {}) as Record<string, string>
  if (path === '/api/meta') return { version: '1.1.0-dev.1', models: Object.entries(cropNames).map(([crop, name]) => ({ crop: crop as Crop, name, ready: false, classes: 0, version: null })), knowledge_count: previewCards.length, product_count: 0, deepseek_configured: false } satisfies Meta
  if (path === '/api/knowledge') return { items: previewCards }
  if (path === '/api/cases' && method === 'GET') return { items: clone(read()) }
  if (path === '/api/cases/demo') return put(create(data, true))
  const match = path.match(/^\/api\/cases\/([^/]+)(?:\/(context|messages))?$/)
  if (!match) throw new Error('前端体验暂不支持这个操作')
  const record = get(match[1])
  if (method === 'DELETE') { save(read().filter(item => item.id !== record.id)); return { ok: true } }
  if (match[2] === 'context') Object.assign(record, { stage: data.stage, location: data.location, note: data.note })
  if (match[2] === 'messages') {
    if (!data.text?.trim()) throw new Error('请先填写咨询内容')
    record.messages.push({ role: 'user', text: data.text, provider: 'user', created_at: stamp(), sources: [], products: [] }, reply(record, data.text))
  }
  if (method === 'POST') { record.updated_at = stamp(); return put(record) }
  return record
}

async function localImage(path: string): Promise<string> {
  // #ifdef H5
  const response = await fetch(path)
  const blob = await response.blob()
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(blob.type)) throw new Error('请选择 JPG、PNG 或 WebP 图片')
  return await new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = () => {
      const scale = Math.min(1, 1280 / Math.max(image.width, image.height))
      const canvas = document.createElement('canvas'); canvas.width = Math.round(image.width * scale); canvas.height = Math.round(image.height * scale)
      const context = canvas.getContext('2d')
      if (!context) { reject(new Error('此浏览器暂不支持图片处理')); return }
      context.fillStyle = '#ffffff'; context.fillRect(0, 0, canvas.width, canvas.height); context.drawImage(image, 0, 0, canvas.width, canvas.height)
      resolve(canvas.toDataURL('image/jpeg', .78)); URL.revokeObjectURL(image.src)
    }
    image.onerror = () => reject(new Error('图片无法读取，请重新选择'))
    image.src = URL.createObjectURL(blob)
  })
  // #endif
  // #ifndef H5
  return await new Promise((resolve, reject) => uni.getFileSystemManager().readFile({ filePath: path, encoding: 'base64', success: result => resolve('data:image/jpeg;base64,' + result.data), fail: () => reject(new Error('图片读取失败，请重试')) }))
  // #endif
}
export async function previewUpload(path: string, file: string, data: Record<string, string>): Promise<CaseRecord> {
  const record = path === '/api/cases' ? create(data) : get(path.split('/')[3])
  if (record.is_demo) throw new Error('演示样例无法添加照片，请新建一次问诊')
  if (record.images.length >= 6) throw new Error('每次问诊最多保存 6 张照片')
  const url = await localImage(file)
  record.images.push({ id: makeId(), url, quality: { issues: [], width: 0, height: 0 }, created_at: stamp() })
  record.updated_at = stamp()
  return put(record)
}
export function previewImage(record: CaseRecord, id?: string) { return record.images.find(image => image.id === id)?.url || record.images[record.images.length - 1]?.url || asset(`crops/${record.crop}.png`) }
