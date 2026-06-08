import assert from 'node:assert/strict'
import test from 'node:test'

import {
  getSyncTaskTypeMeta,
  getSyncTriggerMeta,
  resolveSyncTriggerSource
} from '../src/domains/data_platform/utils/syncTaskDisplay.js'

test('maps sync task types to stable labels and tag types', () => {
  assert.deepEqual(getSyncTaskTypeMeta('auto_ingest'), {
    text: '自动入库',
    tagType: 'success'
  })
  assert.deepEqual(getSyncTaskTypeMeta('single_file'), {
    text: '单文件同步',
    tagType: 'info'
  })
  assert.deepEqual(getSyncTaskTypeMeta('bulk_ingest'), {
    text: '批量同步',
    tagType: 'primary'
  })
  assert.deepEqual(getSyncTaskTypeMeta('batch_ingest'), {
    text: '批量同步',
    tagType: 'primary'
  })
  assert.deepEqual(getSyncTaskTypeMeta('batch_sync_all'), {
    text: '全量同步',
    tagType: 'primary'
  })
  assert.deepEqual(getSyncTaskTypeMeta('custom_type'), {
    text: 'custom_type',
    tagType: 'info'
  })
  assert.deepEqual(getSyncTaskTypeMeta(''), {
    text: '-',
    tagType: 'info'
  })
})

test('resolves trigger source for explicit, legacy manual, and auto-ingest task rows', () => {
  assert.equal(
    resolveSyncTriggerSource({
      task_id: 'auto_ingest_20260608120000_abcdef12',
      task_type: 'auto_ingest'
    }),
    'auto_ingest'
  )
  assert.equal(resolveSyncTriggerSource({ task_type: 'single_file' }), 'manual')
  assert.equal(resolveSyncTriggerSource({ task_type: 'bulk_ingest', trigger_source: '' }), 'manual')
  assert.equal(resolveSyncTriggerSource({ task_type: 'single_file', trigger_source: 'sync_now' }), 'sync_now')
})

test('maps trigger sources to stable labels and tag types', () => {
  assert.deepEqual(getSyncTriggerMeta({ task_type: 'auto_ingest' }), {
    source: 'auto_ingest',
    text: '自动',
    tagType: 'success'
  })
  assert.deepEqual(getSyncTriggerMeta({ task_type: 'single_file' }), {
    source: 'manual',
    text: '手动',
    tagType: 'info'
  })
  assert.deepEqual(getSyncTriggerMeta({ trigger_source: 'sync_now' }), {
    source: 'sync_now',
    text: '手动',
    tagType: 'info'
  })
  assert.deepEqual(getSyncTriggerMeta({ trigger_source: 'repair' }), {
    source: 'repair',
    text: '修复',
    tagType: 'warning'
  })
  assert.deepEqual(getSyncTriggerMeta({ trigger_source: 'cloud_sync_admin' }), {
    source: 'cloud_sync_admin',
    text: '管理台',
    tagType: 'primary'
  })
  assert.deepEqual(getSyncTriggerMeta({ trigger_source: 'custom_bot' }), {
    source: 'custom_bot',
    text: 'custom_bot',
    tagType: 'info'
  })
})
