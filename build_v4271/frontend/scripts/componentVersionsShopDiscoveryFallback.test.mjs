import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const viewPath = path.resolve(__dirname, '../src/views/ComponentVersions.vue')
const source = fs.readFileSync(viewPath, 'utf8')

test('component versions offers account-management discovery fallback when no shop accounts exist', () => {
  assert.equal(
    source.includes('去账号管理探测店铺'),
    true,
    'component versions should render a discovery fallback CTA'
  )

  assert.equal(
    source.includes('openAccountManagementForDiscovery'),
    true,
    'component versions should wire the discovery fallback action'
  )
})
