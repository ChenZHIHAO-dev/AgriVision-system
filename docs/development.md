# 本机开发、构建和检查

在 Windows PowerShell 进入 `F:\college\AgriVision`。前端使用 Node.js 24，后端和训练共用项目的 Python 3.12 `.venv`。已有环境直接复用。uv 和 npm 安装缓存放在项目 `.cache`。 [训练环境与权重缓存](recognition-training-checklist.md)

## 本地联调

首次准备依赖执行 `.\scripts\Setup.ps1`。需要本机训练时选 `.\scripts\Setup.ps1 -WithCuda`。当前小麦权重、数据与本机配置在 Git 忽略目录中。

用一条命令启动已构建的网页和 API。

```powershell
.\scripts\Start.ps1
```

打开 [本机网页](http://127.0.0.1:8000/?mode=live) 或 [FastAPI 接口文档](http://127.0.0.1:8000/docs)。停止时执行 `.\scripts\Stop.ps1`。修改后端后重启。修改前端后可重新构建，或在两个终端分别运行以下命令，用 [5173 热更新网页](http://127.0.0.1:5173/?mode=live) 调试。

```powershell
.\scripts\Start.ps1 -ApiOnly
```

```powershell
npm run dev
```

DeepSeek 密钥使用服务端 `secrets/deepseek.env` 的 `DEEPSEEK_API_KEY`。管理员密码哈希由 `.\.venv\Scripts\python.exe scripts/hash_admin_password.py` 生成，保存到服务端 `AGRIVISION_ADMIN_PASSWORD_HASH`。参数模板见 [后端设置](../.env.example)，服务器部署见 [上线试测](wechat-deployment.md#接入真实服务)。

## 三端构建

| 在项目根目录运行 | 生成目录 | 用途 |
| --- | --- | --- |
| `npm run build` | `apps/client/dist/build/h5` | 本机或同源托管网页 |
| `npm run build:pages` | `apps/client/dist/pages` | GitHub Pages 的子路径网页 |
| `npm run build:wechat` | `apps/client/dist/wechat/preview` | 导入开发者工具，编译后预览 |
| `npm run build:wechat -- --live` | `apps/client/dist/wechat/live` | 写入小程序 AppID 和 HTTPS API 地址，扫码联调 |
| `npm run build:app` | `apps/client/dist/build/app` | Android 和 iOS 的 Uni-app 打包资源 |

App 内测可用 [HBuilderX 真机运行](https://uniapp.dcloud.net.cn/tutorial/run/run-app.html)。安装包发行使用相应的打包与签名流程。网页和 App 连接实际服务时，可在「我的 → 设置」维护 API 地址。微信联网包使用构建参数固定连接。

品牌原图和微信头像分别见 [高分辨率源图](../apps/client/branding/wan-nong-logo-v1.png) 与 [144 px 头像](../apps/client/branding/wan-nong-avatar-144.png)。运行时按钮图标位于 `apps/client/src/static/icons`，使用 `npm run icons` 从图标源重新生成。

## 数据和配置怎么用

| 文件或目录 | 用途 |
| --- | --- |
| `data/wheat/sources`、`data/wheat/review` | 原始来源、筛选表和照片对应关系 |
| `data/wheat/prepared` | 当前八类小麦工作集。`manifest.csv` 和 `labels.json` 给训练使用 |
| [wheat-review.json](../configs/labels/wheat-review.json) | 筛选时的候选病名全表，运行预处理后产生本次训练的实际标签 |
| [wheat-v1.json](../configs/labels/wheat-v1.json) | 小麦 V1 复现实验的五类定义 |
| [作物分类模板](../configs/labels/crop-identification-starter.json)、[玉米标签](../configs/labels/maize.json)、[花生标签](../configs/labels/peanut.json) | 对应后续任务的初始类别配置 |
| `artifacts/experiments`、`artifacts/models/<任务>` | 训练结果与供 API 加载的完整模型包 |

维护时先从 [架构](architecture.md) 和 [迭代计划](roadmap.md) 找现行入口。代码、脚本、配置、文档链接均无用途的旧文件可删。新增数据或更新模型后，在原操作清单直接更新版本、路径和相关影响。

## 测试和现场检查

前端交互与微信构建在 [tests/frontend](../tests/frontend)，账户、识别和对话接口在 [tests/api](../tests/api)，小麦数据准备与模型检查在 [tests/ml](../tests/ml)。它们由测试命令或 CI 执行，客户端和 API 从各自的运行入口加载业务代码。

| 命令 | 检查内容 |
| --- | --- |
| `npm run test:frontend` | 对话输入、键盘、深浅色、底栏、资料、历史和微信构建规则 |
| `npm run typecheck` | Vue 和 TypeScript 校验 |
| `.\.venv\Scripts\python.exe -m pytest -q` | 使用临时库检查账号隔离、识别、问答、资料和数据预处理 |
| `.\.venv\Scripts\python.exe scripts/verify_local_pipeline.py` | 默认检查健康信息、匿名业务拒绝和注册关闭；加 --username admin 检查实际识别、补图、选填资料与退出，并删除本次记录 |
| `.\.venv\Scripts\python.exe scripts/smoke_ml.py` | 通过小规模合成数据检查 CPU 训练、评测、加载和识别接口 |

本机 Windows 的测试临时文件统一放 `F:\Temp\AgriVision`。项目内 `.cache/tmp` 曾在普通文本目录重命名微复现中出现间歇 WinError 5；移到项目外 F 盘后，相同微复现和完整 ML 回归通过。尚未确认具体占用进程，不需要关闭安全软件，也没有给预处理加重试。下面三行仅设置当前 PowerShell 会话的临时目录，不新建 Python 环境，不改 `data` 工作图：

```powershell
New-Item -ItemType Directory -Path F:\Temp\AgriVision -Force | Out-Null
$env:TEMP = 'F:\Temp\AgriVision'
$env:TMP = $env:TEMP
```

设置后再运行表中的 pytest 命令。模型权重和训练缓存仍保留在项目已有目录。

真实服务检查可加 `--username admin` 在终端隐藏输入密码，检查已登录流程。`--exercise-provider` 与 `--web` 会请求外部问答服务并消耗用量，日常回归用默认命令。 [真机和集成验收](validation.md)

提交前运行 npm run test:frontend。其中的公开配置检查会扫描 Git 管理的文件，阻止具体格式的微信 AppID、常见提供商密钥、私钥和本机环境文件进入公开版本。真实设置保存在 .env、.env.wechat.local 或 secrets，示例配置只保留空字段和测试占位内容。

数据目录现按作物分为 `data/wheat`、`data/maize`、`data/peanut`、`data/crop-identification`。各自维护 sources/review/prepared；小麦 reference 是筛选表依赖，archive 为已有历史输出。多次训练只增加 artifacts 下的实验结果，不复制工作图片。详见[训练清单第 9 节](recognition-training-checklist.md#9-多作物目录与分组交叉验证2026-11-27)。
