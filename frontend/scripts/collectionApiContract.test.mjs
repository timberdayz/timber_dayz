import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  buildTimeSelectionPayload,
  getAvailableDomainOptions,
  resolveAccountIdsForConfigRun,
} from '../src/constants/collection.js'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const apiPath = path.resolve(__dirname, '../src/api/collection.js')
const apiSource = fs.readFileSync(apiPath, 'utf8')
const viewPath = path.resolve(__dirname, '../src/views/collection/CollectionConfig.vue')
const viewSource = fs.readFileSync(viewPath, 'utf8')

test('collection api default export exposes getTaskScreenshotUrl', () => {
  assert.equal(
    apiSource.includes('getTaskScreenshotUrl,'),
    true,
    'default collection api export should expose getTaskScreenshotUrl'
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

test('getAvailableDomainOptions restricts miaoshou to orders only', () => {
  assert.deepEqual(
    getAvailableDomainOptions('miaoshou').map((item) => item.value),
    ['orders']
  )
})

test('CollectionConfig exposes explicit granularity control for custom time selection', () => {
  assert.equal(
    viewSource.includes("v-if=\"form.date_range_type === 'custom'\""),
    true,
    'custom date section should still exist'
  )

  assert.equal(
    viewSource.includes('label="自定义粒度"'),
    true,
    'custom time selection should expose an explicit granularity field'
  )

  assert.equal(
    viewSource.includes('v-for="option in availableDomainOptions"'),
    true,
    'data domain options should come from the platform-aware domain list'
  )
})
