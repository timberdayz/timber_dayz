import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const businessViewsDir = path.resolve(__dirname, '../src/domains/business/views')

function collectVueFiles(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true })
  return entries.flatMap((entry) => {
    const fullPath = path.join(dir, entry.name)
    if (entry.isDirectory()) return collectVueFiles(fullPath)
    return entry.isFile() && fullPath.endsWith('.vue') ? [fullPath] : []
  })
}

test('business views do not directly depend on accounts or collection apis', () => {
  const files = collectVueFiles(businessViewsDir)
  const offenders = files.filter((file) => {
    if (file.endsWith(`${path.sep}AccountAlignment.vue`)) return false
    const text = fs.readFileSync(file, 'utf8')
    return text.includes("@/api/accounts") || text.includes("@/api/collection")
  })

  assert.deepEqual(offenders, [])
})
