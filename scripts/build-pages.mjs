import { spawnSync } from 'node:child_process'
import { mkdirSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const output = path.join(root, 'apps/client/dist/pages')
if (!process.env.npm_execpath) throw new Error('Run this script with npm run build:pages')
const result = spawnSync(process.execPath, [process.env.npm_execpath, 'run', 'build'], {
  cwd: root, stdio: 'inherit', env: { ...process.env, UNI_H5_BASE: '/AgriVision-system/', UNI_OUTPUT_DIR: output, VITE_DATA_MODE: 'preview' },
})
if (result.status !== 0) process.exit(result.status || 1)
mkdirSync(output, { recursive: true })
writeFileSync(path.join(output, '.nojekyll'), '')
console.log(`Pages output: ${output}`)
