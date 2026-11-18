import { spawnSync } from 'node:child_process'
import { readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs'
import { isIP } from 'node:net'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../', import.meta.url))
const args = process.argv.slice(2)
if (args.length > 1 || (args.length === 1 && args[0] !== '--live')) {
  throw new Error('用法：npm run build:wechat [-- --live]')
}
if (!process.env.npm_execpath) throw new Error('请使用 npm run build:wechat')

const mode = args[0] === '--live' ? 'live' : 'preview'
const appid = process.env.AGRIVISION_WECHAT_APP_ID?.trim() || 'touristappid'
if (appid !== 'touristappid' && !/^wx[a-f0-9]{16}$/i.test(appid)) {
  throw new Error('AGRIVISION_WECHAT_APP_ID 应填写微信公众平台分配的小程序 AppID')
}
if (mode === 'live' && appid === 'touristappid') {
  throw new Error('联网包需要在 .env.wechat.local 中填写 AGRIVISION_WECHAT_APP_ID')
}

function httpsOrigin(value) {
  const url = URL.canParse(value) ? new URL(value) : null
  if (
    !url ||
    url.protocol !== 'https:' ||
    !url.hostname.includes('.') ||
    isIP(url.hostname) ||
    url.port ||
    url.pathname !== '/' ||
    url.href !== url.origin + '/' ||
    !/^https:\/\/[^/?#]+\/?$/i.test(value)
  ) {
    throw new Error('VITE_API_BASE_URL 应为后端 HTTPS 域名，例如 https://api.example.com')
  }
  return url.origin
}

const base = mode === 'live' ? httpsOrigin(process.env.VITE_API_BASE_URL?.trim() || '') : ''
const output = path.join(root, 'apps/client/dist/wechat', mode)
const build = spawnSync(process.execPath, [process.env.npm_execpath, 'run', 'build:mp'], {
  cwd: root,
  stdio: 'inherit',
  env: {
    ...process.env,
    UNI_OUTPUT_DIR: output,
    VITE_WECHAT_PACKAGE: mode,
    VITE_DATA_MODE: mode,
    VITE_API_BASE_URL: base,
  },
})
if (build.error) throw build.error
if (build.status !== 0) process.exit(build.status || 1)

const app = JSON.parse(readFileSync(path.join(output, 'app.json'), 'utf8'))
const entry = app.pages?.[0]
if (!entry || !statSync(path.join(output, entry + '.wxml')).isFile()) {
  throw new Error('微信构建产物缺少入口页面')
}
const projectFile = path.join(output, 'project.config.json')
const project = JSON.parse(readFileSync(projectFile, 'utf8'))
if (project.compileType !== 'miniprogram') throw new Error('微信构建产物的项目类型无效')
project.appid = appid
project.setting = { ...project.setting, urlCheck: true }
writeFileSync(projectFile, JSON.stringify(project, null, 2) + '\n')

const compiled = readFileSync(path.join(output, 'lib/transport.js'), 'utf8')
if (!compiled.includes('environmentMode:' + JSON.stringify(mode))) {
  throw new Error('小程序产物没有包含预期的数据模式')
}
if (base && !compiled.includes('environmentBase:' + JSON.stringify(base))) {
  throw new Error('小程序产物没有包含预期的后端地址')
}
const compiledExtensions = new Set(['.js', '.json', '.wxml', '.wxss', '.wxs', '.png'])
let bytes = 0
for (const file of readdirSync(output, { recursive: true, withFileTypes: true })) {
  if (file.isDirectory()) continue
  if (
    !file.isFile() ||
    file.name.startsWith('.') ||
    !compiledExtensions.has(path.extname(file.name))
  ) {
    throw new Error('小程序包发现意外文件：' + file.name)
  }
  bytes += statSync(path.join(file.parentPath, file.name)).size
}
console.log('WeChat ' + mode + ' output: ' + output)
console.log('Compiled files: ' + (bytes / (1024 * 1024)).toFixed(2) + ' MiB')
