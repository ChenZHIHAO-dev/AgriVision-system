import { previewRequest, previewUpload, previewImage } from './preview'
import { asset } from './assets'
import { apiBase, dataMode, clientId, sessionHeaders } from './transport'
export { apiBase, setApiBase, dataMode, setDataMode, clientId } from './transport'
export type { DataMode } from './transport'
export type Crop = 'wheat' | 'maize' | 'peanut'
export type ChatModel = 'deepseek-flash' | 'deepseek-v4-pro'
export interface DocumentAttachment {
  id: string
  name: string
  size: number
  characters: number
  kind: 'document'
  extraction: 'ready' | 'requires-backend'
  created_at: string
  truncated?: boolean
}
export interface FollowUp {
  field: 'crop' | 'stage'
  prompt: string
  options: { value: string; label: string }[]
}
export interface Source {
  title: string
  url: string
  date: string
}
export interface KnowledgeCard {
  id: string
  crop: Crop | 'general'
  title: string
  category: string
  summary: string
  keywords: string[]
  actions: string[]
  sources: Source[]
}
export interface Product {
  id: string
  name: string
  ingredient: string
  formulation: string
  registration: string
  instructions: string
  label_url: string
}
export interface ImageEvidence {
  image_id: string
  image_index: number
  status: string
  title: string
  model_version: string | null
  candidates: { id: string; name: string; score: number }[]
  quality_issues: string[]
}
export interface RecognitionReceipt {
  image_received: boolean
  image_count: number
  status: string
  outcome: string
  summary: string
  model_version: string | null
  disease_id: string | null
  candidates: { id: string; name: string; score: number }[]
  experimental: boolean
  next_steps: string[]
  image_results?: ImageEvidence[]
}
export interface Message {
  role: 'user' | 'assistant'
  text: string
  created_at: string
  provider: string
  sources: Source[]
  products: Product[]
  notice?: string
  model?: ChatModel
  thinking?: boolean
  follow_up?: FollowUp
  recognition?: RecognitionReceipt
  web_search_used?: boolean
  attachments?: { id: string; name: string; kind: 'image' | 'document' }[]
}
export interface CaseRecord {
  id: string
  crop: Crop | null
  crop_name: string
  location: string
  stage: string
  note: string
  variety?: string
  documents?: DocumentAttachment[]
  experimental?: boolean
  recognition?: RecognitionReceipt
  created_at: string
  updated_at: string
  is_demo: boolean
  status: string
  title: string
  disease_id: string | null
  model_version: string | null
  candidates: { id: string; name: string; score: number }[]
  images: {
    id: string
    url?: string
    quality: { issues: string[]; width: number; height: number }
    created_at: string
  }[]
  messages: Message[]
  versions: { title: string; created_at: string }[]
  advice: { summary: string; actions: string[]; sources: Source[]; products: Product[] }
}
export interface Meta {
  version: string
  models: {
    crop: Crop
    name: string
    ready: boolean
    classes: number
    version: string | null
    experimental?: boolean
  }[]
  deepseek_configured: boolean
  knowledge_count: number
  product_count: number
}

function errorText(data: unknown): string {
  if (typeof data === 'object' && data && 'detail' in data && typeof data.detail === 'string')
    return data.detail
  return '操作未完成，请检查信息后重试'
}
export function request<T>(
  path: string,
  method: 'GET' | 'POST' | 'DELETE' = 'GET',
  data?: unknown,
): Promise<T> {
  if (dataMode() === 'preview') return previewRequest(path, method, data) as Promise<T>
  return new Promise((resolve, reject) =>
    uni.request({
      url: apiBase() + path,
      method,
      data: data as Record<string, unknown>,
      timeout: path.endsWith('/messages') ? 180000 : 35000,
      header: { ...sessionHeaders(), 'Content-Type': 'application/json' },
      success: (res) =>
        res.statusCode >= 200 && res.statusCode < 300
          ? resolve(res.data as T)
          : reject(new Error(errorText(res.data))),
      fail: () => reject(new Error('暂时连接不上本地服务，请确认后端已启动，或检查服务地址')),
    }),
  )
}
export function upload(
  path: string,
  filePath: string,
  formData: Record<string, string>,
): Promise<CaseRecord> {
  if (dataMode() === 'preview') return previewUpload(path, filePath, formData)
  return new Promise((resolve, reject) =>
    uni.uploadFile({
      url: apiBase() + path,
      filePath,
      name: 'file',
      formData,
      header: sessionHeaders(),
      timeout: 60000,
      success: (res) => {
        try {
          const result = JSON.parse(res.data)
          res.statusCode >= 200 && res.statusCode < 300
            ? resolve(result)
            : reject(new Error(errorText(result)))
        } catch {
          reject(new Error('服务响应无法读取，请重试'))
        }
      },
      fail: () => reject(new Error('附件上传失败，请检查网络并重试')),
    }),
  )
}
export function imageUrl(record: CaseRecord, imageId?: string) {
  if (record.id.startsWith('preview_')) return previewImage(record, imageId)
  const id = imageId || record.images[record.images.length - 1]?.id
  const provided = record.images.find((image) => image.id === id)?.url
  return provided?.startsWith('/api/')
    ? apiBase() + provided
    : asset(record.crop ? 'crops/' + record.crop + '.png' : 'icons/leaf.png')
}
