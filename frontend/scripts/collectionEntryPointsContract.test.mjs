import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const constantsPath = path.resolve(__dirname, '../src/constants/collection.js')
const configViewPath = path.resolve(__dirname, '../src/views/collection/CollectionConfig.vue')
const tasksViewPath = path.resolve(__dirname, '../src/views/collection/CollectionTasks.vue')
const routerPath = path.resolve(__dirname, '../src/router/index.js')
const rootTasksViewPath = path.resolve(__dirname, '../src/views/CollectionTasks.vue')

const constantsSource = fs.readFileSync(constantsPath, 'utf8')
const configSource = fs.readFileSync(configViewPath, 'utf8')
const tasksSource = fs.readFileSync(tasksViewPath, 'utf8')
const routerSource = fs.readFileSync(routerPath, 'utf8')
const rootTasksSource = fs.readFileSync(rootTasksViewPath, 'utf8')

test('collection constants expose orders sub-domain options', () => {
  assert.equal(
    constantsSource.includes('orders: ['),
    true,
    'orders should be modeled as a subtype-aware domain'
  )

  assert.equal(
    constantsSource.includes("value: 'shopee'"),
    true,
    'orders subtype options should include shopee'
  )

  assert.equal(
    constantsSource.includes("value: 'tiktok'"),
    true,
    'orders subtype options should include tiktok'
  )
})

test('CollectionTasks sends unified time_selection payload for quick tasks', () => {
  assert.equal(
    tasksSource.includes('time_selection: buildTimeSelectionPayload('),
    true,
    'quick task creation should send unified time_selection to the backend'
  )

  assert.equal(
    tasksSource.includes("granularity: 'daily'"),
    false,
    'quick task creation should not hardcode daily granularity'
  )
})

test('CollectionConfig resolves effective account ids before creating tasks', () => {
  assert.equal(
    configSource.includes('resolveAccountIdsForConfigRun(row, accounts.value)'),
    true,
    'config execution should resolve effective account ids instead of blindly looping row.account_ids'
  )

  assert.equal(
    configSource.includes('row.account_ids.length'),
    false,
    'config execution should not derive created task count from row.account_ids.length directly'
  )
})

test('router uses collection subdirectory views as canonical collection entry points', () => {
  assert.equal(
    routerSource.includes("../views/collection/CollectionTasks.vue"),
    true,
    'router should use collection/CollectionTasks.vue as the canonical task entry point'
  )

  assert.equal(
    routerSource.includes("../views/collection/CollectionConfig.vue"),
    true,
    'router should use collection/CollectionConfig.vue as the canonical config entry point'
  )

  assert.equal(
    routerSource.includes("../views/collection/CollectionHistory.vue"),
    true,
    'router should use collection/CollectionHistory.vue as the canonical history entry point'
  )
})

test('legacy root CollectionTasks view is no longer the default collection entry point', () => {
  assert.equal(
    rootTasksSource.includes('VerificationResumeDialog'),
    true,
    'legacy root task page may remain as reference but should not be the canonical router target'
  )
})
