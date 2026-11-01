import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const repoRoot = resolve(import.meta.dirname, '..')
const viewSource = readFileSync(
  resolve(repoRoot, 'src/domains/collection/views/collection/CollectionTasks.vue'),
  'utf8'
)

const loadTasksBody = (() => {
  const start = viewSource.indexOf('const loadTasks = async () => {')
  assert.notEqual(start, -1)
  const end = viewSource.indexOf('\nconst ', start + 10)
  return viewSource.slice(start, end === -1 ? undefined : end)
})()

test('interrupted 是终态，不会再自己往下走', () => {
  assert.match(viewSource, /TERMINAL_STATUSES = \[[^\]]*'interrupted'/)
})

test('interrupted 有中文标签和标签色', () => {
  assert.match(viewSource, /interrupted: '已中断'/)
  assert.match(viewSource, /interrupted: 'warning'/)
})

test('任务列表加载失败才报「加载任务失败」', () => {
  assert.match(loadTasksBody, /ElMessage\.error\('加载任务失败: '/)
})

test('待确认项加载失败单独提示，不再冒充「加载任务失败」', () => {
  assert.match(loadTasksBody, /ElMessage\.warning\('加载待确认项失败: '/)
  const errorCalls = loadTasksBody.match(/ElMessage\.error\(/g) || []
  assert.equal(errorCalls.length, 1)
})

test('loadTasks 里三段数据各自兜底，互不连坐', () => {
  const catchCount = (loadTasksBody.match(/catch \(error\)/g) || []).length
  assert.equal(catchCount, 3)
})

test('聚焦任务失败只写日志，不弹错误框', () => {
  assert.match(loadTasksBody, /console\.warn\('\[采集任务\] 聚焦任务失败:'/)
})
