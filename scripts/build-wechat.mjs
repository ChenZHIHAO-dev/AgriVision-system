import { spawnSync } from 'node:child_process'
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  realpathSync,
  renameSync,
  rmSync,
  statSync,
  writeFileSync,
} from 'node:fs'
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
const buildParent = path.join(root, 'apps/client/dist/wechat')
mkdirSync(buildParent, { recursive: true })
const parent = realpathSync(buildParent)
const output = path.join(parent, mode)
const prefix = '.' + mode + '-build-'
const staged = mkdtempSync(path.join(parent, prefix))
const compileSettings = { compileHotReLoad: false, ignoreDevUnusedFiles: false }

const compiledExtensions = new Set(['.js', '.json', '.wxml', '.wxss', '.wxs', '.png'])

function checkStylesheet(filePath) {
  // Skip strings and comments before checking rule preludes. WXSS accepts
  // multiplication in declarations such as calc(), but no universal selectors.
  const stylesheet = readFileSync(filePath, 'utf8').replace(
    /\/\*[\s\S]*?\*\/|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'/g,
    '',
  )
  for (const [, prelude] of stylesheet.matchAll(/(?:^|(?<=[{}]))([^{}]*)\{/g)) {
    const selector = prelude.trim()
    if (selector.startsWith('@')) continue
    if (/(?:^|[\s,>+~(|])\*(?=$|[\s.#:,>+~)\[])/.test(selector)) {
      throw new Error(
        path.relative(staged, filePath) + ' 含微信 WXSS 不支持的通配选择器：' + selector,
      )
    }
  }
}

function publish(files, entry, projectName) {
  // Fully validate before touching the project the IDE is watching.
  const privateName = 'project.private.config.json'
  const privateFile = path.join(output, privateName)
  if (existsSync(privateFile)) {
    const local = JSON.parse(readFileSync(privateFile, 'utf8'))
    const settings = local.setting || {}
    const settingsChanged = Object.keys(compileSettings).some(
      (key) => settings[key] !== compileSettings[key],
    )
    // DevTools saves imported names in this override and can URI-encode them.
    const projectAlias = projectName ? encodeURIComponent(projectName) : ''
    const aliasChanged =
      projectAlias &&
      Object.hasOwn(local, 'projectname') &&
      local.projectname !== projectName &&
      local.projectname !== projectAlias
    if (settingsChanged || aliasChanged) {
      if (settingsChanged) local.setting = { ...settings, ...compileSettings }
      if (aliasChanged) local.projectname = projectAlias
      writeFileSync(path.join(staged, privateName), JSON.stringify(local, null, 2) + '\n')
      files.push(privateName)
    }
  }

  // Replace files in place. Neither app.json nor the project directory disappears.
  const last = [
    'app.js',
    path.normalize(entry + '.js'),
    'app.json',
    'project.config.json',
    privateName,
  ]
  const filesInOrder = [
    ...files.filter((file) => !last.includes(file)),
    ...last.filter((file) => files.includes(file)),
  ]
  for (const file of filesInOrder) {
    const from = path.join(staged, file)
    const to = path.join(output, file)
    if (existsSync(to) && readFileSync(from).equals(readFileSync(to))) continue
    mkdirSync(path.dirname(to), { recursive: true })
    renameSync(from, to)
  }

  const expected = new Set(files)
  for (const item of readdirSync(output, { recursive: true, withFileTypes: true })) {
    if (
      !item.isFile() ||
      item.name === privateName ||
      !compiledExtensions.has(path.extname(item.name))
    )
      continue
    const file = path.join(item.parentPath, item.name)
    if (!expected.has(path.relative(output, file))) rmSync(file)
  }
}

try {
  const build = spawnSync(process.execPath, [process.env.npm_execpath, 'run', 'build:mp'], {
    cwd: root,
    stdio: ['inherit', 'pipe', 'inherit'],
    encoding: 'utf8',
    maxBuffer: 8 * 1024 * 1024,
    env: {
      ...process.env,
      UNI_OUTPUT_DIR: staged,
      VITE_WECHAT_PACKAGE: mode,
      VITE_DATA_MODE: mode,
      VITE_API_BASE_URL: base,
    },
  })
  if (build.stdout)
    process.stdout.write(
      build.stdout.replace(
        /^Run method: open Weixin Mini Program Devtools, import[^\r\n]*\r?\n?/gm,
        '',
      ),
    )
  if (build.error) throw build.error
  if (build.status !== 0) throw new Error('微信源码构建失败，原有预览工程保持可用')

  const app = JSON.parse(readFileSync(path.join(staged, 'app.json'), 'utf8'))
  if (Object.hasOwn(app.permission || {}, 'scope.camera')) {
    throw new Error('app.json 的 permission 不接受 scope.camera，相机权限在调用相机时申请')
  }
  const entry = app.pages?.[0]
  if (!entry || !statSync(path.join(staged, entry + '.wxml')).isFile()) {
    throw new Error('微信构建产物缺少入口页面')
  }
  const projectFile = path.join(staged, 'project.config.json')
  const project = JSON.parse(readFileSync(projectFile, 'utf8'))
  if (project.compileType !== 'miniprogram') throw new Error('微信构建产物的项目类型无效')
  project.appid = appid
  project.setting = { ...project.setting, urlCheck: true, ...compileSettings }
  writeFileSync(projectFile, JSON.stringify(project, null, 2) + '\n')

  const compiled = readFileSync(path.join(staged, 'lib/transport.js'), 'utf8')
  if (!compiled.includes('environmentMode:' + JSON.stringify(mode))) {
    throw new Error('小程序产物没有包含预期的数据模式')
  }
  if (base && !compiled.includes('environmentBase:' + JSON.stringify(base))) {
    throw new Error('小程序产物没有包含预期的后端地址')
  }
  const files = []
  let bytes = 0
  for (const file of readdirSync(staged, { recursive: true, withFileTypes: true })) {
    if (file.isDirectory()) continue
    if (
      !file.isFile() ||
      file.name.startsWith('.') ||
      !compiledExtensions.has(path.extname(file.name))
    ) {
      throw new Error('小程序包发现意外文件：' + file.name)
    }
    const filePath = path.join(file.parentPath, file.name)
    if (path.extname(file.name) === '.wxss') checkStylesheet(filePath)
    files.push(path.relative(staged, filePath))
    bytes += statSync(filePath).size
  }
  publish(files, entry, project.projectname)
  console.log('WeChat ' + mode + ' output: ' + output)
  console.log('Compiled files: ' + (bytes / (1024 * 1024)).toFixed(2) + ' MiB')
} finally {
  const stagePath = realpathSync(staged)
  if (path.dirname(stagePath) === parent && path.basename(stagePath).startsWith(prefix)) {
    rmSync(stagePath, { recursive: true, force: true })
  }
}
