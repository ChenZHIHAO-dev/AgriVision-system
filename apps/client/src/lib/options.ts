import type { Crop } from './api'
export const crops: { id: Crop; name: string; caption: string }[] = [
  { id: 'wheat', name: '小麦', caption: '叶片 · 麦穗' },
  { id: 'maize', name: '玉米', caption: '叶部病害 · 虫害' },
  { id: 'peanut', name: '花生', caption: '叶斑 · 根茎' },
]
export const stages: Record<Crop, string[]> = {
  wheat: ['不清楚', '暂不确定', '苗期', '返青起身期', '拔节孕穗期', '抽穗扬花期', '灌浆成熟期'],
  maize: ['不清楚', '暂不确定', '苗期', '拔节期', '大喇叭口期', '抽雄吐丝期', '灌浆成熟期'],
  peanut: ['不清楚', '暂不确定', '苗期', '开花下针期', '结荚期', '饱果成熟期'],
}
export const regions: Record<string, Record<string, string[]>> = {
  河南省: {
    南阳市: [
      '暂不填写区县',
      '宛城区',
      '卧龙区',
      '邓州市',
      '唐河县',
      '方城县',
      '镇平县',
      '社旗县',
      '南召县',
      '内乡县',
      '淅川县',
      '新野县',
      '桐柏县',
      '西峡县',
    ],
    驻马店市: ['暂不填写区县'],
    信阳市: ['暂不填写区县'],
    洛阳市: ['暂不填写区县'],
    平顶山市: ['暂不填写区县'],
  },
  湖北省: { 襄阳市: ['暂不填写区县'], 十堰市: ['暂不填写区县'], 随州市: ['暂不填写区县'] },
  陕西省: { 商洛市: ['暂不填写区县'] },
}
export function dateLabel(value: string) {
  return new Date(value).toLocaleString('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}
export function statusLabel(status: string) {
  return (
    (
      {
        awaiting_image: '种植对话',
        demo: '演示样例',
        identified: '初步结果',
        uncertain: '待补充信息',
        needs_retake: '建议补拍',
        needs_model: '待模型识别',
        model_error: '识别待重试',
      } as Record<string, string>
    )[status] || '历史记录'
  )
}
