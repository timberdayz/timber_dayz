import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  buildDynamicTimeWindowPreview,
  buildTimeSelectionPayload,
  getAvailableDomainOptions,
  resolveAccountIdsForConfigRun,
} from '../src/constants/collection.js'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const apiPath = path.resolve(__dirname, '../src/api/collection.js')
const apiSource = fs.readFileSync(apiPath, 'utf8')
const viewPath = path.resolve(__dirname, '../src/domains/collection/views/collection/CollectionConfig.vue')
const viewSource = fs.readFileSync(viewPath, 'utf8')
const tasksViewPath = path.resolve(__dirname, '../src/domains/collection/views/collection/CollectionTasks.vue')
const tasksViewSource = fs.readFileSync(tasksViewPath, 'utf8')

test('collection api default export exposes getTaskScreenshotUrl', () => {
  assert.equal(
    apiSource.includes('getTaskScreenshotUrl,'),
    true,
    'default collection api export should expose getTaskScreenshotUrl'
  )
})

test('collection api default export exposes getVerificationItems', () => {
  assert.equal(
    apiSource.includes('getVerificationItems,'),
    true,
    'default collection api export should expose getVerificationItems'
  )
})

test('buildTimeSelectionPayload emits preset runtime contract', () => {
  assert.deepEqual(
    buildTimeSelectionPayload('last_7_days'),
    {
      mode: 'preset',
      preset: 'last_7_days',
    }
  )
})

test('buildTimeSelectionPayload emits custom runtime contract', () => {
  assert.deepEqual(
    buildTimeSelectionPayload('custom', {
      customRange: ['2026-03-01', '2026-03-31'],
    }),
    {
      mode: 'custom',
      start_date: '2026-03-01',
      end_date: '2026-03-31',
      start_time: '00:00:00',
      end_time: '23:59:59',
    }
  )
})

test('buildTimeSelectionPayload accepts compact dynamic date range codes', () => {
  assert.deepEqual(
    buildTimeSelectionPayload('auto_month_to_date'),
    {
      mode: 'dynamic',
      strategy: 'current_month_to_available_day',
      available_after_time: '06:00',
    }
  )
})

test('buildDynamicTimeWindowPreview uses Asia Hong Kong 06:00 cutoff', () => {
  assert.deepEqual(
    buildDynamicTimeWindowPreview(
      'auto_month_to_date',
      new Date('2026-07-04T21:59:00.000Z')
    ),
    {
      start_date: '2026-07-01',
      end_date: '2026-07-03',
      available_after_time: '06:00',
      time_window_label: '本月累计到最近可采集日',
    }
  )

  assert.deepEqual(
    buildDynamicTimeWindowPreview(
      'auto_month_to_date',
      new Date('2026-07-04T22:00:00.000Z')
    ),
    {
      start_date: '2026-07-01',
      end_date: '2026-07-04',
      available_after_time: '06:00',
      time_window_label: '本月累计到最近可采集日',
    }
  )
})

test('resolveAccountIdsForConfigRun falls back to active platform accounts only', () => {
  const accounts = [
    { id: 'a-1', platform: 'miaoshou', status: 'active' },
    { id: 'a-2', platform: 'miaoshou', status: 'inactive' },
    { id: 'a-3', platform: 'shopee', status: 'active' },
  ]

  assert.deepEqual(
    resolveAccountIdsForConfigRun(
      {
        platform: 'miaoshou',
        account_ids: [],
      },
      accounts
    ),
    ['a-1']
  )
})

test('resolveAccountIdsForConfigRun preserves explicit account ids', () => {
  assert.deepEqual(
    resolveAccountIdsForConfigRun(
      {
        platform: 'miaoshou',
        account_ids: ['fixed-1', 'fixed-2'],
      },
      []
    ),
    ['fixed-1', 'fixed-2']
  )
})

test('getAvailableDomainOptions keeps full domain list for miaoshou config setup', () => {
  assert.deepEqual(
    getAvailableDomainOptions('miaoshou').map((item) => item.value),
    ['orders', 'products', 'analytics', 'finance', 'services', 'inventory']
  )
})

test('CollectionConfig exposes explicit granularity control for custom time selection', () => {
  assert.equal(
    viewSource.includes("v-if=\"form.date_range_type === 'custom'\""),
    true,
    'custom date section should still exist'
  )

  assert.equal(
    viewSource.includes('v-model="activeGranularity"'),
    true,
    'config page should expose explicit granularity controls via activeGranularity'
  )

  assert.equal(
    viewSource.includes('v-for="option in availableDomainOptions"'),
    true,
    'data domain options should come from the platform-aware domain list'
  )

  assert.equal(
    viewSource.includes('label="执行模式"'),
    true,
    'config page should expose execution mode selection'
  )

  assert.equal(
    viewSource.includes('<el-table-column label="执行模式"'),
    true,
    'config list should display execution mode'
  )
})

test('CollectionConfig hands execution off to CollectionTasks after creating tasks', () => {
  assert.equal(
    viewSource.includes('runConfig(row)'),
    true,
    'config list should expose config-level execution entry points'
  )

  assert.equal(
    viewSource.includes('collectionApi.runConfig(row.id,'),
    true,
    'config page should invoke the config-run endpoint directly'
  )

  assert.equal(
    tasksViewSource.includes('useRoute'),
    true,
    'task page should still support route query filters for config handoff flows'
  )

  assert.equal(
    tasksViewSource.includes('task_ids'),
    true,
    'task page should consume task_ids from route query'
  )

  assert.equal(
    tasksViewSource.includes('config_id'),
    true,
    'task page should consume config_id from route query'
  )
})
