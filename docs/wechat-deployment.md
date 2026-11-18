# 微信小程序 B 版试用与部署

2026-11-19 首测可用当前 `1.4.0-beta.4`。先在微信开发者工具导入离线预览包，验收首页、资料和咨询。手里有小程序 AppID 时，再用同一预览包扫码测试手机上的手势、键盘和相机。接入真实识别、DeepSeek 和账户后再测试联网包。

## 在电脑上试用

1. 安装微信开发者工具稳定版，并按工具提示用微信登录。[官方下载](https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html)
2. 已在本机准备好项目依赖时，从 PowerShell 运行这两行。新环境先准备 Node.js 24，并在项目根目录运行 `npm ci --ignore-scripts --no-audit --no-fund` 安装前端依赖。

   ```powershell
   Set-Location -LiteralPath 'F:\college\AgriVision'
   npm run build:wechat
   ```

3. 在微信开发者工具选「小程序」→「导入」，目录选 `F:\college\AgriVision\apps\client\dist\wechat\preview`。该目录直接包含 `project.config.json` 和 `app.json`。已注册小程序时，建议把 AppID 输入框里的 `touristappid` 直接换成自己的小程序 AppID，选择「小程序」和「不使用云服务」。部分工具版本或导入模式会拒绝游客 AppID 并显示「游客 AppID 无法使用此功能」。如果暂时没有自己的 AppID，可按工具界面申请「测试号」。[uni-app 微信小程序导入说明](https://uniapp.dcloud.net.cn/quickstart-hx.html)
4. 点「编译」，在模拟器打开首页。以后更新代码后重新运行构建，再点「编译」加载新包。预览包自带演示数据，咨询返回模拟回复，登录界面可查看。真实账号登录、识别和模型回答使用联网包。

运行 `npm run build:wechat` 的机器只需前端依赖。模拟器适合检查页面和交互。相机拍摄、微信顶部胶囊、键盘及手势表现以真机为准。

## 用手机微信扫码

1. 登录微信公众平台，打开「账号设置 → 账号信息」，复制显示为「AppID（小程序 ID）」的 wx 开头编号。也可在「开发管理 → 开发设置」查看。gh_ 开头的是原始 ID。开发者工具使用该项目的管理员或已添加为开发者的微信号登录。[腾讯云 AppID 查询指引](https://cloud.tencent.com/document/product/1759/122555)
2. 已在导入框手动填入自己的 AppID 时，可以直接使用预览按钮。希望以后的构建自动写入 AppID 时，复制 `.env.wechat.example` 为 `.env.wechat.local`，填 `AGRIVISION_WECHAT_APP_ID`。预览阶段可留空 `VITE_API_BASE_URL`。执行 `npm run build:wechat`，重新导入预览目录，并确认导入窗口显示自己的 AppID。
3. 在工具里点「预览」，用有权限的微信账号扫二维码。此时测试的是微信运行环境中的离线包。要邀请他人持续测试，由具备上传权限的账号在工具里上传，再在公众平台将对应开发版本设为体验版、添加体验成员，并发体验版二维码。[uni-app 微信小程序发行说明](https://uniapp.dcloud.net.cn/quickstart-hx.html)
4. 从微信公众平台填写实际会用到的照片、相机和附件相关隐私说明。用真实 AppID 构建后，在真机上分别验证首次授权、拒绝后恢复和取消选图。若报隐私接口未声明或未授权，检查后台声明及代码的同意流程。[DCloud 小程序隐私协议开发指南](https://uniapp.dcloud.io/tutorial/mp-weixin-user-privacy.html)

## 首测清单

| 场景 | 操作与预期 |
| --- | --- |
| 首页资料 | 点最近问诊、参考资料和农业资讯，内容在首页下半区切换。往下滑时搜索仍可用，点筛选可以重新展开。切到花生等短列表时卡片仍从上方开始。 |
| 空咨询与有消息 | 进入文字咨询，检查空态提示和快捷问题的位置。发送一句普通问题，再从会话标题处打开菜单，检查标题及相关操作、返回层级和草稿。 |
| 底栏及外观 | 分别单击和按住横拖切页。切换浅色和深色，检查按钮按下时的文字对比、当前页状态及作物图标。 |
| 窄屏与键盘 | 换一个较窄的模拟器尺寸，再在真机打开输入键盘。检查顶部胶囊、底部输入区、弹层和表格的换行与留白。 |
| 相机与相册 | 在真机分别尝试允许、拒绝、返回取消、选图后返回。离线包用来验证选图和反馈，联网包加入真实上传和识别结果。 |
| 联网与账号 | 联网包测试访客问答、登录后历史、会话标题修改后重新打开、识别失败反馈、附件上传及断网恢复。这个环节等服务部署完再验收。 |

记录问题时附上测试端（H5、微信模拟器或微信真机）、版本、手机型号、微信版本、出问题前的两三步和截图。涉及照片时使用样例图或遮挡个人信息。

## 接入真实服务

使用 `.env.wechat.local` 保留预览阶段的 AppID，并补填 HTTPS API 域名。Git 忽略本地配置和编译目录。AppSecret、DeepSeek 密钥和数据库设置放在服务端。

| 构建参数 | 填写内容 |
| --- | --- |
| `AGRIVISION_WECHAT_APP_ID` | 微信公众平台分配给该小程序的 AppID |
| `VITE_API_BASE_URL` | HTTPS API 域名，例如 `https://api.example.com`，仅填写域名和协议 |

```powershell
npm run build:wechat -- --live
```

联网包输出到 `F:\college\AgriVision\apps\client\dist\wechat\live`，同样导入微信开发者工具。代码从包里的部署配置读取域名，换域名需重新打包。脚本会校验 AppID 和 HTTPS 域名的格式。

在微信公众平台的「开发管理」→「开发设置」里，为该小程序配置 API 的 request、uploadFile 和 downloadFile 合法域名。后端域名需要有效 HTTPS 证书。保持工具的合法域名校验开启，再实测启动、上传和图片读取。[腾讯云网络配置](https://intl.cloud.tencent.com/zh/document/product/1219/61745)

联网包目前使用应用的账号系统。以后接微信一键登录时，由小程序通过 `wx.login` 获取临时代码，再由服务端换取微信身份并签发会话。[小程序登录流程](https://intl.cloud.tencent.com/zh/document/product/1219/68263)

## CPU 联网试测

小程序沿用本项目的 FastAPI 服务。手机上传照片到 HTTPS API，服务端用已训练的 EfficientNet-B0 小麦模型做推理，再把识别结果和模型版本返给小程序。低并发试测可先用 Linux x86-64 CPU 服务器，记录首次请求、预热后的端到端耗时和并发时的等待时间，再决定是否需要 GPU。对话由后端调用远程 DeepSeek 接口，在服务器上配置密钥即可。

只有本人在电脑上验证时，先使用本机 FastAPI 与网页。外网小程序需要真实识别时，再将同一套代码和模型迁移到云机，配置微信可访问的 HTTPS 域名，然后构建联网体验包。

本机另用临时运行目录执行过 CPU 接口冒烟检查。GET /api/health 返回 200，POST /api/cases 以 multipart 上传一张内部留出样例返回 201。实验版模型 20261117-092348 给出小麦白粉病，冷请求约 2.0 秒。测试走 FastAPI 的本地 HTTP/ASGI 路径，未经过云网关或手机网络。

在本机 Ryzen 9 5900HX 上，将 PyTorch 显式设为 CPU，并使用现有 EfficientNet-B0 小麦模型。暖机后逐张测量质检、转码和 Top 3 预测，现有权重约 15.6 MiB。

| CPU 运算线程 | 30 张内部测试图片 P50 / P95 | 12 次 1200 万像素样例 P50 / P95 |
| --- | --- | --- |
| 2 | 41 / 58 ms | 287 / 340 ms |
| 4 | 26 / 33 ms | 259 / 286 ms |

大图由内部样例放大，用于测量像素量对耗时的影响。峰值单进程工作集约 760 MiB。以上结果为本机串行请求，未计入服务器排队、HTTP、数据库、网络和 DeepSeek。可把 **2 vCPU、4 GB 内存**作为低并发体验版的起测配置，在目标云机上再测手机上传到结果的总耗时与并发。

1. 将仓库代码部署到服务器，保留 `services/api`、`ml` 和 `knowledge`。把可信的 `weights.pt`、`metadata.json` 一起传至 `<AGRIVISION_MODEL_DIR>/wheat/`，默认模型目录为 `artifacts/models`。试测当前实验权重时启用 `AGRIVISION_ALLOW_EXPERIMENTAL_MODELS=1`，保留实验提示。正式开放识别时使用经过验证的模型并设为 `0`。
2. 当前 Windows 启动脚本适合本机。Linux 可在仓库根目录安装 CPU 版依赖并启动一个进程。下列命令用于受控试测，启动后仍需在 HTTPS 网关设置测试网络访问范围。[PyTorch CPU 安装指引](https://pytorch.org/get-started/previous-versions/)

   ```sh
   python3.12 -m venv .venv
   .venv/bin/python -m pip install -r requirements.txt
   .venv/bin/python -m pip install torch==2.7.1 torchvision==0.22.1 --index-url https://download.pytorch.org/whl/cpu
   AGRIVISION_DEVICE=cpu AGRIVISION_ALLOW_EXPERIMENTAL_MODELS=1 \
     .venv/bin/python -m uvicorn app.main:app --app-dir services/api \
     --host 127.0.0.1 --port 8000 --workers 1
   ```

3. 由反向代理将 HTTPS 域名的 `/api/` 原样转发到该进程。账户记录与照片所在目录可用 `AGRIVISION_RUNTIME_DIR` 指向持久盘。网页若跨域访问，再通过 `AGRIVISION_CORS_ORIGINS` 登记网页 origin。识别和对话分别验收，启用对话时通过服务器的环境变量或受保护的配置文件提供 `DEEPSEEK_API_KEY`。
4. 先从试测网络访问 `GET /api/health`、`GET /api/meta`，确认小麦模型的 `ready`、版本和实验标记，再按上一节的 AppID、域名配置生成联网包。真机拍照或从相册上传一张已知小麦样例，查看识别状态和返回图片。再验证弱网、模糊照片以及登录后的历史读取。手机拍照至结果的耗时包含上传、预处理、推理和返回，需在准备租用的规格上复测。

| 功能 | 当前接口 |
| --- | --- |
| 进程和模型状态 | `GET /api/health`、`GET /api/meta` |
| 拍照识别 | `POST /api/cases`，multipart 字段 `file` 和 `crop` |
| 会话与历史 | `POST /api/consultations`、`GET /api/cases`、`GET /api/cases/{case_id}` |
| 发送咨询 | `POST /api/cases/{case_id}/messages` |
| 补充照片、附件与图片预览 | `POST /api/cases/{case_id}/images`、`POST /api/cases/{case_id}/attachments`、接口返回的短期签名图片 URL |

开发版账户和会话在进程内存中，还带有固定的开发管理员。外部用户上线前，需要移除固定管理员、接入可持久化的账户和会话，并为识别上传和付费对话配置限流与用量控制。短期签名图片链接按私有内容处理，代理和日志避免缓存或记录链接中的签名参数。

## H5、微信、小程序后台及 APP

| 端 | 试用与部署方式 |
| --- | --- |
| H5 网页 | [GitHub Pages](https://chenzhihao-dev.github.io/AgriVision-system/) 用手机或电脑浏览器打开，运行网页预览。 |
| 微信小程序 | 导入 `apps/client/dist/wechat/preview` 或 `apps/client/dist/wechat/live`，在开发者工具编译，由微信管理预览、体验版及正式发布。 |
| 应用后端 | 在服务器部署 `services/api`、识别权重、账户和数据库设置。通过 HTTPS 代理提供 `/api/`，由微信与网页各自连接。 |
| APP | 单独完成原生打包、签名和设备测试，可复用现有 API。 |

真实服务先在公网测试环境检查 `/api/health` 和 `/api/meta`，再测试小麦识别、对话和历史。代理的请求体限制需容纳 8 MiB 附件及 multipart 开销。微信端长对话的等待时间需实测。腾讯文档列出小程序网络默认超时和最大超时为 60 秒，后端的超时配置无法延长微信自身上限。长思考若频繁超时，采用异步任务与轮询。[腾讯云网络配置](https://intl.cloud.tencent.com/zh/document/product/1219/61745)

临时开发账户和内存会话适合本机测试。开放真实服务前，先替换默认管理员和开发账户存储，配置访问控制、用量配额、隐私说明和数据备份。当前内存会话只在单进程内共享。推理是否需要 GPU 取决于并发和实测延迟，离线首测可直接在现有电脑完成。
