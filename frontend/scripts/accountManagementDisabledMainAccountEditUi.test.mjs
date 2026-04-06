import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const storePath = path.resolve(__dirname, '../src/stores/accounts.js')
const viewPath = path.resolve(__dirname, '../src/views/AccountManagement.vue')
const storeSource = fs.readFileSync(storePath, 'utf8')
const viewSource = fs.readFileSync(viewPath, 'utf8')

test('account management keeps disabled main-account metadata available for shop editing', () => {
  assert.equal(
    /this\.mainAccounts\s*=\s*\(mainAccounts\s*\|\|\s*\[\]\)\.filter\(\(item\)\s*=>[\s\S]*item\.enabled[\s\S]*\)/m.test(
      storeSource
    ),
    false,
    'accounts store should not drop disabled main-account metadata needed by edit dialogs'
  )
})

test('shop edit dialog still requires username validation sourced from main-account metadata', () => {
  assert.equal(
    viewSource.includes("username: [{ required: true, message: '请输入用户名', trigger: 'blur' }]"),
    true,
    'account management should keep username required during shop editing'
  )
})
