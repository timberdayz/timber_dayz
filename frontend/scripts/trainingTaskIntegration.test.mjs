import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const myTasksSource = fs.readFileSync(path.resolve(__dirname, '../src/views/approval/MyTasks.vue'), 'utf8')
const notificationsSource = fs.readFileSync(path.resolve(__dirname, '../src/views/messages/SystemNotifications.vue'), 'utf8')
const taskDetailPath = path.resolve(__dirname, '../src/views/training/TrainingAssignmentDetail.vue')

test('my tasks routes training items to training assignment detail', () => {
  assert.equal(myTasksSource.includes("source_module === 'training'"), true)
  assert.equal(myTasksSource.includes('/training/assignments/'), true)
})

test('system notifications can route using target_route or training notification types', () => {
  assert.equal(notificationsSource.includes('notification.extra_data?.target_route'), true)
  assert.equal(notificationsSource.includes('training_assigned'), true)
})

test('training assignment detail view exists', () => {
  assert.equal(fs.existsSync(taskDetailPath), true)
  const source = fs.readFileSync(taskDetailPath, 'utf8')
  assert.equal(source.includes('培训详情'), true)
})
