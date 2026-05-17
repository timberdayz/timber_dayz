import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const viewPath = path.resolve(__dirname, '../src/domains/collection/views/collection/CollectionTasks.vue')
const source = fs.readFileSync(viewPath, 'utf8')

test('CollectionTasks task detail exposes session quality metadata', () => {
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
      true,
      `task detail should expose ${field}`
    )
  }
})
