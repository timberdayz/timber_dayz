import test from 'node:test'
import assert from 'node:assert/strict'

import { resolveManualChunk } from '../manualChunks.js'

test('resolveManualChunk keeps vue ecosystem internals out of a separate vendor-vue-core chunk', () => {
  assert.equal(
    resolveManualChunk('/repo/frontend/node_modules/@vue/runtime-core/dist/runtime-core.esm-bundler.js'),
    'vendor-misc'
  )
  assert.equal(
    resolveManualChunk('/repo/frontend/node_modules/@vue/shared/dist/shared.esm-bundler.js'),
    'vendor-misc'
  )
  assert.equal(
    resolveManualChunk('/repo/frontend/node_modules/vue-router/dist/vue-router.mjs'),
    'vendor-misc'
  )
  assert.equal(
    resolveManualChunk('/repo/frontend/node_modules/pinia/dist/pinia.mjs'),
    'vendor-misc'
  )
})

test('resolveManualChunk keeps non-vue libraries out of vendor-vue-core', () => {
  assert.equal(
    resolveManualChunk('/repo/frontend/node_modules/axios/index.js'),
    'vendor-misc'
  )
  assert.equal(
    resolveManualChunk('/repo/frontend/src/views/BusinessOverview.vue'),
    undefined
  )
})

test('resolveManualChunk keeps all Element Plus internals in one vendor chunk', () => {
  assert.equal(
    resolveManualChunk('/repo/frontend/node_modules/element-plus/es/components/message/index.mjs'),
    'vendor-element-plus'
  )
  assert.equal(
    resolveManualChunk('/repo/frontend/node_modules/element-plus/es/components/form/src/form.mjs'),
    'vendor-element-plus'
  )
  assert.equal(
    resolveManualChunk('/repo/frontend/node_modules/element-plus/es/components/date-picker/src/date-picker.mjs'),
    'vendor-element-plus'
  )
  assert.equal(
    resolveManualChunk('/repo/frontend/node_modules/@element-plus/icons-vue/dist/index.mjs'),
    'vendor-element-plus'
  )
})
