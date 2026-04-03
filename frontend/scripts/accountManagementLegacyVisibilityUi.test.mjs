import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const viewPath = path.resolve(__dirname, '../src/views/AccountManagement.vue')
const storePath = path.resolve(__dirname, '../src/stores/accounts.js')
const viewSource = fs.readFileSync(viewPath, 'utf8')
const storeSource = fs.readFileSync(storePath, 'utf8')

test('account management exposes legacy visibility switch', () => {
  assert.equal(
    viewSource.includes('显示历史记录'),
    true,
    'account management should expose a toggle for historical disabled records'
  )
})

test('accounts store defaults account loading to enabled=true unless history is requested', () => {
  assert.equal(
    storeSource.includes('const defaultEnabled = mergedParams.include_disabled ? mergedParams.enabled : true'),
    true,
    'accounts store should default to enabled=true when history is hidden'
  )
})
