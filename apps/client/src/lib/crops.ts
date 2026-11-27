import catalog from '../../../../knowledge/crops.json'

// 与 API 共用目录。新增作物只增加选择入口；模型就绪状态始终以 /api/meta 为准。
export type Crop = keyof typeof catalog
export const crops = Object.entries(catalog).map(([id, item]) => ({ id: id as Crop, ...item }))
export const cropNames = Object.fromEntries(crops.map((crop) => [crop.id, crop.name])) as Record<
  Crop,
  string
>
export const stages = Object.fromEntries(
  crops.map((crop) => [crop.id, ['不清楚', '暂不确定', ...crop.stages]]),
) as Record<Crop, string[]>
export const exampleIds = Object.fromEntries(
  crops.map((crop) => [crop.id, crop.demo_card]),
) as Record<Crop, string | null>

export function mentionedCrops(text: string): Crop[] {
  return crops
    .filter((crop) => [crop.name, ...crop.aliases].some((name) => text.includes(name)))
    .map((crop) => crop.id)
}
