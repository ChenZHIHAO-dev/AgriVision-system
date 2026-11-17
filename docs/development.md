# AgriVision 本地开发与模型接入

当前版本 1.2.0-dev.1，项目位于 `F:\college\AgriVision`。功能边界和待验收项见[1.2 记录](backend-1.2.md)。

## 启动与环境

本机依赖、数据和实验权重已准备，运行：

```powershell
.\scripts\Start.ps1
```

打开 http://127.0.0.1:8000，在“偏好与连接”选择“连接后端”，地址同为 http://127.0.0.1:8000。API 文档为 /docs；停止用 `.\scripts\Stop.ps1`。服务只绑定本机，不会自动开放公网。

新环境安装使用 `.\scripts\Setup.ps1`；需要训练与 CUDA 时使用 `.\scripts\Setup.ps1 -WithCuda`。依赖分别锁定在 package-lock.json、requirements-lock.txt 和 requirements-ml.txt。建议 Python 3.12；本机 Node 24、PyTorch 2.7.1+cu126。

前端热更新：

```powershell
npm run dev
```

默认前端体验模式，不调用真实识别与 API。后端可另开终端运行：

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir services/api --host 127.0.0.1 --port 8000
```

后端同时提供 apps/client/dist/build/h5 中的网页。修改前端后运行 npm run build；修改后端后重启。Start / Stop 脚本校验本项目监听进程及启动时间，不停止其他应用。

## DeepSeek 配置

密钥放在用户拥有的 `secrets/deepseek.env`：

```dotenv
DEEPSEEK_API_KEY="在本机填写"
```

整个 secrets 目录被忽略；不要把它提交，也不要放入前端 VITE 变量。用户已填写，不需要代理打开或重写。应用运行时读取，支持引号并关闭插值，日志和 API 只显示配置状态。

根目录 .env.example 仅提供后端参数模板。模型默认 deepseek-flash，网页可选 deepseek-v4-pro 和思考开关；参数见[官方文档](https://api-docs.deepseek.com/zh-cn/)。未配置或调用失败时返回本地资料与明确提示；用药方案仍由标签规则处理。

## 数据与模型

本轮模型的来源、类别、划分、训练命令、阈值与实际指标见[小麦模型说明](model-card-wheat-v1.md)。所有数据与权重保存在本机，代码仓库不包含它们。

| 路径 | 内容 |
| --- | --- |
| data/sources/kaggle-wheat-v6.zip | 主数据原始压缩包 |
| data/sources/metadata | 来源元数据及版本 |
| data/wheat-v1 | 整理图像、来源映射、数据清单与检查报告 |
| artifacts/experiments/wheat-b0-v1 | 实验权重、训练记录、校准和评测 |
| artifacts/models/wheat | 当前本机服务加载的实验模型包 |
| data/manual-tests/wheat-real-photos | 用户手动试图、署名许可与空白记录表 |

模型标签为 configs/labels/wheat-v1.json 的五类。旧 wheat.json 保留四类通用框架示例，不混用标签顺序。训练和推理共享架构、预处理及标签元数据。

实验激活使用 evaluate 的 --activate-experimental，要求真实训练清单的 test 划分、每类至少 20 张、Macro-F1 ≥ 0.8、每类召回率 ≥ 0.6，仍保持 validated=false。默认本机允许实验模型；设 AGRIVISION_ALLOW_EXPERIMENTAL_MODELS=0 可以关闭。合成开发检查模型始终被拒绝。

--activate 与 --field-verified 仅在完成实际田间验证并由操作者确认时使用，不能以内部测试代替。新实验使用新输出目录；迁移 AutoDL 时保留清单、标签、依赖和实验记录。

## 微信与手机

`npm run build:mp` 输出 apps/client/dist/build/mp-weixin，可导入微信开发者工具。当前 AppID 是游客占位；真机需自己的 AppID、手机可达的后端地址、权限与域名配置。

GitHub Pages 只提供前端。手机 localhost 指向手机自身，不能用它访问电脑的 3060 或 API。实际手机后端联调需后续配置可达的 HTTPS 服务，不把密钥放到 Pages。

## 验证

```powershell
npm run test:frontend
npm run typecheck
npm run build
npm run build:mp
npm run build:pages
.venv\Scripts\python.exe -m pytest -q
```

scripts/check_live_chat.py 和 scripts/check_backend_pipeline.py 通过正常本机 HTTP 接口检查真实服务，会产生少量 API 用量；只输出调用状态和字数，不读取密钥文件或输出回答正文。后者使用内部测试样本，绝不扫描手动试图目录。

scripts/smoke_ml.py 仍用于合成图像的训练 / 导出 / 推理代码检查，产物只能位于 .cache，不能用于业务识别或评价病害效果。

## 运行资料

已有 SQLite 保存本机问诊记录，账户仍为前端测试。knowledge/products.json 为空；接入公司资料时需保持来源和审核状态，再完善登记、适用作物、病虫害对象、生育期及标签用法。

图片保存在 runtime/images，文档在本机解析为文字；接口返回文档元数据，资料摘录用于对话。数据、运行记录、密钥和权重均在 Git 忽略规则中。待办与浏览器 / 真机验证范围持续记录在 README 和 validation.md。
