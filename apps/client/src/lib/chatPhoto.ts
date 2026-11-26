import type { CaseRecord, Crop } from './api'

/** 附图只能沿用当前记录的已知作物，不能继承拍照页全局选项。 */
export function chatPhotoContext(record: Pick<CaseRecord, 'crop' | 'stage' | 'variety'> | null) {
  return {
    crop: (record?.crop || null) as Crop | null,
    stage: record?.stage || '不清楚',
    variety: record?.variety || '',
  }
}
