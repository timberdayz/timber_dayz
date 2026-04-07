import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const tasksViewPath = path.resolve(__dirname, '../src/views/collection/CollectionTasks.vue')

const tasksSource = fs.readFileSync(tasksViewPath, 'utf8')

test('CollectionTasks uses faster refresh cadence while active tasks exist', () => {
  assert.equal(
    tasksSource.includes('const ACTIVE_TASK_POLL_INTERVAL = 3000'),
    true,
    'active tasks should refresh on a short cadence instead of waiting for the 30-second idle poll'
  )

  assert.equal(
    tasksSource.includes('const IDLE_TASK_POLL_INTERVAL = 30000'),
    true,
    'idle task list should keep the cheaper 30-second refresh cadence'
  )

  assert.equal(
    tasksSource.includes('scheduleTaskRefresh(tasks.value)'),
    true,
    'task loading should reschedule the next refresh using the current task activity state'
  )
})

test('CollectionTasks reloads the task list after websocket completion messages', () => {
  assert.equal(
    tasksSource.includes('void loadTasks()'),
    true,
    'task completion websocket messages should trigger a full list refresh so the table reflects final state immediately'
  )
})
