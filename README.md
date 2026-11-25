# 宛田观叶 · AgriVision

为小麦等作物提供照片辅助识别、种植问答和农业资料。网页、微信小程序和 App 资源共用业务组件，通过 FastAPI 请求识别、资料和账户服务。当前属于开发内测，可以离线演练，也可以连接实际后端。

## 在本机打开

在 PowerShell 进入项目目录。

```powershell
Set-Location -LiteralPath 'F:\college\AgriVision'
```

首次安装依赖使用 `.\scripts\Setup.ps1`。更新网页代码后运行 `npm run build`。已有构建时直接启动。

```powershell
.\scripts\Start.ps1
```

打开 [本机网页](http://127.0.0.1:8000/?mode=live)。游客可拍照识别，登录后可询问 AI 和查看记录。联调设置、停止与代码热更新见 [本机开发和检查](docs/development.md)。

## 目前做到哪一步

| 功能 | 当前状态 |
| --- | --- |
| 网页、微信、App | 首页使用拍照、询问 AI 两个入口。最近记录、参考资料和农业资讯在首页切换。桌面网页保留历史侧栏。App 可生成打包资源，待 Android 和 iOS 真机验收 |
| 图像识别 | 支持手选作物或让作物识别给出候选。七组实验已完成，本机已接入八类 Swin-T 内测权重。固定留出测试准确率 98.94%；详见训练清单第 7 节。作物分类及其他作物的实用权重待训练和验收 |
| 问答与资料 | 15 张公开资料卡可查阅。后端可用资料或 DeepSeek 回答，继续对话可承接本次照片。联网内测使用管理员账户，离线演示使用演示账号 |
| 小麦数据 | `data/wheat-leaf-spike-03` 已有 6,455 张工作图、8 类标签、1,290 组。固定使用这份工作集，已完成四种架构的七组完整实验；在线增强不另存图片 |

## 按任务查文档

| 要做的事 | 文件 |
| --- | --- |
| 看前后端职责、主要接口和交互层级 | [系统架构与现行功能](docs/architecture.md) |
| 启停开发服务、构建三端和运行测试 | [本机开发和检查](docs/development.md) · [验收与历史报告](docs/validation.md) |
| 筛图、预处理、训练和评价 | [Windows 操作清单](docs/recognition-training-checklist.md) · [数据来源和病名](docs/data-sources.md) |
| 看当前模型的指标、曲线、局限与复现命令 | [七组实验报告](docs/recognition-training-checklist.md#7-本轮七组实验与历史问题)；[V1 历史模型卡](docs/model-card-wheat-v1.md) |
| 部署 API 或生成微信预览、联网包 | [微信构建与部署](docs/wechat-deployment.md) |
| 跟进图像模型、资料检索与问答开发 | [迭代计划](docs/roadmap.md) |
