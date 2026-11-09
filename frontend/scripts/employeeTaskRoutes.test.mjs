import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const routerSource = fs.readFileSync(path.resolve(__dirname, '../src/router/index.js'), 'utf8')
const menuSource = fs.readFileSync(path.resolve(__dirname, '../src/config/menuGroups.js'), 'utf8')

test('router exposes my tasks and task detail routes', () => {
  assert.equal(routerSource.includes("path: '/my-tasks'"), true)
  assert.equal(routerSource.includes("path: '/my-tasks/:taskId'"), true)
  assert.equal(routerSource.includes("name: 'TaskDetail'"), true)
})

test('my tasks route is no longer admin only', () => {
  const myTasksStart = routerSource.indexOf("path: '/my-tasks'")
  // 只截取「我的待办」这一条路由对象，避免把后面 admin 专属的路由也算进来
  const myTasksBlock = routerSource.slice(
    myTasksStart,
    routerSource.indexOf("path: '", myTasksStart + 1)
  )
  assert.equal(myTasksBlock.includes("roles: ['admin']"), false)
  assert.equal(myTasksBlock.includes("'manager'"), true)
  assert.equal(myTasksBlock.includes("'operator'"), true)
  assert.equal(myTasksBlock.includes("'finance'"), true)
})

test('menu still exposes my tasks entry', () => {
  assert.equal(menuSource.includes('/my-tasks'), true)
})
