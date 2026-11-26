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

## DINOv2 实验权重

作物种类识别对照使用 Meta 发布的 DINOv2 ViT-B/14 with registers，通过 timm 加载。代码和官方模型权重为 Apache License 2.0；参见[官方模型卡](https://github.com/facebookresearch/dinov2/blob/main/MODEL_CARD.md)及[完整许可证](https://github.com/facebookresearch/dinov2/blob/main/LICENSE)。该权重保存在本地忽略缓存，不随本仓库或网页分发，项目自己的非商业条款不替换其原许可。实验配置记录下载 URL、SHA256 和实现版本。

## 花生原图及 AgML 镜像

Aishwarya Manvikar（Aishwarya M. P.）、A. Padmanabha Reddy 发布的 [Mendeley Data V3，DOI 10.17632/22p2vcbxfk.3](https://data.mendeley.com/datasets/22p2vcbxfk/3)使用 CC BY 4.0。本轮补取的 [Project-AgML 官方镜像](https://huggingface.co/datasets/Project-AgML/groundnut_leaf_disease_classification_2)引用同一数据 DOI，标注同一许可；镜像不是另一套独立授权，也不受本项目自有代码许可替代。原作者论文为 [Data in Brief 48 (2023), 109185](https://doi.org/10.1016/j.dib.2023.109185)。

镜像 revision、两份原包 SHA-256、原文件名和逐图哈希保留于 `data/peanut/sources/mendeley-22p2vcbxfk-v3/raw-agml/source.json` 与 `images.csv`。JPEG 字节未修改；本项目只增加来源审计、标签映射和外域清单。图片、打包副本及模型权重不随公开仓库分发；后续分发时须保留作者、来源、[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)及实际修改说明。原图 3,058 张与原文 3,059 张的差异、处理包隔离和人工抽查范围见[数据来源说明](docs/data-sources.md)。

## Cornell 手持玉米 NLB 数据

Tyr Wiesner-Hanks、Ethan L. Stewart、Nicholas Kaczmar、Chad DeChant、Harvey Wu、Rebecca J. Nelson、Hod Lipson、Michael A. Gore 发布的 [Image set for deep learning: field images of maize annotated with disease symptoms](https://doi.org/10.1186/s13104-018-3548-6)对应 [OSF p67rz 原库](https://osf.io/p67rz/)。原论文的权利说明将数据置于 [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/)，论文正文另为 CC BY 4.0；本项目保留作者与出处便于科研追溯，不将正文许可与数据许可混为一谈。

本轮仅取得 1,787 张手持原图的原始归档及专家标注，下载地址、发布方 MD5、本地 SHA-256、标注与数量差异保存在 `data/maize/sources/cornell-nlb-handheld-osf-p67rz/source.json`。原包不随公开仓库分发；统计、EXIF 方向和适用边界见[数据来源说明](docs/data-sources.md)。Purdue CD&S 目前只核验公开清单，数据许可尚未明确，未下载图像，不借用 Cornell 的许可。
