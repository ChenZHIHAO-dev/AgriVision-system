export type Crop = 'wheat' | 'maize' | 'peanut'
export interface Source { title: string; url: string; date: string }
export interface KnowledgeCard { id: string; crop: Crop | 'general'; title: string; category: string; summary: string; keywords: string[]; actions: string[]; sources: Source[] }
export interface Product { id: string; name: string; ingredient: string; formulation: string; registration: string; instructions: string; label_url: string }
export interface Message { role: 'user' | 'assistant'; text: string; created_at: string; provider: string; sources: Source[]; products: Product[]; notice?: string }
export interface CaseRecord {
  id: string; crop: Crop; crop_name: string; location: string; stage: string; note: string;
  created_at: string; updated_at: string; is_demo: boolean; status: string; title: string;
  disease_id: string | null; model_version: string | null;
  candidates: { id: string; name: string; score: number }[];
  images: { id: string; quality: { issues: string[]; width: number; height: number }; created_at: string }[];
  messages: Message[]; versions: { title: string; created_at: string }[];
  advice: { summary: string; actions: string[]; sources: Source[]; products: Product[] };
}
export interface Meta { version: string; models: { crop: Crop; name: string; ready: boolean; classes: number; version: string | null }[]; deepseek_configured: boolean; knowledge_count: number; product_count: number }

const defaultBase = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
export function apiBase(): string { return String(uni.getStorageSync('agrivision.api') || defaultBase).replace(/\/$/, '') }
export function setApiBase(url: string) {
  if (!/^https?:\/\/[^\s/?#]+(?::\d+)?(?:\/[^?#]*)?$/.test(url)) throw new Error('请输入有效的 http 或 https 服务地址')
  uni.setStorageSync('agrivision.api', url.replace(/\/$/, ''))
}
export function clientId(): string {
  let id = uni.getStorageSync('agrivision.client')
  if (!id) { id = 'av_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 14); uni.setStorageSync('agrivision.client', id) }
  return String(id)
}
function errorText(data: unknown): string {
  if (typeof data === 'object' && data && 'detail' in data && typeof data.detail === 'string') return data.detail
  return '操作未完成，请检查信息后重试'
}
export function request<T>(path: string, method: 'GET' | 'POST' | 'DELETE' = 'GET', data?: unknown): Promise<T> {
  return new Promise((resolve, reject) => uni.request({
    url: apiBase() + path, method, data: data as Record<string, unknown>, timeout: 35000,
    header: { 'X-Client-ID': clientId(), 'Content-Type': 'application/json' },
    success: res => res.statusCode >= 200 && res.statusCode < 300 ? resolve(res.data as T) : reject(new Error(errorText(res.data))),
    fail: () => reject(new Error('暂时连接不上本地服务，请确认后端已启动，或检查服务地址')),
  }))
}
export function upload(path: string, filePath: string, formData: Record<string, string>): Promise<CaseRecord> {
  return new Promise((resolve, reject) => uni.uploadFile({
    url: apiBase() + path, filePath, name: 'file', formData,
    header: { 'X-Client-ID': clientId() }, timeout: 60000,
    success: res => { try { const result = JSON.parse(res.data); res.statusCode >= 200 && res.statusCode < 300 ? resolve(result) : reject(new Error(errorText(result))) } catch { reject(new Error('服务响应无法读取，请重试')) } },
    fail: () => reject(new Error('图片上传失败，请检查网络并重试')),
  }))
}
export function imageUrl(record: CaseRecord, imageId?: string) {
  const id = imageId || record.images[record.images.length - 1]?.id
  return id ? apiBase() + '/api/cases/' + record.id + '/images/' + id + '?client_id=' + clientId() : '/static/crops/' + record.crop + '.png'
}
