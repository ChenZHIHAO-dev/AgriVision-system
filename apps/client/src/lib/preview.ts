import type { CaseRecord, Crop, KnowledgeCard, Message, Meta, FollowUp } from './api'
import { user } from './auth'
import { asset } from './assets'
import { stages } from './options'
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
  if (!record.crop) return { role:'assistant',text:'先确认一下，这次主要咨询哪种作物？选好后，我们结合你的问题继续说明。',created_at:stamp(),provider:'preview',sources:[],products:[],follow_up:clarification(record)! }
  let card = previewCards.find(item => item.id === record.disease_id)
  const scoped = previewCards.filter(item => item.crop === record.crop || item.crop === 'general')
  card = scoped.find(item => item.title.includes(text) || item.keywords.some(word => word.length > 2 && text.includes(word))) || card
  if (/拍照|拍摄|照片|拍清/.test(text)) card = previewCards.find(item => item.id === 'photo_guide')
  const medicine = /用药|药物|配方|剂量|用量|混配|农药|打药|喷什么|用什么药/.test(text)
  let answer: string
  if (medicine) answer = '目前还没有录入公司的产品标签资料。请先核对产品名称、有效成分和含量、剂型、适用作物与防治对象，以及标签用法。\n\n准备好完整标签、生育期和近期施药记录后，再由农技人员确认用量与混配方案。你可以先查看这次问诊中的田间检查建议。'
  else if (card) answer = `${record.is_demo ? '这是一条演示问诊。' : '目前还没有自动识别结论。'}以下是「${card.title}」的资料参考：\n\n${card.summary}\n\n${card.actions.map(action => '• ' + action).join('\n')}\n\n症状大约出现了多久？是零星发生还是成片出现？`
  else answer = '先把田间情况记录清楚 🌱\n\n• 症状出现在叶片、麦穗还是根茎部？\n• 大约出现了多久，是零星还是成片发生？\n• 近期是否施过药、灌过水或遇到连续降雨？\n\n可以再补一张症状近照和整株照片。前端体验中的回答来自本地资料，正式识别和智能对话服务后续接入。'
  return { role: 'assistant', text: answer, created_at: stamp(), provider: 'preview', sources: medicine ? [] : card?.sources || [], products: [],follow_up:clarification(record) || undefined }
}
function clarification(record:CaseRecord):FollowUp|null {
  if (!record.crop) return {field:'crop',prompt:'这次主要咨询哪种作物？',options:Object.entries(cropNames).map(([value,label])=>({value,label}))}
  if (!record.stage || record.stage==='不清楚') return {field:'stage',prompt:'目前处于哪个生育期？',options:[...stages[record.crop].filter(stage=>!['不清楚','暂不确定'].includes(stage)).map(stage=>({value:stage,label:stage})),{value:'暂不确定',label:'先不填写'}]}
  return null
}
export async function previewRequest(path: string, method: string, raw?: unknown): Promise<unknown> {
  const data = (raw || {}) as Record<string, string>
  if (path === '/api/meta') return { version: '1.2.0-dev.1', models: Object.entries(cropNames).map(([crop, name]) => ({ crop: crop as Crop, name, ready: false, classes: 0, version: null })), knowledge_count: previewCards.length, product_count: 0, deepseek_configured: false } satisfies Meta
  if (path === '/api/knowledge') return { items: previewCards }
  if (path === '/api/cases' && method === 'GET') return { items: clone(read()) }
  if (path === '/api/consultations') {
    const record=create(data)
    record.crop=(data.crop as Crop)||null; record.crop_name=record.crop ? cropNames[record.crop] : '作物待补充'
    record.title=(record.crop ? record.crop_name : '作物')+'种植咨询';record.status='awaiting_image';record.documents=[]
    return put(record)
  }
  if (path === '/api/cases/demo') return put(create(data, true))
  const remove = path.match(/^\/api\/cases\/([^/]+)\/attachments\/([^/]+)$/)
  if (remove && method==='DELETE') { const record=get(remove[1]); record.documents=(record.documents||[]).filter(file=>file.id!==remove[2]);put(record);return {ok:true} }
  const match = path.match(/^\/api\/cases\/([^/]+)(?:\/(context|messages))?$/)
  if (!match) throw new Error('前端体验暂不支持这个操作')
  const record = get(match[1])
  if (method === 'DELETE') { save(read().filter(item => item.id !== record.id)); return { ok: true } }
  if (match[2] === 'context') {
    for (const key of ['stage','location','note','variety'] as const) if (data[key]!==undefined) record[key]=data[key]
    if (data.crop) { record.crop=data.crop as Crop;record.crop_name=cropNames[record.crop];record.title=record.crop_name+'种植咨询' }
  }
  if (match[2] === 'messages') {
    if (!data.text?.trim()) throw new Error('请先填写咨询内容')
    if (!record.crop) { const mentions=(Object.entries(cropNames) as [Crop,string][]).filter(([,name])=>data.text.includes(name));if(mentions.length===1){record.crop=mentions[0][0];record.crop_name=mentions[0][1];record.title=record.crop_name+'种植咨询'} }
    if (record.crop && (!record.stage || record.stage==='不清楚')) { const found=stages[record.crop].find(stage=>stage!=='不清楚' && data.text.includes(stage));if(found)record.stage=found }
    const rawOptions=(raw||{}) as {attachment_ids?:string[];image_ids?:string[]}
    const files=(record.documents||[]).filter(file=>rawOptions.attachment_ids?.includes(file.id)).map(file=>({id:file.id,name:file.name,kind:'document' as const}))
    const images=record.images.filter(image=>rawOptions.image_ids?.includes(image.id)).map(image=>({id:image.id,name:'症状照片',kind:'image' as const}))
    const answer = reply(record, data.text)
    if (files.length) answer.text = '已记录附件名称。前端体验暂不解析文件正文，连接后端后可进行资料问答。\n\n' + answer.text
    record.messages.push({ role: 'user', text: data.text, provider: 'user', created_at: stamp(), sources: [], products: [],attachments:[...files,...images] }, answer)
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
  if (path.endsWith('/attachments')) {
    if ((record.documents||[]).length>=6) throw new Error('每次咨询最多添加 6 份资料')
    const filename=data.filename || '资料文件'
    if (!/\.(txt|md|pdf|docx)$/i.test(filename)) throw new Error('支持 TXT、MD、PDF、DOCX 资料')
    let size=0
    // #ifdef H5
    const blob=await (await fetch(file)).blob();size=blob.size
    if(size>8*1024*1024)throw new Error('文件不能超过 8MB')
    // #endif
    record.documents=record.documents||[]
    record.documents.push({id:makeId(),name:filename,size,characters:0,kind:'document',extraction:'requires-backend',created_at:stamp()})
    return put(record)
  }
  if (data.crop) { record.crop=data.crop as Crop;record.crop_name=cropNames[record.crop] }
  if (data.stage) record.stage=data.stage
  if (data.variety) record.variety=data.variety
  if (record.is_demo) throw new Error('演示样例无法添加照片，请新建一次问诊')
  if (record.images.length >= 6) throw new Error('每次问诊最多保存 6 张照片')
  const url = await localImage(file)
  record.images.push({ id: makeId(), url, quality: { issues: [], width: 0, height: 0 }, created_at: stamp() })
  record.status='needs_model';record.title='图片已保存，等待模型接入'
  record.updated_at = stamp()
  return put(record)
}
export function previewImage(record: CaseRecord, id?: string) { return record.images.find(image => image.id === id)?.url || record.images[record.images.length - 1]?.url || asset(record.crop ? `crops/${record.crop}.png` : 'icons/leaf.png') }
