import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const viewPath = path.resolve(__dirname, '../src/domains/collection/views/collection/CollectionTasks.vue')
const source = fs.readFileSync(viewPath, 'utf8')

const extractArrowFunctionBody = (name) => {
  const matched = source.match(new RegExp(`const ${name} = \\([^)]*\\) => \\{([\\s\\S]*?)\\n\\}`))
  assert.ok(matched, `${name} should exist in ${viewPath}`)
  return matched[1]
}

test('CollectionTasks task detail exposes profile session diagnostics', () => {
  for (const field of [
    'session_profile_path',
    'session_reused',
    'session_proxy',
    'session_source',
    'getSessionSourceLabel'
  ]) {
    assert.equal(
      source.includes(field),
      true,
      `task detail should expose ${field}`
    )
  }
})

test('CollectionTasks task detail drops legacy session quality fields', () => {
  for (const field of [
    'session_quality_score',
    'session_quality_gate_passed',
    'session_quality_source',
    'session_manual_seeded',
    'session_protected',
    'getSessionQualitySourceLabel'
  ]) {
    assert.equal(
      source.includes(field),
      false,
      `task detail should no longer expose ${field}`
    )
  }
})

test('CollectionTasks task detail drops legacy profile field names', () => {
  for (const field of [
    'persistent_profile_path',
    'profile_contains_state'
  ]) {
    assert.equal(
      source.includes(field),
      false,
      `task detail should no longer expose ${field}`
    )
  }
})

test('getSessionSourceLabel maps the single profile source and keeps a fallback', () => {
  const body = extractArrowFunctionBody('getSessionSourceLabel')

  assert.equal(body.includes("profile: '持久化浏览器档案'"), true)
  assert.equal(body.includes('labels[source] || source'), true)

  for (const legacyKey of ['storage_state', 'persistent_profile', 'fresh_login']) {
    assert.equal(
      body.includes(legacyKey),
      false,
      `getSessionSourceLabel should no longer map ${legacyKey}`
    )
  }
})

test('getRuntimeStrategyReasonLabel drops removed session-file strategies', () => {
  const body = extractArrowFunctionBody('getRuntimeStrategyReasonLabel')

  assert.equal(body.includes('profile_is_single_source_of_truth'), true)
  assert.equal(body.includes('persistent_profile_available'), true)

  for (const removedReason of [
    'manual_storage_state_available',
    'storage_state_available',
    'storage_state_missing',
    'storage_state_fanout'
  ]) {
    assert.equal(
      body.includes(removedReason),
      false,
      `getRuntimeStrategyReasonLabel should no longer map ${removedReason}`
    )
  }
})
