/**
 * 人力管理页（父容器）加载链路守护。
 *
 * 【守护的是哪一次事故】
 * ----------------------
 * 2026-11-20 的重构（``dd04894e``）把「员工管理」从父容器
 * ``frontend/src/domains/business/views/HumanResources.vue`` 拆成独立子组件
 * ``frontend/src/domains/business/views/hr/EmployeeTab.vue``：
 * ``loadEmployees`` 随之搬到子组件，父容器的 ``loadInitialData`` 里
 * **却漏删了那一行调用** ⇒ 运行时 ``ReferenceError: loadEmployees is not defined``
 * ⇒ 被 catch 捕获 ⇒ 页面顶部弹「加载数据失败，请刷新重试」。
 *
 * 这个假警报最坏的地方在于：数据其实全部加载成功（子组件自己加载），
 * 所以任何人看截图都会以为"员工数据没加载出来"。
 *
 * 【为什么它能进生产】
 * --------------------
 * Vue SFC 的 ESLint 默认关闭 ``no-undef``，前端守护又是 ``node --test``
 * （不挂载组件运行时）⇒ 构建期与测试期都抓不到"调用了不存在的函数"。
 *
 * 【本守护的作用】
 * ----------------
 * 1. 父容器**不得**出现 ``loadEmployees``（员工列表归子组件自持）；
 * 2. 父容器不得残留重构遗留的死函数；
 * 3. 父容器仍必须加载部门 / 职位 / 员工姓名（考勤与工资单要用）；
 * 4. 子组件仍必须自己定义并加载员工列表（防止"修一处、坏一处"）。
 *
 * 通用防线（任何页面调用了不存在的函数都会红）在 CI 里：
 * ``.github/workflows/ci.yml`` 的 ``frontend-guard`` job 跑
 * ``eslint --rule '{"no-undef":"error"}'``。
 */

import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const viewSource = readFileSync(
  path.resolve(__dirname, '../src/domains/business/views/HumanResources.vue'),
  'utf8'
)
const employeeTabSource = readFileSync(
  path.resolve(__dirname, '../src/domains/business/views/hr/EmployeeTab.vue'),
  'utf8'
)

test('父容器不得调用 loadEmployees：员工列表归员工管理子组件自持', () => {
  assert.equal(
    viewSource.includes('loadEmployees'),
    false,
    'HumanResources.vue 调用了 loadEmployees，但该函数只存在于 EmployeeTab.vue；' +
      '运行时会抛 ReferenceError 并弹出误导性的「加载数据失败」提示'
  )
})

test('父容器不残留重构遗留的死函数', () => {
  for (const deadName of [
    'showPayrollDialog',
    'confirmPayroll',
    'reopenPayroll',
    'markPayrollPaid'
  ]) {
    assert.equal(
      viewSource.includes(deadName),
      false,
      `${deadName} 已是重构遗留的死代码（模板无引用），应删除`
    )
  }
})

test('父容器仍加载部门、职位与员工姓名（考勤与工资单标签页依赖）', () => {
  for (const loader of ['loadDepartments()', 'loadPositions()', 'loadEmployeeNames()']) {
    assert.equal(
      viewSource.includes(loader),
      true,
      `父容器的 loadInitialData 仍应调用 ${loader}`
    )
  }
})

test('员工管理子组件仍自己定义并加载员工列表', () => {
  assert.equal(
    employeeTabSource.includes('const loadEmployees = async'),
    true,
    'EmployeeTab.vue 必须自己定义 loadEmployees（员工列表由子组件自持）'
  )
  assert.equal(
    employeeTabSource.includes('loadEmployees()'),
    true,
    'EmployeeTab.vue 必须仍然加载员工列表'
  )
})
