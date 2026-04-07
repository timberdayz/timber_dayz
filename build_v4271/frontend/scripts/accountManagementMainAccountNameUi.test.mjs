import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const viewPath = path.resolve(__dirname, '../src/views/AccountManagement.vue')
const source = fs.readFileSync(viewPath, 'utf8')

test('account management distinguishes main account name, id, and login username', () => {
  assert.equal(
    source.includes('主账号名称'),
    true,
    'account management should expose a main account name field'
  )

  assert.equal(
    source.includes('登录用户名'),
    true,
    'account management should label the login username explicitly'
  )
})
