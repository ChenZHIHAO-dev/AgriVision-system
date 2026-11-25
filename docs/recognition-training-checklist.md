# 小麦预处理、数据增强和训练操作清单

本轮固定使用 `data/wheat-leaf-spike-03`。当前已经完成预处理，可以先看图、核对类别和划分。数据增强由训练命令启动，在训练读取照片时执行。

| 阶段 | 程序 | 这一阶段做什么 |
| --- | --- | --- |
| 预处理，已完成 | [wheat_review.py](../ml/agrivision_ml/preprocessing/wheat_review.py) | 读取筛选表，生成 `03` 的工作图、训练划分与统计 |
| 数据增强，随训练执行 | [model.py](../ml/agrivision_ml/model.py) | 对每次读取的训练图做随机变换，直接把结果交给模型 |
| 模型训练，数据核对后执行 | [train.py](../ml/agrivision_ml/train.py) | 读取 `03`，更新模型参数，在训练结果目录保存权重和曲线 |

## 0. 打开项目目录

在 **Windows PowerShell** 输入这一行。后续代码框逐条执行，使用项目已有的 `.venv`。

```powershell
cd F:\college\AgriVision
```

## 1. 筛选与预处理

### 运行数据预处理

**这一步已经完成。** 你运行过的 `wheat_review` 命令读取 `leaf-spike-review.csv` 中标记 `keep` 的照片，核验文件、整理方向、查重并按采集组划分训练、验证和测试。工作图保留长宽比，长边最多 1,024 像素。生成位置就是本轮的 `data/wheat-leaf-spike-03`。

目前直接复核 `03`。生成命令的 `--output` 用于首次写入，脚本看到现有目录时会拒绝覆盖。

### 检查处理结果

本轮结果有 **6,455 张、8 类、1,290 组**。训练 4,621 张，验证 981 张，测试 853 张。81 种分辨率来自不同原图的尺寸和长宽比。逐张人工复核仍在进行。 [本轮来源和筛选记录](data-sources.md#本轮叶片与麦穗)

打开现有工作图，按类别查看。

```powershell
explorer F:\college\AgriVision\data\wheat-leaf-spike-03\images
```

| `03` 里的文件 | 用途 |
| --- | --- |
| `images/<类别 ID>/` | 按类别查看清洗后的工作图 |
| `manifest.report.json` | 查各类数量、采集组、来源、分辨率和排除原因 |
| `sources.csv` | 从工作图找到原图路径和拍摄部位 |
| `manifest.csv` | 记录每张图的类别、采集组和训练、验证、测试划分 |
| `labels.json` | 记录该工作集实际包含的类别和名称 |

### 看图并修改筛选决定

打开筛选表。`decision=keep` 表示当前保留候选。修改后用 **CSV UTF-8** 保存。

```powershell
Invoke-Item F:\college\AgriVision\data\wheat-review\leaf-spike-review.csv
```

1. 从工作图追溯原图时，在 `03` 的 `sources.csv` 查找工作图文件名。用同一行的 `source_path` 在筛选表的 `path` 列定位。
2. 清晰的麦叶或麦穗实拍图填 `keep`。带水印、拼图、明显模糊、非小麦或根部图填 `drop`。看不准的留空，可在 `note` 记录原因。
3. 查看类别时以 `label` 为准，`class_name` 和 `part` 方便按中文病名和部位检查。 [病名与原始标签](data-sources.md#病名与原始标签对照)

### 先看要处理几套数据

这条只检查当前筛选表中的照片路径，打印 `keep`、`drop`、待复核数量及各类、各来源张数。修改筛选表后，这条命令显示的是**修改后的筛选决定**。训练实际读取的是 `03` 中已经生成的 `manifest.csv`。

```powershell
.\.venv\Scripts\python.exe -m ml.agrivision_ml.preprocessing.wheat_review --review data/wheat-review/leaf-spike-review.csv --check
```

## 2. 开始训练

### 上一轮训练结果

这次用的是 **MobileNetV4-Conv-Small**，由 timm 加载 ImageNet 预训练权重。它是轻量 CNN。照片先经过普通卷积，再经多级卷积块提取特征。其中的通用倒残差块用逐通道卷积提取空间特征，用 1×1 卷积混合通道。最后做全局平均池化和八类分类。本项目换成八类分类头后有约 **250 万参数**，网络中有 46 个 BatchNorm2d 层。 [MobileNetV4 论文](https://www.ecva.net/papers/eccv_2024/papers_ECCV/html/5647_ECCV_2024_paper.php) · [timm 使用的预训练权重](https://huggingface.co/timm/mobilenetv4_conv_small.e2400_r224_in1k)

| 轮次 | 训练准确率 | 验证准确率 | 验证 Macro-F1 | 验证 loss |
| --- | ---: | ---: | ---: | ---: |
| 8，保存的最佳权重 | 82.06% | 85.93% | 82.56% | 0.717 |
| 9 | 81.87% | 71.76% | 70.28% | 2.216 |
| 11 | 77.43% | 78.80% | 75.98% | 8.141 |
| 13，早停 | 84.79% | 69.93% | 68.55% | 19.762 |

第 8 轮在 981 张验证图上复跑得到 843 张正确。第 9 轮起表现明显波动，之后连续 5 轮没有刷新 Macro-F1，程序提前结束。第 13 轮有 77 张条锈病被错分成叶锈病，第 8 轮这个数字是 9 张。训练继续变好、验证整体变差，已经出现泛化落差。 [逐轮曲线和混淆矩阵](../artifacts/experiments/wheat-leaf-spike-03-mnv4-01/training.json)

准确率按第一候选是否正确计数，loss 还取决于模型给各类的分数。例如在普通交叉熵里，真实类别得到 10% 概率时损失约为 2.30，得到 0.1% 时约为 6.91，两种情况都可能只计一次错。本项目还按训练图数量给类别加权，并使用 0.03 的标签平滑。因此第 11 轮比第 9 轮猜对更多照片，loss 仍可能更高。 [模型置信度与校准研究](https://proceedings.mlr.press/v70/guo17a.html)

这次 batch 为 8，骨干冻结 2 轮，解冻后所有层一起更新，初始学习率 0.0003，实际为 FP32。小批次的 BatchNorm 统计和解冻后的学习率值得分别排查。用第 8 轮权重冻结所有参数，只用 512 张训练图重估 BatchNorm 均值和方差，验证准确率从 85.93% 变为 86.24%，loss 从约 0.717 变为 1.095。这个实验测到了分数对 BatchNorm 统计的敏感性。第 13 轮没有保存权重或逐图分数，具体是哪一次更新或哪一层引发跳升仍待定位。 [BatchNorm 训练与评估机制](https://docs.pytorch.org/docs/stable/generated/torch.nn.BatchNorm2d.html)

先核对第 8 轮就存在的混淆。217 张条锈病验证图中有 31 张被判成黄矮病，涉及 8 个采集组。其中 30 张来自 MSWDD2022，该来源共有 135 张条锈病验证图。优先检查这些组的病名、拍摄部位和相近画面。比较模型时同时看逐类召回与来源，避免只看总体准确率。

### 数据增强怎么执行

**先运行预处理保存工作图，再启动训练读取这些工作图。** 当前 `03` 已经生成，训练命令可以直接使用。

1. `wheat_review.py` 从筛选表读保留项，校正方向、等比缩图，整理采集组和划分。工作图与清单存放在 `data/wheat-leaf-spike-03`。例如一张 `1024×768` 的工作图仍然是 4∶3。 [预处理入口](../ml/agrivision_ml/preprocessing/wheat_review.py)
2. 每一轮，`Images` 按清单把工作图读入内存。原有方案统一缩放为 `224×224`，这一步会拉伸非方形图。训练图再随机水平翻转、在 ±10° 内旋转，并微调亮度、对比度、饱和度，最后转换为张量并归一化。验证、测试和推理只走固定尺寸和归一化。 [读图代码](../ml/agrivision_ml/train.py) · [模型输入与增强](../ml/agrivision_ml/model.py)
3. 增强结果直接交给这一次训练批次。下一轮读取同一张工作图时会重新抽取增强参数。磁盘上的照片是第 1 步输出的工作图。每轮训练写出的文件是权重、指标和曲线。

本轮先保留相同清单、224 输入和增强方式，便于和第 8 轮基线比较。如果细小病斑仍认不清，再单独做保比例、提高输入分辨率的对照。 [预处理与增强实验](data-sources.md#预处理与增强实验)

### 设置预训练权重缓存

在开始训练的同一个 PowerShell 窗口执行。TorchVision 第一次下载的 ConvNeXt 权重会放到 F 盘项目缓存。这一行只作用于当前窗口及它启动的程序。

```powershell
$env:TORCH_HOME = 'F:\college\AgriVision\.cache\torch'
```

### 运行训练命令

**下一轮先试 ConvNeXt-Tiny。** 它同样是 CNN，八类分类头下约 **2,783 万参数**，使用 LayerNorm，以单个样本的特征计算归一化，不依赖 BatchNorm 的跨批运行统计。用 `03` 的小样本在本机 RTX 3060 6 GiB 做了两轮检查，每批 8 张 `224×224` 图，覆盖冻结骨干、全网微调、曲线输出和 CPU 读回最优权重。短训中 PyTorch 峰值预留显存约 790 MiB。完整训练后再比较准确率。 [ConvNeXt 论文](https://openaccess.thecvf.com/content/CVPR2022/html/Liu_A_ConvNet_for_the_2020s_CVPR_2022_paper.html) · [TorchVision 模型与权重](https://docs.pytorch.org/vision/main/models/generated/torchvision.models.convnext_tiny.html)

```powershell
.\.venv\Scripts\python.exe -m ml.agrivision_ml.train --data-root data/wheat-leaf-spike-03/images --manifest data/wheat-leaf-spike-03/manifest.csv --labels data/wheat-leaf-spike-03/labels.json --output artifacts/experiments/wheat-leaf-spike-03-convnext/wheat --architecture convnext_tiny --device cuda --input-size 224 --batch-size 8 --lr 0.0001 --freeze-epochs 2 --precision amp --epochs 24 --workers 0
```

| 参数 | 具体做什么 |
| --- | --- |
| `--data-root`、`--manifest`、`--labels` | 分别读取 `03` 的工作图、划分和八类标签表 |
| `--output` | 写入本轮权重、配置、逐轮指标和曲线。末尾的 `wheat` 对应 API 的小麦模型目录结构 |
| `--architecture convnext_tiny --device cuda` | 用 ImageNet 权重初始化 ConvNeXt-Tiny，交给本机 NVIDIA 显卡训练 |
| `--input-size 224` | 模型每次接收 224×224 的 RGB 图，与上一轮保持一致 |
| `--batch-size 8 --precision amp` | 与上一轮一样每批读八张图，用 CUDA 混合精度完成训练 |
| `--lr 0.0001 --freeze-epochs 2` | 使用更小的初始学习率，前两轮先适配八类分类头，随后全网微调 |
| `--epochs 24 --workers 0` | 最多 24 轮，在当前 Python 进程读图。验证 Macro-F1 连续 5 轮不改善会早停 |

终端先核对目录和照片，再显示每轮训练、验证进度，以及 loss、准确率、Macro-F1 和实际更新次数。这是一次候选方案比较。如果要单独确认学习率是否影响稳定性，用原来的 MobileNetV4 配置，只把 `--lr` 改为 `0.0001`。每次训练的 `--output` 都指向该实验自己的结果位置，数据仍用同一份 `03`。

## 3. 查看训练曲线

训练开始写出结果后，打开本轮结果目录。

```powershell
explorer F:\college\AgriVision\artifacts\experiments\wheat-leaf-spike-03-convnext\wheat
```

- `training-curves.png` 查看训练、验证的 loss 和准确率，每轮更新。
- `training.json` 查看逐轮指标及混淆矩阵。对照之前的 85.93% 验证准确率和 82.56% Macro-F1，也检查条锈病、黄矮病、叶枯病等易混类别。
- `weights.pt` 和 `metadata.json` 保存验证 Macro-F1 最佳轮次的权重和模型配置。对应轮次在 `metadata.json` 的 `validation.epoch`。

## 4. 训练完再校准和测试

先校准。程序读取最佳权重，在 `03` 的验证集上调整温度和明确结果阈值，更新 `metadata.json`，生成 `calibration.json`。第一候选的顺序仍由模型决定。校准效果看给出明确结果的覆盖率和这些结果的准确率。 [校准代码](../ml/agrivision_ml/calibrate.py)

```powershell
.\.venv\Scripts\python.exe -m ml.agrivision_ml.calibrate --bundle artifacts/experiments/wheat-leaf-spike-03-convnext/wheat --data-root data/wheat-leaf-spike-03/images --manifest data/wheat-leaf-spike-03/manifest.csv --device cuda
```

在验证集上确定模型后再测试。下面读取 `03` 的 **853 张留出测试图**。输出 `evaluation-test.json`，其中有全量准确率、Macro-F1、逐类召回、混淆矩阵和拒识后的覆盖率。总体以九成以上为目标，也看各类的表现。 [评估代码](../ml/agrivision_ml/evaluate.py)

```powershell
.\.venv\Scripts\python.exe -m ml.agrivision_ml.evaluate --bundle artifacts/experiments/wheat-leaf-spike-03-convnext/wheat --data-root data/wheat-leaf-spike-03/images --manifest data/wheat-leaf-spike-03/manifest.csv --split test --device cuda
```

## 5. 本机单张试图与参数帮助

把 `F:\photos\wheat-sample.jpg` 换成你电脑上实际的照片路径。这条运行一次本机 GPU 推理，在终端显示前三候选、分数和加载的模型版本。用 CPU 时把末尾的 `cuda` 改为 `cpu`。 [单图推理代码](../ml/agrivision_ml/inference.py)

```powershell
.\.venv\Scripts\python.exe -m ml.agrivision_ml.inference --bundle artifacts/experiments/wheat-leaf-spike-03-convnext/wheat --image "F:\photos\wheat-sample.jpg" --device cuda
```

下面这条只打印训练参数帮助。

```powershell
.\.venv\Scripts\python.exe -m ml.agrivision_ml.train --help
```

Windows 训练依赖、Python 和缓存配置分别见 [requirements-ml.txt](../requirements-ml.txt)、[.python-version](../.python-version) 和 [uv.toml](../uv.toml)。

## 6. 读代码从哪里开始

| 想看什么 | 从这个文件开始 |
| --- | --- |
| 从筛选表到工作图 | [wheat_review.py](../ml/agrivision_ml/preprocessing/wheat_review.py) 的 `build_dataset()` |
| 校正方向与等比缩放 | [images.py](../ml/agrivision_ml/preprocessing/images.py) 的 `decode_rgb()` 和 `write_work_jpeg()` |
| 查重、合并采集组和划分 | [manifest.py](../ml/agrivision_ml/preprocessing/manifest.py) · [groups.py](../ml/agrivision_ml/preprocessing/groups.py) · [splits.py](../ml/agrivision_ml/preprocessing/splits.py) |
| 切换模型、随机增强与模型输入 | [model.py](../ml/agrivision_ml/model.py) 的 `build_model()` 和 `preprocessing()` |
| 从 `03` 读图、训练和早停 | [train.py](../ml/agrivision_ml/train.py) 的 `Images` 和 `train()` |
| 每轮曲线如何输出 | [training_curves.py](../ml/agrivision_ml/training_curves.py) |

## 7. 独立田测与发布

本机训练和测试完成后，再用独立田块和拍摄批次了解逐类召回、覆盖率和未知症状误接受率。尤其留意目前来源较少的病类。田测可使用同一个模型包。数据来源和现有网页权重分别见 [数据来源](data-sources.md) · [小麦 V1 模型卡](model-card-wheat-v1.md)。

## 8. CPU 服务接入

**先在这台电脑验证效果。** 第 5 节可以直接试新权重。下一步接本机网页时，模型包需要 `weights.pt`、`metadata.json` 和实验评估状态。第 4 节的命令可加 `--activate-experimental`，达到现有 API 的内测门槛时会更新该包的状态。API 还将病害 ID 与知识条目核对。八类模型要在网页上启用，需要先补齐颖枯病、黄矮病和壳针孢叶枯病条目。接好后将服务的 `AGRIVISION_MODEL_DIR` 指向 `artifacts/experiments/wheat-leaf-spike-03-convnext`，用 `AGRIVISION_DEVICE=cuda` 启动本机服务，先看 `GET /api/meta` 的小麦版本，再在网页上传实拍照片。 [模型加载规则](../services/api/app/models.py) · [本机服务启停](development.md#本地联调)

下面是 Ryzen 9 5900HX 本机对 40 张验证 JPEG 的测量。模型预先加载并预热，每次推理一张，计时含打开 JPEG、缩放、模型前向和选前三候选。ConvNeXt 使用相同结构的初始权重测计算耗时。P95 是 95% 的实测请求在其以内完成的耗时。

| 模型 | 2 个 CPU 线程 P50 / P95 | 4 个 CPU 线程 P50 / P95 |
| --- | ---: | ---: |
| 已训练的 MobileNetV4-Conv-Small | 16 / 20 ms | 17 / 23 ms |
| ConvNeXt-Tiny | 101 / 125 ms | 98 / 143 ms |

**云上可从 4 vCPU、8 GiB、单进程常驻一个分类器试起。** 上传图片时 API 按需加载权重并缓存。上云后在目标实例测手机或网页上传到收到结果的 P95，也看并发时的延迟、CPU 和内存，再决定是否升级。复用现有 CPU 机器先测也可以。 [阿里云计算型实例规格](https://help.aliyun.com/zh/ecs/user-guide/instance-specification-naming-and-classification) · [CPU 联网试测](wechat-deployment.md#cpu-联网试测)

**效果达标后再压缩。** 如果云端实测达不到延迟或资源目标，先用同一个模型对比 PyTorch 与 ONNX Runtime 的 FP32 推理，再试静态 INT8，用有代表性的训练照片校准。若仍需降低计算量，用表现最好的模型作教师，让 MobileNetV4 等小模型学习它的类别分数分布。两种压缩产物都用原评测口径比较准确率、逐类召回、覆盖率和延迟。 [ONNX Runtime 量化](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html) · [知识蒸馏论文](https://arxiv.org/abs/1503.02531)


## 9. 本轮五次完整实验

本轮固定读取 `data/wheat-leaf-spike-03`，训练 4,621 张、验证 981 张、测试 853 张。在线增强在每次训练读图时执行，增强图保存在内存中。结果统一放在 `artifacts/experiments/wheat-study`。

| 实验目录 | 本轮要检验的问题 |
| --- | --- |
| `01-convnext-light` | ConvNeXt-Tiny 用等比补边、轻增强，建立中等规模模型基线 |
| `02-convnext-field` | 在同一骨干和输入下，轻微成像退化是否改善识别 |
| `03-efficientnetv2` | 用前两轮较好增强比较 EfficientNetV2-S，并固定 BN 运行统计 |
| `04-resolution320` | 基于前三轮较好方案提高分辨率到 320，观察小病斑与易混类别 |
| `05-weight-balance` | 基于前四轮较好方案，减弱类别损失加权，观察少数类误报与总体表现 |

每轮从 ImageNet 预训练权重重新开始，种子固定为 42，每批 16 张，最多 20 个完整 epoch。验证 Macro-F1 连续 6 轮不改善会早停。每个完成的 epoch 都遍历全部训练图，验证集只做固定尺寸变换。五轮全部完成后，先按验证 Macro-F1 选定候选，再统一计算测试结果。

`light` 使用水平翻转、±10° 旋转和轻微亮度、对比度、饱和度变化。`field` 在相似强度下加入不超过 3% 的平移、0.95–1.05 倍缩放，并以 15% 概率随机选一种成像退化。退化包括 σ=0.1–0.7 的 3×3 模糊、质量 75–95 的 JPEG 或标准差为 3/255 的高斯噪声。这些数值是本轮待比较的轻增强起点，实际收益由第 1、2 轮对照决定。原图及增强图的示例在 `augmentation-preview.png`。增强实现集中在 [augmentation.py](../ml/agrivision_ml/augmentation.py)。

每个实验的 `wheat` 子目录都保存最佳 `weights.pt`、末轮 `last-weights.pt`、`metadata.json`、逐轮 `training.json`、`training-curves.png`、`confusion-val.png`、`predictions-val.csv` 和评估 JSON。最终增加相应测试图表及预测 CSV。最后一轮权重用于分析训练异常，最佳权重由验证 Macro-F1 决定。`train_images_seen` 记录该轮读过的训练图数，`max_gradient_norm` 记录裁剪前最大梯度范数。

`study.json` 保存各轮完整命令、调整理由和实际参数。`summary.json` 保存统一对比和按验证集选出的版本。数据划分及原图内容的 SHA-256 与代码提交号记录在模型配置中。使用现有虚拟环境，在本机 GPU 上训练。模型量化与蒸馏安排在本轮准确率和易混类别结果明确后进行。
