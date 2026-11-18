# 微信小程序 B 版试用与部署

2026-11-19 首测使用 `1.4.0-beta.1`。先在微信开发者工具导入离线预览包，验收首页、资料和咨询。手里有小程序 AppID 时，再用同一预览包扫码测试手机上的手势、键盘和相机。接入真实识别、DeepSeek 和账户后再测试联网包。

## 在电脑上试用

1. 安装微信开发者工具稳定版，并按工具提示用微信登录。[官方下载](https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html)
2. 已在本机准备好项目依赖时，从 PowerShell 运行这两行。新环境先准备 Node.js 24，并在项目根目录运行 `npm ci --ignore-scripts --no-audit --no-fund` 安装前端依赖。

   ```powershell
   Set-Location -LiteralPath 'F:\college\AgriVision'
   npm run build:wechat
   ```

3. 在微信开发者工具选「小程序」→「导入」，目录选 `F:\college\AgriVision\apps\client\dist\wechat\preview`。选中的目录直接包含 `project.config.json` 和 `app.json`。无 AppID 时选工具界面提供的游客模式，项目默认使用 `touristappid`。如界面提示选择云服务，选「不使用云服务」。[uni-app 微信小程序导入说明](https://uniapp.dcloud.net.cn/quickstart-hx.html)
4. 点「编译」，在模拟器打开首页。以后更新代码后重新运行构建，再点「编译」加载新包。预览包自带演示数据，咨询返回模拟回复，登录界面可查看。真实账号登录、识别和模型回答使用联网包。

运行 `npm run build:wechat` 的机器只需前端依赖。模拟器适合检查页面和交互。相机拍摄、微信顶部胶囊、键盘及手势表现以真机为准。

## 用手机微信扫码

1. 登录微信公众平台，找到自有小程序的 AppID，并确认用于登录开发工具的微信号在项目里有开发权限。[微信公众平台](https://mp.weixin.qq.com/)
2. 首次配置时复制 `.env.wechat.example` 为 `.env.wechat.local`，填 `AGRIVISION_WECHAT_APP_ID`。预览阶段可留空 `VITE_API_BASE_URL`。执行 `npm run build:wechat`，重新导入预览目录，并确认导入窗口显示自己的 AppID。
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

## H5、微信、小程序后台及 APP

| 端 | 试用与部署方式 |
| --- | --- |
| H5 网页 | [GitHub Pages](https://chenzhihao-dev.github.io/AgriVision-system/) 用手机或电脑浏览器打开，运行网页预览。 |
| 微信小程序 | 导入 `apps/client/dist/wechat/preview` 或 `apps/client/dist/wechat/live`，在开发者工具编译，由微信管理预览、体验版及正式发布。 |
| 应用后端 | 在服务器部署 `services/api`、识别权重、账户和数据库设置。通过 HTTPS 代理提供 `/api/`，由微信与网页各自连接。 |
| APP | 单独完成原生打包、签名和设备测试，可复用现有 API。 |

真实服务先在公网测试环境检查 `/api/health` 和 `/api/meta`，再测试小麦识别、对话和历史。代理的请求体限制需容纳 8 MiB 附件及 multipart 开销。微信端长对话的等待时间需实测。腾讯文档列出小程序网络默认超时和最大超时为 60 秒，后端的超时配置无法延长微信自身上限。长思考若频繁超时，采用异步任务与轮询。[腾讯云网络配置](https://intl.cloud.tencent.com/zh/document/product/1219/61745)

临时开发账户和内存会话适合本机测试。开放真实服务前，先替换默认管理员和开发账户存储，配置访问控制、用量配额、隐私说明和数据备份。当前内存会话只在单进程内共享。推理是否需要 GPU 取决于并发和实测延迟，离线首测可直接在现有电脑完成。
