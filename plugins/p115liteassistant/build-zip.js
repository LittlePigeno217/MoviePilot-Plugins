import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import archiver from 'archiver'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const output = fs.createWriteStream(path.join(__dirname, 'p115liteassistant.zip'))
const archive = archiver('zip', { zlib: { level: 9 } })

archive.pipe(output)
archive.file(path.join(__dirname, '__init__.py'), { name: '__init__.py' })
archive.file(path.join(__dirname, 'requirements.txt'), { name: 'requirements.txt' })
archive.directory(path.join(__dirname, 'dist'), 'dist')
archive.finalize()
