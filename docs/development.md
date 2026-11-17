# AgriVision 本地开发与模型接入

## 软件启动

在项目根目录使用 PowerShell。已完成环境准备时，运行：

```powershell
.\scripts\Start.ps1
```

打开 `http://127.0.0.1:8000`，接口说明在 `http://127.0.0.1:8000/docs`。停止服务运行 `.\scripts\Stop.ps1`。

新环境安装使用 `.\scripts\Setup.ps1`；需要 CUDA 模型框架时使用 `.\scripts\Setup.ps1 -WithCuda`。脚本要求 uv 和 Node.js，Python 建议 3.12。依赖保存在项目 `.venv` 与 `node_modules` 中；前后端安装分别使用已验证的 `package-lock.json` 和 `requirements-lock.txt`。

前端热更新开发使用 `npm run dev`，后端另开终端运行：

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir services/api --host 127.0.0.1 --port 8000
```

后端启动时如果 `apps/client/dist/build/h5` 已存在，会同时服务网页构建产物。前端依赖或环境配置变化后执行 `npm run build`。使用端口 8000 以外的后端时，需同步修改客户端运行与连接中的地址或构建前端的 `VITE_API_BASE_URL`。

## 微信小程序

运行 `npm run build:mp`，将 `apps/client/dist/build/mp-weixin` 导入微信开发者工具。当前使用游客 AppID 作为开发占位，正式测试替换为自己的小程序 AppID。手机真机的 localhost 指向手机自身，需改为手机可达的后端地址并配置微信网络要求。

前端所有业务请求共用 `src/lib/api.ts`，问诊信息更新使用 POST context 接口，避免依赖小程序请求方法中未声明的 PATCH。

## DeepSeek 配置

复制 `.env.example` 为项目根目录 `.env`，只在后端填写 `DEEPSEEK_API_KEY`。模型标识默认 `deepseek-flash`，可按[官方 Chat Completions 文档](https://api-docs.deepseek.com/api/create-chat-completion/)修改。重新启动后端后，运行状态会显示已配置。

未配置密钥时，咨询使用本地资料检索与说明；接口调用失败也保留这条路径。用药配方请求使用独立的产品规则，不让对话模型自由填入剂量。

## 数据与模型

原始数据按标签配置的内部标识放置：

```text
data/raw/wheat/
  wheat_stripe_rust/
  wheat_leaf_rust/
  wheat_powdery_mildew/
  healthy/
```

生成数据清单：

```powershell
.venv\Scripts\python.exe -m ml.agrivision_ml.prepare --data-root data/raw/wheat --labels configs/labels/wheat.json --output data/manifests/wheat.csv
```

同叶、同株、同地块拍摄批次或增强衍生关系应通过 `--groups data/groups.csv` 提供。分组文件为 `path,group` 两列，路径相对于数据根目录。默认精确与感知哈希只能发现部分重复，不能替代来源分组和人工复核。

开始迁移学习：

```powershell
.venv\Scripts\python.exe -m ml.agrivision_ml.train --data-root data/raw/wheat --manifest data/manifests/wheat.csv --labels configs/labels/wheat.json --output artifacts/models/wheat --epochs 30 --batch-size 8 --device auto
```

默认采用 ImageNet 预训练 EfficientNet-B0；`--architecture mobilenet_v3_small` 可比较轻量方案。首次使用预训练权重会访问 PyTorch 官方下载地址。输入大小、批量、冻结轮数与学习率可用命令行调整。路径与数据清单可迁移至 AutoDL。

模型包包含 `weights.pt`、`metadata.json` 和 `training.json`。标签顺序、图像缩放、归一化与模型结构由训练和推理共用。默认阈值为开发起点，需根据验证集检查并调整；模型分数不是病害确诊概率。

评测与接入：

```powershell
.venv\Scripts\python.exe -m ml.agrivision_ml.evaluate --bundle artifacts/models/wheat --data-root data/raw/wheat --manifest data/manifests/wheat.csv --split test
```

模型默认 `validated=false`。实拍和独立测试核对完成后，可在同一命令加入 `--activate --field-verified` 接入开发服务。开发门槛要求每类测试至少 20 张、Macro-F1 至少 0.8、每类召回率至少 0.6；这些是开发接入检查，不代表商业田间效果标准。开发检查模型始终禁止激活。

运行模型框架检查：

```powershell
.venv\Scripts\python.exe scripts/smoke_ml.py
```

该脚本创建合成图片，执行数据划分、一次短训练、权重导出和加载推理，仅验证代码链路。产物位于 `.cache/ml-smoke`，不会进入业务模型目录。

## 产品资料与测试

`knowledge/products.json` 初始为空。产品结构定义在 `services/api/app/schemas.py`；只有审核信息、有效期、标签来源、适用作物与对象等字段匹配的产品才会展示。公司资料接入后，还需扩展生育期、采收间隔和混配模板等条件核对。

后端与数据测试：`.venv\Scripts\python.exe -m pytest -q`。前端类型检查：`npm run typecheck`。两端构建分别为 `npm run build`、`npm run build:mp`。

数据、用户图片、数据库、密钥、模型权重和本地缓存均在忽略规则中。业务源文件与配置模板可提交到代码仓库。
