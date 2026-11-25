# 小麦数据处理、训练与本地联调清单

更新于 2026-11-26。本轮使用 Windows 本机现有的 `.venv`，固定数据目录为 `data/wheat-leaf-spike-03`。**预处理已完成；七组完整实验正在执行，结果集中在 `artifacts/experiments/wheat-study`。**

## 0. 先看运行顺序

| 步骤 | 做什么 | 是否保存图片 |
| --- | --- | --- |
| 1. 筛选、预处理，已完成 | 核验照片、整理方向、等比缩图、查重、按采集组划分训练/验证/测试 | 工作图保存在 `data/wheat-leaf-spike-03/images` |
| 2. 数据增强，在训练读取时执行 | 随机翻转、旋转、颜色变化；可比较轻微模糊、压缩和噪声 | 仅存在内存，直接交给这一批训练 |
| 3. 模型训练 | 从 ImageNet 预训练权重开始，先适配分类头，再全网微调 | 保存权重、配置、逐轮指标和曲线 |
| 4. 评估 | 按验证集选择模型；校准后报告留出测试集表现 | 保存逐图预测、混淆矩阵和指标 |
| 5. 本地联调 | 后端加载选中权重，网页通过 HTTP API 上传照片 | 后端保存临时记录，模型保持常驻 |

先在 PowerShell 进入项目目录。以下命令均使用这一目录和同一个虚拟环境，无需新建环境。

```powershell
cd F:\college\AgriVision
```

## 1. 当前数据与筛选

本轮共有 **6,455 张照片、8 个类别、1,290 个采集组**。训练 4,621 张、验证 981 张、测试 853 张。同一采集组留在同一划分中。各轮模型比较固定使用这些划分，增强只作用于训练集。

| 类别 | 训练 | 验证 | 测试 | 合计 |
| --- | ---: | ---: | ---: | ---: |
| 小麦条锈病 | 727 | 217 | 98 | 1,042 |
| 小麦叶锈病 | 539 | 127 | 80 | 746 |
| 小麦白粉病 | 530 | 147 | 121 | 798 |
| 小麦赤霉病 | 1,159 | 232 | 214 | 1,605 |
| 小麦颖枯病 | 307 | 42 | 58 | 407 |
| 小麦黄矮病 | 300 | 52 | 56 | 408 |
| 健康参考 | 815 | 112 | 174 | 1,101 |
| 小麦壳针孢叶枯病 | 244 | 52 | 52 | 348 |

来源为河南原阳、MSWDD2022 和 JIC。这里的健康参考表示这组标签中的健康图，实际识别时仍需考虑模型未覆盖的症状。筛选表中仍有待复核项目，当前工作集没有被逐张人工确认过。来源、许可、别名和排除原因见 [数据来源](data-sources.md)。

打开工作图，可以按类别查看：

```powershell
explorer F:\college\AgriVision\data\wheat-leaf-spike-03\images
```

| 文件 | 怎么使用 |
| --- | --- |
| `images/<类别 ID>/` | 查看工作照片 |
| `sources.csv` | 用工作图文件名追溯原图、来源和拍摄部位 |
| `manifest.csv` | 每张图的类别、采集组、训练/验证/测试归属 |
| `labels.json` | 模型实际使用的标签顺序与中文名称 |
| `manifest.report.json` | 各类数量、分辨率、来源和排除原因 |

工作图长边不超过 1,024 像素，保持原有长宽比。因此 81 种分辨率是正常的；统一成模型输入尺寸在读图时完成。当前模型使用等比缩放并补边，避免将长叶片或麦穗直接拉成方形。

如需继续筛图，打开这张表，修改后保存为 CSV UTF-8：

```powershell
Invoke-Item F:\college\AgriVision\data\wheat-review\leaf-spike-review.csv
```

`decision=keep` 是保留候选，`drop` 是排除，空白是待复核。`label` 是类别 ID；`class_name`、`part`、`note` 辅助核对。照片编号本身不决定标签。下面只检查筛选表，不改变现有工作图：

```powershell
.\.venv\Scripts\python.exe -m ml.agrivision_ml.preprocessing.wheat_review --review data/wheat-review/leaf-spike-review.csv --check
```

本轮七组实验执行期间保持 `03` 不变。筛选表的修改不会自动改写已经生成的 `03`。后续确认数据修改后统一更新当前工作集和划分，再启动新一组对照；不要为每次训练复制一份数据。

## 2. 数据增强在哪里，参数什么意思

增强代码集中在 [augmentation.py](../ml/agrivision_ml/augmentation.py)。训练入口 [train.py](../ml/agrivision_ml/train.py) 的 `Images` 负责读图，再调用它。

- `--resize letterbox`：等比缩放并居中补边，保持叶片和麦穗的形状。训练、验证、测试、接口推理共同读取这个配置。
- `--augmentation light`：水平翻转、±10° 旋转，亮度/对比度幅度 0.12、饱和度幅度 0.10。
- `--augmentation field`：小幅平移（最多宽高的 3%）、0.95–1.05 倍缩放、±10° 旋转和上述颜色变化；再以 15% 概率选择一种成像退化。
- 退化候选：3×3 高斯模糊（σ=0.1–0.7）、JPEG 质量 75–95，或高斯噪声 σ=3/255。最后一种相当于 8 位像素大约 3 个灰度级的标准差。每次至多抽一种退化，避免强烈叠加后掩盖病斑。

这些是待比较的轻量起点，具体收益由第 1、2 组实验决定。第 2 组同时改变小幅几何扰动和成像退化，因此结果说明的是整套增强方案的差别，不能单独归因于噪声。实现复用 TorchVision/Pillow 的标准变换。 [TorchVision 变换说明](https://docs.pytorch.org/vision/stable/transforms.html)

示例图：[原图、轻增强与田间增强对照](../artifacts/experiments/wheat-study/augmentation-preview.png)。

**数据量不需要靠落盘复制补成一样。** 当前训练每个 epoch 遍历全部 4,621 张训练照片。类别不平衡通过损失权重处理，第 5 组另外比较平方根权重：原逆频率权重给稀少类更大的学习权重；开平方会减轻这种放大程度，观察误报和逐类召回的变化。这与抽样重复照片是两种不同操作。

## 3. 运行一组完整训练

本轮机器为 RTX 3060 Laptop 6 GiB，使用 BF16 混合精度，每批 16 张，先冻结骨干 2 个 epoch，再全网微调。原有数据和模型缓存都放 F 盘。

先在同一 PowerShell 窗口指定权重缓存：

```powershell
$env:TORCH_HOME = 'F:\college\AgriVision\.cache\torch'
```

下面是第一组实验的完整命令，**已有运行结果时用于阅读和复现，不要对正在运行或已保存的结果目录重复执行**。每次训练只有实验结果目录不同，数据目录仍固定为 `03`。

```powershell
.\.venv\Scripts\python.exe -m ml.agrivision_ml.train --data-root data/wheat-leaf-spike-03/images --manifest data/wheat-leaf-spike-03/manifest.csv --labels data/wheat-leaf-spike-03/labels.json --output artifacts/experiments/wheat-study/01-convnext-light/wheat --architecture convnext_tiny --device cuda --input-size 224 --resize letterbox --augmentation light --batch-size 16 --lr 0.0001 --freeze-epochs 2 --precision bf16 --epochs 20 --patience 6 --workers 0
```

| 参数 | 作用，以及改哪里 |
| --- | --- |
| `--architecture convnext_tiny` | 选择模型；构建代码在 `model.py` |
| `--input-size 224` | 输入 RGB 方图边长；`letterbox` 保持原图比例并补边 |
| `--augmentation light` | 选择增强方案；具体强度在 `augmentation.py` |
| `--batch-size 16` | 每次更新读 16 张；本轮每个 epoch 共 289 次参数更新 |
| `--lr 0.0001` | AdamW 初始学习率，之后按余弦调度降低 |
| `--freeze-epochs 2` | 前两轮适配八类分类头，随后训练整个网络 |
| `--precision bf16` | 当前显卡支持的混合精度；较老显卡可改 `fp32` 或 `amp` |
| `--epochs 20 --patience 6` | 最多 20 轮；验证 Macro-F1 连续 6 轮未改善则早停 |
| `--grad-clip 1` | 默认梯度裁剪阈值，限制单次更新过大；记录裁剪前范数供检查 |
| `--class-weight-power 1` | 默认逆频率类别权重；第 5 组比较 `0.5` |
| `--freeze-bn` | 可选，固定 BatchNorm 运行统计；本轮 EfficientNetV2 使用它 |
| `--workers 0` | 当前 Python 进程读图，便于 Windows 本机调试 |
| `--output` | 结果目录；末尾 `wheat` 与 API 按作物加载的目录结构对应 |

只查看所有可选参数，不会开始训练：

```powershell
.\.venv\Scripts\python.exe -m ml.agrivision_ml.train --help
```

## 4. 查看每轮训练结果

```powershell
explorer F:\college\AgriVision\artifacts\experiments\wheat-study
```

每个实验的 `wheat` 子目录包含：

| 产物 | 阅读方法 |
| --- | --- |
| `training-curves.png` | 训练/验证 loss 和准确率曲线，每个 epoch 更新 |
| `training.json` | 逐轮 loss、准确率、Macro-F1、混淆矩阵、耗时、学习率 |
| `weights.pt` | 验证 Macro-F1 最佳的参数 |
| `last-weights.pt` | 最后一轮参数，用于分析训练后期异常 |
| `metadata.json` | 架构、类别、尺寸规则、增强、最佳轮次、配置、数据摘要和代码提交 |
| `predictions-val.csv` / `predictions-test.csv` | 每张图的真实类别、预测、分数、采集组和来源，方便定位错图 |
| `confusion-val.png` / `confusion-test.png` | 左图是张数，右图是按真实类别归一化的召回 |
| `evaluation-val.json` / `evaluation-test.json` | 总体、逐类、按来源和阈值筛选后的指标 |

`train_images_seen=4621` 表示这一轮完整遍历了训练集。`max_gradient_norm` 是裁剪前最大梯度范数，结合 loss 与学习率判断更新是否异常。最佳轮次保存在 `metadata.json` 的 `validation.epoch`。

## 5. 校准、测试和单图推理

训练完成后，先在验证集调温度和结果阈值。以下以第一组目录说明；查看其他实验时只替换 `--bundle` 后的目录。温度校准不改变第一候选排序，用于调整分数和给出明确结果的覆盖率。

```powershell
.\.venv\Scripts\python.exe -m ml.agrivision_ml.calibrate --bundle artifacts/experiments/wheat-study/01-convnext-light/wheat --data-root data/wheat-leaf-spike-03/images --manifest data/wheat-leaf-spike-03/manifest.csv --device cuda
```

生成 853 张留出测试照片的完整报告和混淆矩阵：

```powershell
.\.venv\Scripts\python.exe -m ml.agrivision_ml.experiment_report --bundle artifacts/experiments/wheat-study/01-convnext-light/wheat --data-root data/wheat-leaf-spike-03/images --manifest data/wheat-leaf-spike-03/manifest.csv --split test --device cuda
```

把下面的照片路径换成自己的实际路径，运行一次单张推理。用 CPU 时将末尾 `cuda` 改成 `cpu`：

```powershell
.\.venv\Scripts\python.exe -m ml.agrivision_ml.inference --bundle artifacts/experiments/wheat-study/01-convnext-light/wheat --image "F:\photos\wheat-sample.jpg" --device cuda
```

验证集用于模型和方法选择，测试集用于报告最终表现。七组中的后两种架构在查看前五组测试分数之前已确定，仍只按验证 Macro-F1 选择。已重复查看过的测试集不能替代未来新田块、新季节照片的独立验证。

## 6. 读代码的顺序

| 想理解什么 | 文件与入口 |
| --- | --- |
| 筛选表如何生成工作集 | [wheat_review.py](../ml/agrivision_ml/preprocessing/wheat_review.py) 的 `build_dataset()` |
| 校正方向、等比缩图 | [images.py](../ml/agrivision_ml/preprocessing/images.py) |
| 查重、采集组和划分 | [manifest.py](../ml/agrivision_ml/preprocessing/manifest.py)、[groups.py](../ml/agrivision_ml/preprocessing/groups.py)、[splits.py](../ml/agrivision_ml/preprocessing/splits.py) |
| 模型架构、分类头替换 | [model.py](../ml/agrivision_ml/model.py) 的 `build_model()`、`classification_head()` |
| 尺寸与在线增强 | [augmentation.py](../ml/agrivision_ml/augmentation.py) |
| 读图、反向传播、冻结、早停 | [train.py](../ml/agrivision_ml/train.py) 的 `Images` 和 `train()` |
| loss/acc 曲线 | [training_curves.py](../ml/agrivision_ml/training_curves.py) |
| 分数校准 | [calibrate.py](../ml/agrivision_ml/calibrate.py) |
| 逐图评估、来源统计和混淆矩阵 | [experiment_report.py](../ml/agrivision_ml/experiment_report.py) |
| 部署共用的读权重与推理 | [inference.py](../ml/agrivision_ml/inference.py) 的 `Predictor` |
| API 的按作物缓存与识别 | [models.py](../services/api/app/models.py) 的 `ModelRegistry` |

Python 版本、训练依赖和缓存设置分别见 [版本文件](../.python-version)、[requirements-ml.txt](../requirements-ml.txt)、[uv.toml](../uv.toml)。修改增强或模型构建前，先看对应文件的中文注释；训练主循环负责调用这些独立模块。

## 7. 本轮七组实验与历史问题

原 MobileNetV4-Conv-Small 是约 250 万参数的 CNN，八类训练最佳第 8 轮验证准确率 85.93%、Macro-F1 82.56%。随后 loss 波动并升高，第 13 轮验证准确率 69.93%、loss 19.762。小批次 BatchNorm、解冻后更新幅度和难例分数均值得检查；历史末轮没有留权重，不能认定只有一个原因。已保存的第 8 轮复评为 843/981 正确。BN 统计重估对照只小幅改变准确率，也不足以解释全部下降。

本轮改善输入几何、较低学习率、梯度裁剪、保留末轮权重，并比较以下成熟网络。每组从 ImageNet 权重重新开始，种子 42，每批 16 张，最多 20 个完整 epoch。所有结果统一放在 `artifacts/experiments/wheat-study`。

| 实验目录 | 架构或变化 | 要回答的问题 |
| --- | --- | --- |
| `01-convnext-light` | ConvNeXt-Tiny，224，轻增强 | 中等规模卷积模型基线 |
| `02-convnext-field` | 同一模型和尺寸，田间增强 | 轻微成像退化与空间扰动是否有收益 |
| `03-efficientnetv2` | EfficientNetV2-S，固定 BN 统计 | 比较另一种 CNN，采用前两组较好的增强 |
| `04-resolution320` | 前三组较好架构，尺寸提高到 320 | 小病斑细节是否受益 |
| `05-weight-balance` | 前四组较好方案，类别权重开平方 | 减弱稀少类损失权重是否改善混淆 |
| `06-swin-transformer` | Swin-T，224 | 比较窗口注意力 Transformer |
| `07-convnext-small` | ConvNeXt-Small，224 | 更大一级卷积模型是否有收益 |

第 6、7 组沿用前两组中较好的增强。`study.json` 记录每组完整训练命令、调整理由和实际参数；`summary.json` 记录结果和验证集选中的模型。实验尚在运行时，这些文件只包含已产生的内容。

ConvNeXt 使用卷积与 LayerNorm，Swin 使用分层窗口自注意力；两者不依赖普通 BatchNorm 的跨批运行统计。EfficientNetV2 由 Fused-MBConv 和 MBConv 组成，仍是 CNN。参数规模需与数据、预训练和正则化一起比较，并非越大必然越准确。 [ConvNeXt · CVPR 2022](https://openaccess.thecvf.com/content/CVPR2022/html/Liu_A_ConvNet_for_the_2020s_CVPR_2022_paper.html) · [EfficientNetV2 · ICML 2021](https://proceedings.mlr.press/v139/tan21a.html) · [Swin-T 官方实现与论文入口](https://docs.pytorch.org/vision/main/models/generated/torchvision.models.swin_t.html)

完整结果与本地联调记录将在本节更新。当前第一组已完成 20 个 epoch，最佳第 17 轮验证准确率 97.66%、Macro-F1 96.98%；其余组继续执行中。

## 8. 接入本地 API 与后续部署

模型选择完成后，使用已有留出评估和 `evaluate.py --activate-experimental` 将选中的包标记为内部测试。它不代表已完成独立田间验证。然后在本地 `.env` 中设置：

- `AGRIVISION_MODEL_DIR`：选中实验的父目录，即含有 `wheat` 子目录的目录。
- `AGRIVISION_DEVICE`：本机可用 `cuda`，也可用 `cpu` 比较实际响应时间。
- `AGRIVISION_ALLOW_EXPERIMENTAL_MODELS=1`：允许本地加载该内部测试模型。

模型标签以模型包为准；知识卡按病害 ID 独立查找。某一类资料尚未补齐时仍能返回识别候选，并给出通用的补拍/记录建议；不会凭空生成具体药名和剂量。

构建网页后启动已有本地服务：

```powershell
npm run build
```

```powershell
.\scripts\Start.ps1
```

网页打开 `http://127.0.0.1:8000`，接口文档为 `http://127.0.0.1:8000/docs`。`GET /api/meta` 应显示当前小麦模型的八个类别和新版本。前端上传照片到 `POST /api/cases`，后端加载并缓存模型、执行质检和推理，再返回候选、分数、版本与资料。照片识别不调用 DeepSeek；登录后的对话是独立链路。

停止本机服务：

```powershell
.\scripts\Stop.ps1
```

更详细的前后端开发方式见 [本地联调](development.md#本地联调)。先把本机识别与网页功能测通，再在云服务器测真实延迟、CPU、内存和并发。本机 CPU 线程测试不能直接保证某个云 vCPU 套餐的速度。需要降低成本时，再用选定大模型对比 ONNX、量化或蒸馏，并重新检查准确率、逐类召回和延迟。 [ONNX Runtime 量化](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html)
