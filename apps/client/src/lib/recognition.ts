import type { CaseRecord, RecognitionReceipt } from './api'
export function recognitionFor(record: CaseRecord): RecognitionReceipt | undefined {
  if (record.recognition) return record.recognition
  if (!record.images.length) return undefined
  return {
    image_received: true,
    image_count: record.images.length,
    status: record.status,
    outcome: 'model_unavailable',
    summary: '已收到照片，目前未连接识别服务，暂时没有图像判断结果。',
    model_version: null,
    disease_id: null,
    candidates: [],
    experimental: false,
    next_steps: ['识别服务恢复后重新上传照片'],
    image_results: record.images.map((image, index) => ({
      image_id: image.id,
      image_index: index + 1,
      status: 'needs_model',
      title: '已收到照片，识别服务暂不可用',
      model_version: null,
      candidates: [],
      quality_issues: [],
    })),
  }
}
export function imageQuestion(record: CaseRecord) {
  const receipt = recognitionFor(record)
  if (receipt?.outcome === 'quality_check_failed')
    return '这次照片的画质检查没有通过，请说明具体该怎样补拍。'
  if (receipt?.outcome === 'different_hypotheses')
    return '请分别解释各张照片的初步线索，以及下一步怎样核对，不要把不同照片合成一种病害。'
  if (receipt?.status === 'uncertain')
    return '照片已上传但目前还不能可靠判断，请结合逐张处理回执说明还要观察或补充什么。'
  return '请结合这组照片的逐张识别回执，解释已有线索、未判明的部分和下一步建议。'
}
