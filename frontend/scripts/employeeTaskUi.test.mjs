import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const myTasksSource = fs.readFileSync(path.resolve(__dirname, '../src/domains/platform/views/approval/MyTasks.vue'), 'utf8')
const taskDetailSource = fs.readFileSync(path.resolve(__dirname, '../src/domains/platform/views/approval/TaskDetail.vue'), 'utf8')

test('my tasks page contains summary, tabs, and filters', () => {
  for (const label of ['我的任务', '我发起的', '抄送我的', '按状态筛选', '按优先级筛选']) {
    assert.equal(myTasksSource.includes(label), true, `MyTasks.vue should contain ${label}`)
  }
})

test('task detail page contains timeline and action sections', () => {
  for (const label of ['任务详情', '处理时间线', '处理动作', '关联对象']) {
    assert.equal(taskDetailSource.includes(label), true, `TaskDetail.vue should contain ${label}`)
  }
})

test('task detail page contains phase2 action regions', () => {
  for (const label of ['协作补充', '发起人操作', '管理员操作']) {
    assert.equal(taskDetailSource.includes(label), true, `TaskDetail.vue should contain ${label}`)
  }
})
