# 微信小程序开发与部署

## 先看小程序效果

在项目根目录运行 `npm run build:wechat`。用[微信开发者工具](https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html)导入 `apps/client/dist/wechat/preview`，项目类型选“小程序”。本机完整路径为 `F:\college\AgriVision\apps\client\dist\wechat\preview`。

预览包带默认游客 AppID，用于开发者工具模拟器。可在模拟器检查顶部安全区、资料筛选、长按切换和文字咨询。选择照片可检查上传后的界面与状态提示，演示资料在本地处理。真实识别、DeepSeek 和账户服务需要联网包。用于微信扫码预览时，先在微信公众平台建立小程序项目，并使用有开发权限的微信账号及对应 AppID；预览包可以设置自己的 AppID，仍可离线用样例。微信模拟器和扫码真机是两次独立验收。[uni-app 构建与导入说明](https://uniapp.dcloud.net.cn/quickstart-cli.html)

## 联网构建

复制 `.env.wechat.example` 为 `.env.wechat.local`，填写以下两项。目录 `dist/wechat/preview` 与 `dist/wechat/live` 是不同构建产物，指定的 AppID 和后端域名可从包中看到。将 AppSecret、DeepSeek 密钥和数据库配置留在服务端。

| 构建参数 | 值 |
| --- | --- |
| `AGRIVISION_WECHAT_APP_ID` | 微信公众平台对应的小程序 AppID |
| `VITE_API_BASE_URL` | 自有 HTTPS API 域名，例如 `https://api.example.com`。填域名，不带 `/api` 路径或其他参数 |

```powershell
Copy-Item .env.wechat.example .env.wechat.local
# 填写本地文件中的 AppID 和后端域名，再运行下一行。
npm run build:wechat -- --live
```

导入 `apps/client/dist/wechat/live`。联网包缺少合法格式的 AppID 或 HTTPS 域名时会停止构建。模式和地址由包确定，切换部署地址时重新打包。Git 忽略本地配置和构建目录。原来的 `npm run build:mp` 仍用于直接检查 uni-app 编译。

微信公众平台的开发设置中，将实际 API 域名添加为 request 和 uploadFile 合法域名。图片预览涉及远程图片读取，同一域名也加入 downloadFile 合法域名。域名需要有效 HTTPS 证书，并符合微信后台的域名要求。开发者工具应保持域名校验开启，再用体验版测试手机网络、上传和长对话。[腾讯云网络配置](https://intl.cloud.tencent.com/zh/document/product/1219/61745)

## 服务部署边界

| 部署位置 | 内容 |
| --- | --- |
| GitHub Pages 或自己的站点 | H5 静态网页。桌面与手机宽度使用网页响应式布局 |
| 微信平台 | 微信小程序前端产物，由开发者工具上传。包括编译后的页面、交互代码、公共图标和演示资料 |
| 自己的服务器 | `services/api`、依赖、审核资料、推理所需的模型和标签、账户与持久化记录，环境变量及服务端密钥 |
| APP | 原生构建项目、证书签名和设备测试另行安排，选用同一套服务端接口 |

服务器用域名和 HTTPS 反向代理提供 `/api/`，Python 进程可继续监听服务器本机。先检查 `/api/health` 和 `/api/meta`，再测试拍照上传、小麦模型、咨询和历史。反向代理请求体限制要能容纳 8 MiB 的文件及 multipart 额外数据。聊天请求的代理等待时间需覆盖后端预算，长思考还需实测微信网络层的超时；若超时，应将该请求改为异步任务和轮询。

服务器需要的是推理资源。训练可以使用原来的 3060 或单独租 GPU；对外 API 机器是否需要 GPU，可根据目标并发与 CPU 推理延迟决定。临时开发账户和内存会话用于本机测试。对外开放 API 前应替换默认管理员和开发账户存储，实施访问控制、上传限制、用量配额，并准备数据备份及隐私说明。当前开发会话依赖单进程内存，直接开多个 worker 会造成登录与访客状态不一致。

## 登录与验收顺序

1. 先验证游客打开应用、选择作物、拍照处理、继续咨询和历史抽屉布局。游客可体验主要功能，服务端不为游客保存历史。
2. 通过带真实 AppID 的预览包，在 iOS 和 Android 分别测试胶囊安全区、回滑恢复工具、切换资料分类、底部拖动和取消、系统键盘及拍照权限。相机、相册和问诊照片用途需在微信公众平台配置小程序用户隐私保护指引。
3. 接入 HTTPS 后端后，验证低置信识别、已登录历史、附件上传、网络中断和恢复。预览包无需用户登录。联网包当前接已有应用账户接口。若需要微信一键登录，小程序用 `wx.login` 取临时代码，服务端用 AppSecret 换取微信身份并签发自有会话。单独验收身份绑定和会话隔离后再启用。[小程序登录流程](https://intl.cloud.tencent.com/zh/document/product/1219/68263)
4. 使用微信开发者工具上传测试通过的联网前端，按微信公众平台流程发布体验版、提交审核和发布。[uni-app 微信小程序发行说明](https://uniapp.dcloud.net.cn/quickstart-hx.html)

本轮交付为构建和静态产物验证。实际使用开发者工具模拟器、扫码、微信登录、远程服务器和应用商店发布均有各自账号或真机验收条件。
