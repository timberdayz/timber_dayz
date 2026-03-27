import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const componentPath = path.resolve(__dirname, '../src/views/ComponentRecorder.vue')
const source = fs.readFileSync(componentPath, 'utf8')

test('ComponentRecorder normalizes axios interceptor responses instead of assuming { success, data } shape', () => {
  assert.equal(
    source.includes('statusResponse.success && statusResponse.data'),
    false,
    'polling logic should not expect api.get() to return { success, data }'
  )

  assert.equal(
    source.includes('if (response.success) {'),
    false,
    'recorder actions should not expect api.post() to always return { success, data }'
  )
})
