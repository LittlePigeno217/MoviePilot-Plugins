import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import archiver from 'archiver'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const assetsDir = path.join(__dirname, 'dist', 'assets')

const legacyAssets = {
  config: [
    '__federation_expose_Config-97f7421d.js',
    '__federation_expose_Config-7f5b080b.js',
    '__federation_expose_Config-43e986fa.js',
    '__federation_expose_Config-bd0f9778.js',
    '__federation_expose_Config-469a5646.js',
    '__federation_expose_Config-fb65a95a.js',
    '__federation_expose_Config-ebda5443.js',
  ],
  page: [
    '__federation_expose_Page-977537ad.js',
    '__federation_expose_Page-8cb7e1c8.js',
    '__federation_expose_Page-e25a15b8.js',
    '__federation_expose_Page-841bcd09.js',
  ],
  helper: [
    '_plugin-vue_export-helper-12555fbe.js',
    '_plugin-vue_export-helper-c5cccadb.js',
    '_plugin-vue_export-helper-acbf976c.js',
    '_plugin-vue_export-helper-bb1fda24.js',
  ],
  index: [
    'index-1be59a16.js',
    'index-95a7d879.js',
    'index-293984c5.js',
    'index-c4f2d89c.js',
    'index-30508e71.js',
    'index-2bf71762.js',
    'index-02f8fa5f.js',
  ],
  style: [
    'style-1375dbe0.css',
    'style-c28fa672.css',
    'style-faffdeb7.css',
    'style-63f370f1.css',
    'style-6b3f9aca.css',
    'style-8bf1f287.css',
    'style-5535bc3a.css',
  ],
}

function createLegacyAssetAliases() {
  const files = fs.readdirSync(assetsDir)
  const legacyNames = new Set(Object.values(legacyAssets).flat())
  const current = {
    config: files.find(name => !legacyNames.has(name) && /^__federation_expose_Config-[a-f0-9]+\.js$/.test(name)),
    page: files.find(name => !legacyNames.has(name) && /^__federation_expose_Page-[a-f0-9]+\.js$/.test(name)),
    helper: files.find(name => !legacyNames.has(name) && /^_plugin-vue_export-helper-[a-f0-9]+\.js$/.test(name)),
    index: files.find(name => !legacyNames.has(name) && /^index-[a-f0-9]+\.js$/.test(name)),
    style: files.find(name => !legacyNames.has(name) && /^style-[a-f0-9]+\.css$/.test(name)),
  }

  for (const [kind, aliases] of Object.entries(legacyAssets)) {
    const target = current[kind]
    if (!target) throw new Error(`Missing current ${kind} asset`)
    for (const alias of aliases) {
      if (alias === target) continue
      const content = kind === 'style'
        ? `@import url("./${target}");\n`
        : kind === 'config' || kind === 'page'
          ? `export { default } from "./${target}";\nexport * from "./${target}";\n`
          : `export * from "./${target}";\n`
      fs.writeFileSync(path.join(assetsDir, alias), content)
    }
  }
}

createLegacyAssetAliases()

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
