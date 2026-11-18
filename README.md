> **B 版（1.4.0-beta.4）网页已发布。** 本轮调整咨询侧栏并验证 CPU 识别。

# AgriVision 宛农植保助手

面向河南南阳及周边小麦、玉米、花生种植场景的植保问诊软件。当前客户端版本 **1.4.0-beta.4**，先完善功能与交互，再迭代模型效果。

项目路径：`F:\college\AgriVision`。使用 Git 管理改动，直接编辑工作区，不额外保存整套备份副本。

## 开发记录 · 2026-11-18 / B 版侧栏（1.4.0-beta.4）

- 桌面历史侧栏合并为一个开关。收起后只留左侧边缘把手，可点击或用键盘恢复。
- 手机历史从左侧滑入。顶部为品牌、搜索和关闭，底部为新建咨询与账户。登录后可在已加载的自己的记录中搜标题、作物、地点、备注和对话内容。
- 咨询顶栏明确显示退出入口。用手机尺寸网页实测相册上传、进入咨询、退出回到原识别结果。
- 现有小麦模型完成 CPU 推理基准。现有 FastAPI、模型文件、域名与 AppID 配置见 [微信 CPU 联网试测](docs/wechat-deployment.md#cpu-联网试测)。

43 项前端检查、H5 与独立微信构建通过。[网页部署](https://github.com/ChenZHIHAO-dev/AgriVision-system/actions/runs/44246970157)对应源码 a8ae538，[12 项线上资源](docs/validation/pages-beta4-1.4.json)与本机构建一致。

[桌面和手机浏览器验收](docs/validation/ui-beta4-1.4.json)。

## 开发记录 · 2026-11-18 / B 版图标修正（1.4.0-beta.3）

深浅色切换时，网页直接替换原生图标节点，小程序按图标地址更新位图节点。普通图标与实色按钮图标分别切换，品牌与作物彩图保留原样。新增组件回归验证浅色、深色切换时旧位图会从网页中移除。

43 项前端检查、网页与小程序编译通过。小程序编译使用独立校验目录，原导入项目保持原样。[桌面和手机网页验证](docs/validation/ui-beta3-1.4.json) · [线上一致性](docs/validation/pages-beta3-1.4.json) · [发布记录](https://github.com/ChenZHIHAO-dev/AgriVision-system/actions/runs/44244755315)。

## 开发记录 · 2026-11-18 / B 版配色（1.4.0-beta.2）

深色外观使用黑色主背景和炭灰卡片。顶栏、底栏、选中态、按钮按压和焦点统一为中性灰阶，网页地址栏同步使用黑色。

42 项前端检查通过，手机与桌面网页已检查，微信离线包构建通过。[部署](https://github.com/ChenZHIHAO-dev/AgriVision-system/actions/runs/44243055672)对应源码 aedecb2，[12 项线上资源](docs/validation/pages-beta2-1.4.json)与本地构建一致。

## 开发记录 · 2026-11-18 / B 版（1.4.0-beta.1）

- 工作台下方就地切换「最近问诊 / 参考资料 / 农业资讯」，拍照和文字咨询入口仍在其上。手机资料搜索随页面吸顶，深滚时收起分类和布局工具，回滑或点「筛选」展开。切换作物后回到资料区域。
- 点击「调整顺序」可拖动两张快捷入口的把手，也可点「上移 / 下移」。偏好只存本机，栏目位置保持稳定。
- 聊天合并为一行顶栏，保留返回、会话名称与历史入口。标题菜单提供重命名、问诊资料、复制对话文字，有照片时可查看识别结果。自定义名称保存到对话记录，识别标题独立。空会话提示与示例问题居中显示。
- 降低浅色亮度，统一绿色强调与深色悬停、按压反馈。小麦用麦穗、玉米用玉米棒、花生用果实图标。Markdown 表格表头和单元格留出更多内边距。
- 390×844 实测首页资料吸顶、花生筛选、快捷入口拖动、会话改名与返回资料层级。桌面 1280×800 检查无横向溢出。底部导航交互沿用上版。真机首次验收见 [11 月 19 日微信 B 版试用说明](docs/wechat-deployment.md)。

前端 42 项和后端 67 项通过，网页与微信离线包构建通过。网页发布源 ea32f1d，[GitHub 构建与部署](https://github.com/ChenZHIHAO-dev/AgriVision-system/actions/runs/44241137477)成功，[12 项线上资源](docs/validation/pages-beta-1.4.json)与本地匹配。

[浏览器验收](docs/validation/ui-beta-1.4.json) · [Apple 工具栏](https://developer.apple.com/design/human-interface-guidelines/toolbars) · [Gemini 会话管理](https://support.google.com/gemini/answer/13666746) · [深浅色交互对比规范](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast)。

## 开发记录 · 2026-11-18 / 1.3.1

| 项目 | 改动与验收 |
| --- | --- |
| 手机顶栏 | 首页与拍照页移除重复的快捷栏。主要操作保留在正文，聊天顶栏同时提供返回和问诊历史 |
| 资料 | 手机以独立阅读页打开资料。搜索常驻，知识／资讯、筛选和布局工具随滚动收放。分类、搜索和布局切换后列表回到顶部，卡片顶对齐 |
| 底栏 | 单击直接切页，长按或按住明确横拖时玻璃滑块跟随，松手切换。滑块淡出，只强调当前按钮。390px 浏览器实拖从首页切至我的 |
| 文字咨询 | 常见术语、标签阅读和拍摄方法可直接提问。田间症状判断仍按需收集必要信息，再续答原问题 |
| 模型选择 | 手机底部选项面板保留选中状态和清晰描述。桌面菜单按实际高度锚定。联网仍由独立开关控制 |
| 微信包 | 增加独立预览与联网构建。预览包可导入开发者工具，联网包由 AppID 和 HTTPS 域名定向构建 |
| 交付范围 | 小程序结构与编译产物通过检查。微信模拟器、胶囊、原生键盘和扫码真机待验收，APP 后续单独打包 |

前端 41 项、后端 66 项回归通过。桌面和手机网页已检查。微信预览包 1.10 MiB，本机未安装微信开发者工具，模拟器与真机待验收。

[浏览器验收记录](docs/validation/ui-1.3.1.json) · [微信构建与部署](docs/wechat-deployment.md)。

网页发布源为 766078e，[构建与部署](https://github.com/ChenZHIHAO-dev/AgriVision-system/actions/runs/44237714060)通过，[12 项线上资源](docs/validation/pages-1.3.1.json)与本机构建一致。

界面规则参考 [Apple Toolbars](https://developer.apple.com/design/human-interface-guidelines/toolbars) 和 [Android App bars](https://developer.android.com/develop/ui/compose/components/app-bars) 组织页面工具与阅读空间；参照 [Android Menus](https://developer.android.com/develop/ui/compose/components/menu) 和 [WAI 模态对话框](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/) 明确选项、关闭与焦点；按 [W3C 拖动规范](https://www.w3.org/WAI/WCAG22/Understanding/dragging-movements) 保留单击替代；依据 [GOV.UK 问题页规范](https://design-system.service.gov.uk/patterns/question-pages/) 在应用需要时才收集作物资料。

## 开发记录 · 2026-11-18 / 1.3 手机交互

本轮按手机网页、桌面网页和小程序分别处理导航与输入，详细规则及逐项状态见 [1.3 交互与平台清单](docs/mobile-interactions-v1.3.md)。

| 模块 | 当前结果 |
| --- | --- |
| 手机顶栏 | 核心导航常驻；顶端与前 80px 始终显示工具；深度滚动才按方向收放，1.2 秒只收尾次级工具 |
| 页面上下文 | 工作台、拍照、资料、我的、聊天采用不同标题和工具；资料搜索 / 筛选吸顶 |
| 并行咨询 | 首页增加明显的文字咨询入口；拍照页扩大“直接问”入口，无需先传照片 |
| 底部导航 | 三等分保留；长按玻璃滑块、拖动预览、释放切换；图标和底色持续体现选中 |
| 输入 | 空输入一行 24px，最多八行 192px 后内部滚动；手机换行 / 桌面发送分开处理 |
| 键盘 | 保留应用画布尺寸，只移动输入区或登录窗口；浏览器缩小可视区域模拟通过 |
| 联网开关 | 仅右侧开关响应，说明区域不再整块点击或跳动 |
| 外观 | 手机外观切换保留在“我的”顶栏与设置；桌面仍在登录旁；图标加粗并分别生成深浅色资源 |
| 平台边界 | H5 使用 VisualViewport；微信使用原生键盘事件与胶囊安全区；APP 待打包 |
| 验证 | 前端 39 项、类型、格式通过；H5 / 微信小程序 / Pages 构建通过；未重新训练或调用付费对话 |

浏览器检查：390×844、390×650、1280×800；键盘以 390×480 可视区域模拟。实际 iOS / Android 软键盘、触摸长按、微信胶囊和相机仍需真机验收。数据见 [UI 验证](docs/validation/ui-1.3.json)。

本轮只更新客户端，服务端接口版本仍为 1.2.2-dev.1，识别模型与 DeepSeek 服务沿用现有实现。发布来源：`61cdb3f`。[GitHub 构建与部署](https://github.com/ChenZHIHAO-dev/AgriVision-system/actions/runs/44227095684)成功，12 项线上资源与本机构建一致，见 [公开资源校验](docs/validation/pages-1.3.json)。Pages 仍为前端预览。

## 开发记录 · 2026-11-18 / 1.2.2

本轮按“主页面 → 结果窗口 / 聊天 → 详情”的层级重整交互，详细任务与验收见 [79 项清单](docs/interaction-hierarchy-v1.2.2.md)。

| 模块 | 当前结果 |
| --- | --- |
| 主导航 | 首页、拍照、我的三等分；默认拍照；同一入口重复点击不重置当前问诊 |
| 结果窗口 | 拍照完成显示圆角窗口；关闭回到拍照页，可通过“查看本次识别”恢复 |
| 聊天返回 | 沉浸式聊天隐藏底部导航；明确显示返回目标；详情关闭只返回聊天 |
| 窗口事件 | Escape 每次只关闭最顶层；关闭后恢复触发控件焦点；遮罩下内容不可键盘进入 |
| 基本信息 | 程序收集作物和生育期；没有问题时仅保存选择；已有问题补齐后自动恢复原问题 |
| 对话幂等 | 保存原问题与附件引用；恢复只追加助手回答；重复请求重放原结果，不重复调用 |
| 聊天与历史 | 照片和聊天共用问诊记录；电脑为窄主导航 + 宽历史侧栏；手机为左侧抽屉 |
| 草稿 | 查看识别详情保留聊天与多行草稿；不同问诊分开保存；账户切换清空内存草稿 |
| 首页资料 | 首页“最近问诊 / 参考资料”栏目；资料支持网格、列表、知识与资讯；我的不再放资料入口 |
| 外观 | 登录/头像旁直接循环浅色、深色、跟随系统；设置继续保留三选一；中性灰黑、微灰浅色 |
| 控件 | 统一 Lucide 圆润线性图标和浅底反馈；深色不使用错误反色滤镜；明确的退出登录按钮 |
| 输入 | 长文本在输入框内滚动；聊天输入固定在可视区域底部；保留手机键盘适配 |
| 识别 | 沿用本机 EfficientNet-B0 小麦实验模型；独立识别和本地简要建议不调用 DeepSeek |
| 多图 | 逐张保留识别、未知和质量状态，归纳一致/部分支持/冲突；不计算跨图均值 |
| 对话 | Flash / Pro、思考开关；Flash 可选联网；仅传文字、识别回执与检索材料，不传原图 |
| 隐私与权限 | 访客临时上下文只在服务端内存；账户记录由服务端隔离；管理员配置入口继续受权限保护 |
| 验证 | 后端 65 项、前端 22 项通过；类型/格式通过；H5、小程序、Pages 构建通过 |
| 真实联调 | 独立识别、多图部分支持、基本信息零调用、Flash 恢复原问题与 Pro 思考通过 |
| 发布 | 1.2.2 构建与部署成功，12 项线上资源与本机构建一致；Pages 仅运行前端预览 |

验证文件：[本地识别与对话](docs/validation/local-pipeline-1.2.2.json) · [浏览器界面与层级](docs/validation/ui-1.2.2.json)。

2026-11-18 发布来源：`3c085a7`。[构建与部署](https://github.com/ChenZHIHAO-dev/AgriVision-system/actions/runs/44138296758) · [线上资源一致性](docs/validation/pages-1.2.2.json)。79 项清单中 78 项完成，F08 为真机验收待办。

浏览器实测 390×844、760×900、1280×720；键盘用 390×480 可视区域模拟。**实际 iOS / Android 软键盘、相机权限和微信真机仍需验收**。页面内返回与 Escape 已测试；浏览器原生历史和设备返回手势不等同于页面内返回栈，单独列为后续适配。

本轮清理了 80 条旧布局样式和已弃用图标，没有创建项目备份副本。第三方图标来源与重建方式见 [许可说明](THIRD_PARTY_NOTICES.md)。

上一版本：1.2.1 发布源 a18c312，已通过 [构建与部署](https://github.com/ChenZHIHAO-dev/AgriVision-system/actions/runs/44118457289) 与 [线上资源校验](docs/validation/pages-1.2.1.json)。历史接口与界面报告保留在 docs/validation。

## 本机使用

```powershell
.\scripts\Start.ps1
```

打开 [本机应用](http://127.0.0.1:8000/?mode=live)。本机 8000 端口自动连接同源后端，无需在普通用户设置中填写服务地址。接口文档：[API](http://127.0.0.1:8000/docs)。

停止服务：`.\scripts\Stop.ps1`。更新前端后运行 `npm run build` 并刷新页面；修改后端后使用项目的 Stop / Start 脚本重启。

测试账户：**admin / admin123**。当前账户提供器没有账户数据库，注册、登录、登出和权限流程均在服务端执行：

- 注册账号与登录令牌只在本次服务运行期间有效，重启后失效。
- 登录问诊保存在服务器本地 SQLite，按服务端账户 ID 隔离。固定 admin 身份可以重新登录读取原记录。
- 注册用户的稳定账户、长期历史恢复、正式数据库、云端部署和跨设备同步尚未接入。
- 访客只保留当前上下文，30 分钟无活动过期，不提供历史列表。

新环境先运行 `.\scripts\Setup.ps1 -WithCuda`。GitHub 不含数据、模型权重或密钥，环境与复现见 [开发文档](docs/development.md)。

应用默认进入拍照页。首页提供拍照问诊和文字咨询两个入口，下方展示最近记录与参考资料；拍照页也可直接进入文字咨询。账户与设置在我的中。

## 核心流程

1. 拍照页选择小麦、玉米或花生，拍照或上传图片。本版实际权重只支持小麦；其他作物不伪造病名。
2. 图片由独立 CNN 检查；结果窗口给出初步标签、候选分数和知识建议。关闭后仍可恢复本次结果。未知、需补拍、服务错误分别显示。
3. 点击继续对话，保留原照片和识别摘要。聊天有独立返回入口，底部主导航暂时隐藏；查看识别详情会打开新窗口。
4. 用户发送问题后，基本信息不足时由程序显示选择卡；补齐后自动回答原问题。DeepSeek 根据文字、结构化识别结果和资料摘录解释，不接收原图。
5. 聊天中可以继续添加图片、TXT、MD、可复制文字的 PDF 或 DOCX。每条问诊最多 6 张图、6 份资料，单文件 8MB。

药剂产品库目前为空。具体剂量、混配和用法需有审核过的产品标签与适用条件，程序不根据未经核验的资料编造配方。

## 密钥与部署

密钥放在 `secrets/deepseek.env`，支持带引号的 `DEEPSEEK_API_KEY="在本机填写"`。已填写的文件不需要重填。开发代理未读取该文件，只有后端运行时加载。

密钥、数据集、权重、用户图片、业务数据库和运行日志不提交 Git。前端不会包含 DeepSeek 密钥；后端连接地址通过部署环境 `VITE_API_BASE_URL` 设置，普通用户不承担服务配置。

[GitHub Pages](https://chenzhihao-dev.github.io/AgriVision-system/) 可用于检查前端布局。Pages 不运行 Python、识别模型或 DeepSeek 密钥。手机使用真实识别与对话，需要手机可达的后端 HTTPS 服务；手机的 localhost 指向手机本身。本机默认只监听回环地址。

## 手动试用照片

独立目录：`F:\college\AgriVision\data\manual-tests\wheat-real-photos`。

其中有 10 张实拍照片、来源与许可、参考说明和空白试用表。未纳入训练、校准或评分，也没有由代理提前批量识别。黄化照片没有确诊标签；条锈病照片为二粒小麦，用于跨品系试用。不能将这些照片当作南阳田间评测集。

## 模型范围

本机 RTX 3060 已完成 EfficientNet-B0 初版训练。训练 / 验证 / 测试为 4,458 / 917 / 940 张；模型版本 `20261117-092348`。

内部测试准确率 94.68%、Macro-F1 94.65%。这不是南阳田间准确率；界面上的单图分数也不是确诊概率。模型保持实验状态，详细数据来源、近重复处理和独立性限制见 [模型说明](docs/model-card-wheat-v1.md)。

## 项目结构与检查

- `apps/client`：网页、小程序共用前端及可复用界面组件。
- `services/api/app`：账户、问诊记录、图像识别、对话与资料处理。
- `knowledge`：审核资料、产品库与精选资讯。
- `ml`：数据处理、训练与评测。
- `scripts`：环境、启动、发布与本地联调工具。
- `tests`、`docs/validation`：回归检查和脱敏验证记录。
- `data`、`artifacts`、`runtime`、`secrets`：本地私有运行资料，均不上传。

```powershell
npm run test:frontend
npm run typecheck
npm run format:check
npm run build
npm run build:mp
npm run build:wechat
npm run build:pages
.venv\Scripts\python.exe -m pytest -q

# 默认只检查本地流程；加参数会真实调用对话 API
.venv\Scripts\python.exe scripts/verify_local_pipeline.py --exercise-provider --web
```

推送 main 后由 GitHub Actions 检查、构建并部署 Pages。历史 1.2 发布记录见 [验证记录](docs/validation.md)，当前状态以本 README 为准。历史规则见 [1.3.0 清单](docs/mobile-interactions-v1.3.md) 与 [1.2.2 清单](docs/interaction-hierarchy-v1.2.2.md)。

## 后续待办

- [ ] iOS / Android 键盘、微信拍照权限与真机测试。
- [ ] 正式账户数据库、稳定用户身份、服务器 HTTPS 部署与配额。
- [ ] 公司产品标签与审核产品方案，资料维护和资讯自动更新。
- [ ] 南阳田间采集与农技复核，之后再迭代小麦效果和玉米、花生模型，可迁移 AutoDL。
- [ ] 流式回答、扫描文档 OCR、向量检索。
