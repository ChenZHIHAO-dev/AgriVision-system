import { test } from 'node:test'
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import {
  copyFileSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  realpathSync,
  rmSync,
  writeFileSync,
} from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const oldApp = JSON.stringify({
  pages: ['pages/index/index'],
  window: { navigationBarTitleText: '旧预览' },
})
const oldPage = '<view>仍可编译的旧预览页面</view>'
const privateConfig = {
  projectname: encodeURIComponent('旧预览'),
  libVersion: '3.17.6',
  setting: { compileHotReLoad: true, ignoreDevUnusedFiles: true, useApiHook: false },
}

const fakeCompiler = String.raw`
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const root = process.cwd()
const preview = path.join(root, 'apps/client/dist/wechat/preview')
const stage = path.resolve(process.env.UNI_OUTPUT_DIR)
const oldApp = process.env.AV_TEST_OLD_APP
const failure = process.env.AV_TEST_FAILURE
const installedApp = () => fs.readFileSync(path.join(preview, 'app.json'), 'utf8')

assert.notEqual(stage, preview, '小程序编译应写入隔离目录')
assert.equal(path.dirname(stage), path.dirname(preview), '预览与暂存应位于同一个父目录')
assert.equal(installedApp(), oldApp, '编译开始时，已导入的 app.json 应仍可读取')
fs.mkdirSync(path.join(stage, 'pages/index'), { recursive: true })
fs.mkdirSync(path.join(stage, 'lib'), { recursive: true })
fs.writeFileSync(
  path.join(stage, 'app.json'),
  JSON.stringify({ pages: ['pages/index/index'], window: { navigationBarTitleText: '新预览' } }),
)
fs.writeFileSync(path.join(stage, 'pages/index/index.wxml'), '<view>新预览页面</view>')
fs.writeFileSync(path.join(stage, 'project.config.json'), '{"compileType":"miniprogram","projectname":"宛田观叶","setting":{}}')
fs.writeFileSync(path.join(stage, 'lib/transport.js'), '({environmentMode:"preview"})')
fs.writeFileSync(path.join(stage, 'app.wxss'), failure === 'validation' ? '*{display:none}' : '.ok{color:green}')
assert.equal(installedApp(), oldApp, '编译输出产生后，旧包仍应在原目录完整可读')
if (failure === 'compiler') {
  console.error('test compiler stopped after writing output')
  process.exitCode = 7
}
`

function fixture(t, localConfig = privateConfig) {
  const temp = realpathSync(tmpdir())
  const prefix = 'agrivision-wechat-test-'
  const root = mkdtempSync(path.join(temp, prefix))
  t.after(() => {
    const resolved = realpathSync(root)
    assert.equal(path.dirname(resolved), temp)
    assert.ok(path.basename(resolved).startsWith(prefix))
    rmSync(resolved, { recursive: true, force: true })
  })

  const script = path.join(root, 'scripts/build-wechat.mjs')
  const compiler = path.join(root, 'fake-npm.cjs')
  const preview = path.join(root, 'apps/client/dist/wechat/preview')
  const files = {
    'app.json': oldApp,
    'pages/index/index.wxml': oldPage,
    'project.config.json': '{"compileType":"miniprogram","projectname":"旧预览"}',
    'project.private.config.json': JSON.stringify(localConfig),
  }
  mkdirSync(path.dirname(script), { recursive: true })
  copyFileSync(new URL('../../scripts/build-wechat.mjs', import.meta.url), script)
  writeFileSync(compiler, fakeCompiler)
  for (const [relative, contents] of Object.entries(files)) {
    const file = path.join(preview, relative)
    mkdirSync(path.dirname(file), { recursive: true })
    writeFileSync(file, contents)
  }

  return {
    files,
    preview,
    run(failure = '') {
      return spawnSync(process.execPath, [script], {
        cwd: root,
        env: {
          ...(process.env.SystemRoot ? { SystemRoot: process.env.SystemRoot } : {}),
          npm_execpath: compiler,
          AGRIVISION_WECHAT_APP_ID: 'touristappid',
          AV_TEST_OLD_APP: oldApp,
          AV_TEST_FAILURE: failure,
        },
        encoding: 'utf8',
        timeout: 15_000,
      })
    },
  }
}

test('WeChat rebuild keeps the imported package readable while compiling', (t) => {
  const { preview, run } = fixture(t)
  const build = run()
  assert.equal(build.error, undefined)
  assert.equal(build.status, 0, build.stderr)
  const readJson = (name) => JSON.parse(readFileSync(path.join(preview, name), 'utf8'))
  assert.equal(readJson('app.json').window.navigationBarTitleText, '新预览')
  assert.equal(readJson('project.config.json').projectname, '宛田观叶')
  assert.equal(readJson('project.config.json').appid, 'touristappid')
  assert.match(readFileSync(path.join(preview, 'pages/index/index.wxml'), 'utf8'), /新预览页面/)
  assert.deepEqual(readJson('project.private.config.json'), {
    ...privateConfig,
    projectname: encodeURIComponent('宛田观叶'),
    setting: {
      ...privateConfig.setting,
      compileHotReLoad: false,
      ignoreDevUnusedFiles: false,
    },
  })
  assert.deepEqual(readdirSync(path.dirname(preview)), ['preview'])
})

test('WeChat rebuild updates an old imported alias with current compiler settings', (t) => {
  const local = {
    ...privateConfig,
    appid: 'test-only-old-app-id',
    setting: {
      ...privateConfig.setting,
      compileHotReLoad: false,
      ignoreDevUnusedFiles: false,
    },
  }
  const { preview, run } = fixture(t, local)
  const build = run()
  assert.equal(build.status, 0, build.stderr)
  const installed = JSON.parse(
    readFileSync(path.join(preview, 'project.private.config.json'), 'utf8'),
  )
  assert.deepEqual(installed, { ...local, projectname: encodeURIComponent('宛田观叶') })
})

test('failed WeChat compilation or validation leaves the imported package intact', (t) => {
  const { files, preview, run } = fixture(t)
  for (const [failure, reason] of [
    ['compiler', /test compiler stopped after writing output/],
    ['validation', /WXSS 不支持的通配选择器/],
  ]) {
    const build = run(failure)
    assert.equal(build.error, undefined)
    assert.notEqual(build.status, 0, build.stderr)
    assert.match(build.stderr, reason)
    for (const [file, oldContents] of Object.entries(files))
      assert.equal(readFileSync(path.join(preview, file), 'utf8'), oldContents, file)
    const installed = readdirSync(preview, { recursive: true, withFileTypes: true })
      .filter((file) => file.isFile())
      .map((file) =>
        path.relative(preview, path.join(file.parentPath, file.name)).split(path.sep).join('/'),
      )
      .sort()
    assert.deepEqual(installed, Object.keys(files).sort())
    assert.deepEqual(readdirSync(path.dirname(preview)), ['preview'])
  }
})

test('tracked public files contain no concrete app identifiers or provider credentials', () => {
  // 只检查 Git 管理的文件；本机 .env、构建产物和 secrets 不应进入仓库。
  // 错误仅打印文件位置和类型，避免把可疑内容再次泄漏到终端或 CI 日志。
  const tracked = spawnSync('git', ['ls-files', '-z'], {
    cwd: new URL('../../', import.meta.url),
    encoding: 'utf8',
  })
  assert.equal(tracked.status, 0, tracked.stderr)
  const names = tracked.stdout.split('\0').filter(Boolean)
  const textExtensions = new Set([
    '.js',
    '.mjs',
    '.cjs',
    '.ts',
    '.vue',
    '.json',
    '.py',
    '.md',
    '.yml',
    '.yaml',
    '.ps1',
    '.example',
    '.toml',
    '.txt',
  ])
  const forbidden = [
    ['concrete WeChat AppID', /wx[0-9a-fA-F]{16}/],
    ['provider credential', /\b(?:sk-[A-Za-z0-9_-]{16,}|AKIA[A-Z0-9]{16}|LTAI[A-Za-z0-9]{16,})\b/],
    ['private key', /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/],
  ]
  for (const name of names) {
    assert.ok(
      !/(^|\/)(secrets|runtime|node_modules|dist)(\/|$)/.test(name),
      name + ': private/generated directory is tracked',
    )
    const basename = path.basename(name)
    assert.ok(
      !basename.startsWith('.env') || basename.endsWith('.example'),
      name + ': local environment is tracked',
    )
    if (!textExtensions.has(path.extname(name))) continue
    const contents = readFileSync(new URL('../../' + name, import.meta.url), 'utf8')
    for (const [kind, pattern] of forbidden)
      assert.ok(!pattern.test(contents), name + ': contains ' + kind)
  }
})
