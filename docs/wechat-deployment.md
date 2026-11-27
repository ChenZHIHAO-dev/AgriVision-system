# 网页、API 与微信小程序部署

当前代码版本为 **1.5.0-beta.7**。主力是网页和微信小程序；App 保留构建能力，尚未做应用商店发布。小程序名称为 **宛田观叶**。

## 已有环境与入口

| 项目 | 当前安排 |
| --- | --- |
| 云服务器 | 阿里云北京，Ubuntu 24.04，2 vCPU、4 GiB、50 GiB；无 GPU |
| 网页 | `https://agrivision.zchenh.xyz`，Caddy 提供静态文件 |
| API | `https://agriapi.zchenh.xyz`；网页域名下 `/api/*` 也转发到同一 API |
| 源码与虚拟环境 | `/opt/agrivision`、`/opt/agrivision/.venv` |
| 后端服务 | `agrivision-api.service`，一个 Uvicorn 进程，监听 `127.0.0.1:8000` |
| 模型 | `/opt/agrivision/artifacts/models/<任务>/weights.pt` 和 `metadata.json` |
| 账户配置与密钥 | `/etc/agrivision/api.env`，权限 600，仅服务端读取 |
| 数据和照片 | `/var/lib/agrivision`，SQLite 与照片均不放进 Git 或网页目录 |
| 网页发布目录 | `/var/www/agrivision` |
| 本机 SSH | PowerShell 输入 `ssh 2v4ali`；使用已有密钥，不把私钥放进项目 |

用户已完成主域名备案及 HTTPS。微信的体验成员、合法域名、隐私声明与代码版本审核仍在微信后台分别管理；网页部署成功不等于微信真机联网已经验收。

## 登录和使用流程

**联网模式全部业务需登录**，自助注册关闭，目前只有管理员内测。照片识别、上传、作物种类识别、问答和历史都由后端校验会话；参考资料和农业资讯无需登录；隐藏前端按钮不能代替鉴权。离线预览保留演示账户、演示图片回执和模拟回答。

普通农业问题可以直接问。照片、作物、生育期和地区按需建议，均可跳过。保存补充资料不调用 AI；用户明确发消息才请求回答。对话中的照片与拍照页调用同一个图像识别模型，不由文字模型猜图。

勾选“保持登录 7 天”的会话把令牌摘要保存在现有 SQLite，可跨服务重启；未勾选则为当前进程内 8 小时会话。退出、到期或更换密码配置都会撤销对应会话。首次从旧内存版本升级需要重新登录一次。图片 URL 有时效并绑定登录会话，退出后旧链接失效。登录失败、识别/上传和问答分别限流，超限返回 429；请求量计数重启会重置，不作为持久化计费记录。服务器当前先设识别并发 1、2 个 Torch CPU 线程。

## 本机开发与微信离线预览

在 Windows PowerShell 进入项目，并使用现有 Node.js 24 与同一个 Python `.venv`：

```powershell
Set-Location -LiteralPath 'F:\college\AgriVision'
npm run build:wechat
```

在微信开发者工具导入 `F:\college\AgriVision\apps\client\dist\wechat\preview`。这里包含 `project.config.json` 和 `app.json`。自己的 AppID 保存在 Git 忽略的 `.env.wechat.local`，字段名是 `AGRIVISION_WECHAT_APP_ID`；也可在开发者工具导入框填写。公开仓库只保留 `touristappid` 占位值。AppSecret 与 DeepSeek 密钥不放前端。

修改代码后重新构建，再点开发者工具“编译”。扫码“预览”可在有权限的微信号上测试。顶部胶囊、键盘动画、相机权限与系统返回必须再看真机，浏览器手机尺寸不等于真机验收。邀请他人持续试用可在微信后台管理体验成员和体验版。

## 微信连接真实 API

编辑 `.env.wechat.local`：填写自己的 AppID，把 `VITE_API_BASE_URL` 设为 `https://agriapi.zchenh.xyz`，只填协议和域名，不追加 `/api`。然后运行：

```powershell
npm run build:wechat -- --live
```

导入 `F:\college\AgriVision\apps\client\dist\wechat\live`。`preview` 是离线演示工程，即使上传成功也不会连接云端模型；真实内测必须从 `live` 工程重新编译、预览或上传，不能继续扫码旧的 preview 版本。微信公众平台“开发管理 → 开发设置”中，将实际 API 域名登记到 request、uploadFile 和 downloadFile 合法域名。保持开发者工具的域名校验开启，用真机检查登录、上传与图片读取。换 API 域名需要重建联网包。 [微信网络说明](https://developers.weixin.qq.com/miniprogram/dev/framework/ability/network.html)

小程序当前使用应用管理员账号；以后接微信身份时由服务端交换临时代码并签发本应用会话，不能把微信 AppSecret 放进小程序。 [微信登录流程](https://developers.weixin.qq.com/miniprogram/dev/framework/open-ability/login.html)

## 云端更新代码和网页

本机先通过测试、提交并推送 Git。云端只拉取已经确认的提交；模型权重与训练照片不在 Git，克隆代码不会自动得到新权重。SSH 登录后，在 Linux 终端分别执行：

```sh
cd /opt/agrivision
git status --short
git pull --ff-only
```

`git status` 有自己尚未保存的修改时先核对，不用 reset 覆盖。依赖确有变化时更新；云机 PyTorch 保持 CPU 版，不安装训练所需 CUDA 包：

```sh
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
npm ci --ignore-scripts --no-audit --no-fund
```

构建真实联网网页：

```sh
VITE_DATA_MODE=live VITE_API_BASE_URL=https://agrivision.zchenh.xyz UNI_H5_BASE=/ npm run build
```

产物是 `apps/client/dist/build/h5`。将这份完整产物同步到 `/var/www/agrivision`，不发布 `.env`、原图、模型或源码目录。网关把 `/api/*` 转发到 `127.0.0.1:8000`，上传上限 10 MB；后端单文件上限 8 MiB、图片解码上限 24 MP。

在受保护的 `/etc/agrivision/api.env` 中维护部署配置：

| 设置 | 当前用途 |
| --- | --- |
| `AGRIVISION_DEVICE=cpu` | 云端 CPU 推理 |
| `AGRIVISION_MODEL_DIR=/opt/agrivision/artifacts/models` | 按任务查找完整模型包 |
| `AGRIVISION_RUNTIME_DIR=/var/lib/agrivision` | 持久化记录和照片 |
| `AGRIVISION_ALLOW_EXPERIMENTAL_MODELS=1` | 单管理员内部测试已评估但未完成田间验收的模型 |
| `AGRIVISION_SERVE_WEB=0` | 网页由 Caddy 提供 |
| `AGRIVISION_CORS_ORIGINS=https://agrivision.zchenh.xyz` | 实际网页来源 |
| `AGRIVISION_RECOGNITION_CONCURRENCY=1` | 避免两核 CPU 同时进行多次推理 |
| `OMP_NUM_THREADS=2`、`MKL_NUM_THREADS=2` | CPU 运算线程 |
| `AGRIVISION_BUILD_COMMIT` | 填本次实际部署的 Git 完整提交号，由 health/meta 返回 |

管理员哈希使用 `scripts/hash_admin_password.py` 在隐藏输入终端生成。重置只替换管理员哈希，保留 DeepSeek 等其他设置；密码和哈希不写入普通日志。配置完成后：

```sh
sudo systemctl restart agrivision-api.service
sudo systemctl is-active agrivision-api.service
```

同时检查网页域名和 API 域名下的 `/api/health`，确认 `version`、`build_commit` 一致；`/api/meta` 中每项模型的版本独立核对。

## 模型怎样上线

每个模型包包含架构、输入尺寸、标签顺序、校准温度、阈值、权重与版本。上传到暂存目录，校验 SHA256，先做 CPU 加载与样图验收，再成对替换正式目录中的 `weights.pt` 和 `metadata.json`。交叉验证原开发折包 `development_only=true` 不直接当发布包。当前DINO通过 `internal_preview.py` 验证原final779张的隔离和93%整体门槛后，另导出保留源身份的管理员预览包；这不等于重训或田间验收。先保留一个可回退的上一版模型，不能混用两版 metadata 与权重。

| 模型任务 | 服务目录 |
| --- | --- |
| 小麦病害 | `artifacts/models/wheat` |
| 玉米病害 | `artifacts/models/maize` |
| 花生病害 | `artifacts/models/peanut` |
| 作物种类 | `artifacts/models/crop-identification` |

2026-11-27 已在这台 2 vCPU 云机测八类 Swin-T 224 候选包：27,525,506 参数，加载 1.27 秒；32 次预热后串行推理 P50 **546 ms**、P95 **564 ms**，测试进程峰值 **507 MiB**。范围是读图、预处理和网络，不含 HTTP、手机上传、数据库或排队。8 张内部样图用于兼容性检查，不能据此宣称田间准确率。记录保存在本机 `.cache/cloud-deploy/benchmark-wheat.json`。

花生内测包为 ConvNeXt-Tiny 320、版本 `20261126-205154`，四类标签，约 27.82M 参数。相同云机两线程实测串行 P50 780 ms、P95 818 ms、独立进程峰值 507 MiB；已通过两域名的四类样图 HTTP 上传与读取。样图用于兼容性，不替代田间评价。当前启用小麦和花生，玉米外域失败、作物种类未达标，均不启用。具体源码版本继续以 health 的 `build_commit` 为准。

## 发布验收

1. 两个域名的健康信息、源码提交号一致，网页能打开。
2. 退出状态的识别、上传、问答和历史均为 401；公开参考资料列表及详情可读取；注册固定 403。伪造 `X-Client-ID` 不能越权。
3. 管理员登录后上传已知样图，确认实际模型版本、标签和照片可读；勾选保持登录后重启服务，记录与未过期图片链接仍可用；退出后旧会话与旧图片链接不能再用。
4. 普通知识直接回答，症状问题可出现补图/地区建议；跳过后仍能继续，选资料不会自动请求外部模型。
5. 上传模糊/纯色控制图、过大文件，检查提示与资源约束；超过限额返回 429 而非无限排队。
6. 在微信联网包真机复验登录、拍照、长结果滚动、键盘、安全区和断网恢复。

本机可用下列命令检查真实云端。默认只检查匿名拒绝；指定账号后隐藏输入密码，创建并清理本次测试记录，不消耗 DeepSeek 用量：

```powershell
.\.venv\Scripts\python.exe scripts/verify_local_pipeline.py --base https://agrivision.zchenh.xyz --username admin
```

把 `--base` 换成 `https://agriapi.zchenh.xyz` 再检查另一入口。只有明确加 `--exercise-provider` 或 `--web` 才会产生真实外部问答请求。开发与训练命令分别见 [开发说明](development.md) 和 [训练清单](recognition-training-checklist.md)。

### 2026-11-27 四模型内测状态

云端 `9c45f05` 已注册小麦8类、玉米4类、花生4类、作物种类14类，均标记experimental且只允许登录后使用。DINO所需timm1.0.31及依赖已补齐，CPU torch2.7.1 / torchvision0.22.1保持。云端2线程独立DINO基准P50 1514ms、P95 1560ms、峰值981MiB；四模型被API加载后的systemd内存峰值约1.26GiB，单worker、识别并发1保持。

本次 `live` 小程序包指向 `https://agriapi.zchenh.xyz`，启用 `lazyCodeLoading=requiredComponents`，未引用的field-art.png不再打包；约0.67MiB，无单张超过200KiB的PNG。开发工具服务端口关闭，因此没有宣称模拟器/真机已验收。先导入live目录、重新编译并扫码；如果仍无法联网，核对微信后台request、uploadFile、downloadFile合法域名和本次扫码包版本。代码上传成功不等于联网验证通过。
