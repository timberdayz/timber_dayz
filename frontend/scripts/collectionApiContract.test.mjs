import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const apiPath = path.resolve(__dirname, '../src/api/collection.js')
const source = fs.readFileSync(apiPath, 'utf8')

test('collection api default export exposes getTaskScreenshotUrl', () => {
  assert.equal(
    source.includes('getTaskScreenshotUrl,'),
    true,
    'default collection api export should expose getTaskScreenshotUrl'
  )
})
