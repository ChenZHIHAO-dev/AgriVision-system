# AgriVision 宛农植保助手

## 开发记录 · 2026-11-17

**当前：1.2 后端识别、对话与聊天界面完善中。线上 Pages 仍为已发布的 1.1 前端体验版。** 本节随实际开发更新，未验证的功能不会记为完成。

| 模块 | 当前状态 | 已做与待做 |
| --- | --- | --- |
| DeepSeek 密钥隔离 | 已完成 | 创建 `secrets/deepseek.env`，整个目录已加入 Git 忽略；用户已填写。开发代理不读取该文件，后端运行时加载，不记录密钥内容 |
| 小麦公开数据 | 已下载、整理中 | Kaggle v6 约 6.54GB 已下载，核对来源标注 CC0；选取四个核心类别与其他症状，像素去重后 6,331 张；正在做近重复分组与数据划分 |
| JIC 补充数据 | 下载校验中 | 公开子集共 999 张，来源标注 CC BY 4.0；逐文件校验，后续检查与 Kaggle 的重叠 |
| CNN 初版 | 待训练 | 采用 ImageNet 预训练 EfficientNet-B0，RTX 3060 本机训练；尚未产生本轮病害识别成绩 |
| DeepSeek 对话 | 编码中 | Flash / V4 Pro、思考开关、农业系统提示词、CNN 结果文字上下文；真实 API 与自动化验证待完成 |
| 信息补问与附件 | 编码中 | 作物 / 生育期选择卡；图片独立识别；TXT、MD、PDF、DOCX 只提取资料文字给对话模型 |
| 聊天 UI | 修复中 | 多行粘贴输入框溢出、灰黑深色主题、文字对比度、附件与模型控制区 |
| 本轮验证 | 待执行 | 模型独立测试、真实对话联调、多行输入与移动布局；结果会继续写入本节 |

约定：原图不发送给 DeepSeek；模型内部测试成绩与南阳实拍效果分开记录。数据集、权重、密钥、用户上传与运行日志不上传代码仓库。

---

服务河南南阳及周边小麦、玉米、花生种植场景的植保问诊软件。当前为 **1.1.0-dev.1 前端体验版**：访客可问诊和咨询，登录后可保存记录；保留 1.0 的 Python 后端与模型训练框架，后续逐步接入真实服务。

**手机网页体验：** [打开 AgriVision](https://chenzhihao-dev.github.io/AgriVision-system/)。GitHub Pages 只托管前端，本轮的登录、图片记录与资料咨询使用本机演示适配层。

## 本地运行

代码位于 `F:\college\AgriVision`。前端开发运行：

```powershell
npm run dev
```

打开 `http://127.0.0.1:5173`。默认前端体验无需后端。测试账户为 **admin / admin123**，也可以在当前设备注册测试账户。访客可以继续问诊与咨询，查看历史时才提示登录。

需要联调 1.0 后端时，先运行 `.\scripts\Start.ps1`，再在网页的“外观与设置”中选择“连接后端”。后端页面位于 `http://127.0.0.1:8000`，API 文档位于 `/docs`，停止服务运行 `.\scripts\Stop.ps1`。新环境准备使用 `.\scripts\Setup.ps1`，CUDA 依赖使用 `.\scripts\Setup.ps1 -WithCuda`。

## 已实现

- uni-app、Vue 3 和 TypeScript，共用网页与微信小程序页面。
- 固定顶栏与账户状态，工作台内容独立滚动；咨询采用消息区滚动、底部常驻输入框的布局。
- 访客使用、测试登录与注册、密码显示与校验、保持登录、退出和按需登录引导。
- 浅色、深色与跟随系统，分别配置背景、面板、文字和交互颜色。
- 图片选择、手机拍照入口、问诊信息、补图、历史筛选与删除、15 条植保资料及来源。
- 前端演示与后端连接适配；DeepSeek 后端接口、本地检索和标签资料规则。
- EfficientNet-B0、MobileNetV3-Small，数据去重与分组、训练、评测、模型导出和推理。

测试账户和演示记录只保存在当前设备，不等同于服务端认证或权限控制，不跨设备同步。本轮未新增账户数据库。正式病害权重、DeepSeek 密钥和公司产品资料尚待接入；图片不会被演示流程伪装为识别完成。

## 文档与待办

| 文档 | 内容 |
| --- | --- |
| [1.1 前端设计与测试待办](docs/frontend-1.1.md) | 访客与登录逻辑、主题、滚动布局、接口边界和手机待测项 |
| [开发与模型接入](docs/development.md) | 环境、后端、小程序、数据处理与模型训练 |
| [1.0 需求与验收](docs/requirements-v1.md) | 模型和业务框架的初版范围 |
| [实施规划](docs/demo-plan.md) | 地域作物、识别范围与实施顺序 |
| [数据来源](docs/data-sources.md) | 13 项候选数据来源、许可与采集计划 |
| [验证记录](docs/validation.md) | 已执行检查与实际验证范围 |

## 验证与构建

```powershell
npm run test:frontend   # 账户、访客记录、规则、主题和资源路径回归
npm run typecheck       # Vue 与 TypeScript
npm run build          # 本机网页，apps/client/dist/build/h5
npm run build:mp        # 微信小程序，apps/client/dist/build/mp-weixin
npm run build:pages     # Pages 网页，apps/client/dist/pages
```

推送 `main` 后，GitHub Actions 执行前端检查与构建并部署 Pages。Pages 构建使用 `/AgriVision-system/` 基础路径和 hash 路由。微信小程序仍需真实 AppID、后端地址及开发者工具和真机验证。

后端测试为 `.venv\Scripts\python.exe -m pytest -q`，模型链路检查为 `.venv\Scripts\python.exe scripts/smoke_ml.py`。RTX 3060 Laptop 已执行合成图片短训练、导出和推理；这项检查不评价病害识别效果。

密钥、用户图片、数据库、训练数据、权重和本地缓存均由 Git 忽略规则排除。正式后端公开部署还需完成服务端登录权限、HTTPS、配额与备份。
