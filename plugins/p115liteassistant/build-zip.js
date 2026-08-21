import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import archiver from 'archiver'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// 联邦资源放在带版本号的目录里，浏览器不会再复用上一版的 remoteEntry.js，
// 所以不需要为旧文件名写别名桩文件。换目录名即完成缓存失效。
const assetsDir = path.join(__dirname, 'dist', 'assets-v120')

const requiredAssets = [
  /^remoteEntry\.js$/,
  /^__federation_expose_Config-[a-f0-9]+\.js$/,
  /^__federation_expose_Page-[a-f0-9]+\.js$/,
  /^style-[a-f0-9]+\.css$/,
]

function assertBuildOutput() {
  if (!fs.existsSync(assetsDir)) throw new Error(`Missing build output: ${assetsDir}`)
  const files = fs.readdirSync(assetsDir)
  for (const pattern of requiredAssets) {
    if (!files.some(name => pattern.test(name))) throw new Error(`Missing build asset matching ${pattern}`)
  }
}

assertBuildOutput()

const output = fs.createWriteStream(path.join(__dirname, 'p115liteassistant.zip'))
const archive = archiver('zip', { zlib: { level: 9 } })

archive.pipe(output)
const backendFiles = [
  '__init__.py',
  'api.py',
  'checkin_schedule.py',
  'client.py',
  'file_types.py',
  'log_utils.py',
  'life_monitor.py',
  'records.py',
  'resilience.py',
  'store.py',
  'strm.py',
  'uploader.py',
]

for (const fileName of backendFiles) {
  const filePath = path.join(__dirname, fileName)
  if (!fs.existsSync(filePath)) throw new Error(`Missing backend file: ${fileName}`)
  archive.file(filePath, { name: fileName })
}
archive.file(path.join(__dirname, 'requirements.txt'), { name: 'requirements.txt' })
archive.directory(path.join(__dirname, 'dist'), 'dist')
archive.finalize()
