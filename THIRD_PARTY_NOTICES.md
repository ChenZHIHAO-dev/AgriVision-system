# 第三方资源说明

## Lucide 图标

界面图标使用 lucide-static 1.73.0 的选定图标，经 scripts/build-icons.mjs 以统一 2.2 线宽生成 96px PNG。使用四组明确颜色适配浅色、深色和反色表面，避免在微信小程序中依赖本地 SVG 能力。

- 来源：https://lucide.dev/
- 包：lucide-static 1.73.0
- 许可：ISC；其中来源于 Feather 的图标同时包含 MIT 许可。
- 完整许可：[licenses/lucide-LICENSE](licenses/lucide-LICENSE)
- 构建工具：@resvg/resvg-js 2.6.2（仅开发依赖，不进入客户端运行时）
- 重建：npm ci 后运行 npm run icons。仅打包本项目使用的图标。

作物插图由项目脚本 scripts/generate_assets.py 生成。数据集和模型权重不随前端发布。


## 软件与模型的数据来源

根目录 LICENSE 仅规定项目自有部分的许可，不替换依赖包、图标和数据发布者的许可。安装的 Python/npm 依赖仍按各包附带条款使用；分发构建产物时继续保留适用的版权与许可说明。

模型代码复用 PyTorch、TorchVision、timm、scikit-learn 等实现。具体预训练权重以发布者的模型卡和数据条款为准；代码仓库的许可不能替代权重许可。

本地数据来源、版本和署名记录在 `data/<作物>/sources/<来源>/source.json`，公开来源说明见 [docs/data-sources.md](docs/data-sources.md)。包括 CC BY、CC BY-SA、仅研究用途或待确认等不同条件，不能统一覆盖为“禁止商用”。尤其 PlantVillage 的发布方使用 CC BY-SA 3.0 并在原论文中提出训练模型的许可要求，应在发布由它训练的权重前专门核对，不能直接套用根目录的非商业许可。

数据集、下载照片、个人记录及模型权重继续留在本地忽略目录，GitHub 只发布已检查的项目代码、文档和实验统计。
