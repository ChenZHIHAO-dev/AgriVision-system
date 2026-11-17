# 第三方资源说明

## Lucide 图标

界面图标使用 lucide-static 1.73.0 的选定图标，经 scripts/build-icons.mjs 以统一 1.8 线宽生成 96px PNG。使用四组明确颜色适配浅色、深色和反色表面，避免在微信小程序中依赖本地 SVG 能力。

- 来源：https://lucide.dev/
- 包：lucide-static 1.73.0
- 许可：ISC；其中来源于 Feather 的图标同时包含 MIT 许可。
- 完整许可：[licenses/lucide-LICENSE](licenses/lucide-LICENSE)
- 构建工具：@resvg/resvg-js 2.6.2（仅开发依赖，不进入客户端运行时）
- 重建：npm ci 后运行 npm run icons。仅打包本项目使用的图标。

作物插图由项目脚本 scripts/generate_assets.py 生成。数据集和模型权重不随前端发布。
