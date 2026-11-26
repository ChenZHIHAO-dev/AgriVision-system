# 小麦实验模型 v1

训练日期：2026-11-17。模型版本：`20261117-092348`。软件版本：1.2.0-dev.1。

## 任务与架构

首版输入为小麦叶片或症状近照，现有数据提供整图类别，采用 ImageNet 预训练 **EfficientNet-B0 卷积网络**做迁移学习。它适合当前 RTX 3060 Laptop 6GB 和五类分类任务。需要圈出虫体、定位多个病斑时，再补充框标注并评估 YOLO 等检测模型。

参考：[EfficientNet 原始论文](https://arxiv.org/abs/1905.11946)、[torchvision EfficientNet-B0](https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.efficientnet_b0.html)。模型分数是分类分数，不能直接解释为病害确诊概率。

| 内部标识 | 含义 |
| --- | --- |
| wheat_stripe_rust | 小麦条锈病 |
| wheat_leaf_rust | 小麦叶锈病 |
| wheat_powdery_mildew | 小麦白粉病 |
| healthy | 来源健康参考；产品提示“未发现已支持病害的明显特征” |
| wheat_other | 来源中的其他病害、虫害及症状；统一返回不确定 |

单标签模型不描述同叶多病、严重程度、虫体位置或药剂用量。“其他症状”不能覆盖所有未知输入。

## 数据

使用 [Kaggle Wheat Plant Diseases](https://www.kaggle.com/datasets/kushagra3204/wheat-plant-diseases) **version 6**，下载时来源元数据标注 **CC0**。压缩包约 6.54GB，本地统计 14,154 张图片文件。该来源汇集公开照片，来源许可声明不能替代对每张原始照片权属和标签的复核；扩大企业用途前需继续核查。

四个核心类别保留可读取图片，其余来源类别按固定种子最多抽取 150 张 / 类组成 other。像素去重后 6,331 张，进一步剔除两张过小图片和 14 张跨标签近重复冲突，得到 **6,315 张**。保留原始路径、原始划分、文件校验、像素哈希、感知哈希和来源映射。

训练重新按发现的近重复组划分，共 5,678 组；种子 42。原来源没有完整地块 / 拍摄批次标识，哈希分组只能排除发现的重叠，仍存在未识别衍生关系和来源偏差。

| 类别 | 训练 | 验证 | 测试 | 测试召回率 |
| --- | ---: | ---: | ---: | ---: |
| 条锈病 | 945 | 203 | 203 | 98.03% |
| 叶锈病 | 881 | 187 | 196 | 95.92% |
| 白粉病 | 827 | 145 | 159 | 89.94% |
| 健康参考 | 728 | 154 | 155 | 94.19% |
| 其他症状 | 1,077 | 228 | 227 | 94.27% |
| 合计 | **4,458** | **917** | **940** | — |

清单 SHA-256：`af1d352079734cec8271906a42c94eef836316cd7328a110988a4c88aae068c6`。

## 训练与阈值

本机 RTX 3060 Laptop；PyTorch 2.7.1+cu126；224×224；batch 24；AdamW，初始学习率 0.0003；冻结特征两轮后继续微调，余弦学习率；类别加权损失、label smoothing 0.03；AMP，seed 42，workers 2，最多 24 轮，patience 6。

24 轮完成，按验证 Macro-F1 选择第 19 轮，最佳验证 Macro-F1 95.73%。温度和接受门槛仅在验证集 917 张上选择：temperature 0.95、top score ≥ 0.85、前两类分差 ≥ 0.25；预测 other 总是拒绝。选择规则是在接受结果准确率至少 98% 的候选中最大化验证覆盖，且至少接受 30 张。

## 内部测试

冻结配置后评测测试集 940 张：

- 全量 top-1 准确率 **94.68%**，Macro-F1 **94.65%**，平均类别召回率 **94.47%**。
- 接受 662 张，覆盖率 **70.43%**，被接受结果中准确率 **97.89%**；其余交给不确定流程。
- 这些指标针对模型输入，不包含上传端的模糊、曝光或尺寸拦截。

完整汇总与混淆矩阵见[内部测试 JSON](validation/wheat-b0-v1-internal.json)。没有用测试集或用户手动试图继续选阈值。

## JIC 重叠与有限外部检查

[JIC Small / Zenodo 7307816](https://zenodo.org/records/7307816) 公开子集 999 张，来源标注 CC BY 4.0；逐文件 MD5 校验完成。与主数据对比后排除 771 张重复或近重复，剩下 **228 张均为 Septoria，映射到 other**。所以无法从该子集得到四类独立外测准确率，也不报告缺失类别下的总体 Macro-F1。

剩余图片仅做未覆盖症状探索：197 / 228 的 top-1 为 other；阈值下 220 / 228 返回不确定，**8 / 228 被错误接受为支持类别**。这暴露了未知症状仍可能被误判，需要独立田间数据继续检验。见[原始汇总](validation/wheat-b0-v1-external-jic.json)。

## 接入状态与手动试图

本机模型包位于 `artifacts/models/wheat`，包括 weights、metadata、训练、校准和测试报告。状态为 `development_ready=true`、`validated=false`、`field_verified=false`、`release_stage=experimental`。本地设置允许实验模型，界面显示实验标记；合成链路检查模型始终不能服务业务。

另在 `data/manual-tests/wheat-real-photos` 保存 10 张公开实拍照片与署名许可，人工核对拍摄内容并查重。没有将其用于训练、调参、评分或预先运行识别。它们包含跨品系照片和未确诊黄化症状，不是南阳田间正式评测集。

下一步采集南阳不同地块、设备、生育期和天气条件下的照片，由农技人员复核，并按地块与拍摄批次分组评测。白粉病召回率和未知症状误接受应重点检查。

## 复现

将合法取得的 Kaggle v6 压缩包保存为 `data/wheat/sources/kaggle-wheat-v6.zip`，并保留来源元数据。已有数据和模型不需重新训练。以下命令会生成相应输出，重新实验应使用新的输出目录：

```powershell
.venv\Scripts\python.exe scripts/assemble_wheat.py
.venv\Scripts\python.exe -m ml.agrivision_ml.prepare --data-root data/wheat-v1/images --labels configs/labels/wheat-v1.json --output data/wheat-v1/manifest.csv
.venv\Scripts\python.exe -m ml.agrivision_ml.train --data-root data/wheat-v1/images --manifest data/wheat-v1/manifest.csv --labels configs/labels/wheat-v1.json --output artifacts/experiments/wheat-b0-v1 --epochs 24 --batch-size 24 --lr 0.0003 --freeze-epochs 2 --patience 6 --seed 42 --device cuda --workers 2
.venv\Scripts\python.exe -m ml.agrivision_ml.calibrate --bundle artifacts/experiments/wheat-b0-v1 --data-root data/wheat-v1/images --manifest data/wheat-v1/manifest.csv --device cuda
.venv\Scripts\python.exe -m ml.agrivision_ml.evaluate --bundle artifacts/experiments/wheat-b0-v1 --data-root data/wheat-v1/images --manifest data/wheat-v1/manifest.csv --split test --device cuda --activate-experimental
```

以上仅用于实验接入，不能使用 `--field-verified` 代替实际田间验证。迁移 AutoDL 时使用相同标签、清单、配置和依赖，并记录新环境与实验目录。
