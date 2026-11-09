import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import {
  extractBatchConfirmIssues,
  extractBatchConfirmSuccessCount,
  formatBatchConfirmIssue,
  formatBatchConfirmIssueHtml,
  formatBatchConfirmIssueLines
} from '../src/domains/business/views/hr/payrollBatchConfirm.js'

const repoRoot = resolve(import.meta.dirname, '..')
const apiSource = readFileSync(resolve(repoRoot, 'src/api/index.js'), 'utf8')
const salarySource = readFileSync(
  resolve(repoRoot, 'src/domains/business/views/hr/EmployeeSalary.vue'),
  'utf8'
)

const BACKEND_ISSUES = [
  { employee_code: 'EMP260002', record_id: 12, reason: '请先刷新当月工资和人力成本分摊，再确认工资单' },
  { employee_code: 'EMP260003', record_id: 13, reason: '该员工本月没有待确认的草稿工资单' }
]

test('批量确认失败时能从错误里取出 issues 清单', () => {
  // api 拦截器包装过的错误
  const apiError = { data: { issues: BACKEND_ISSUES } }
  const issues = extractBatchConfirmIssues(apiError)
  assert.equal(issues.length, 2)
  assert.equal(issues[0].employee_code, 'EMP260002')
  assert.equal(issues[0].record_id, 12)
  assert.equal(issues[0].reason, '请先刷新当月工资和人力成本分摊，再确认工资单')
})

test('批量确认失败时也能从原始响应里取出 issues 清单', () => {
  const axiosError = { response: { data: { success: false, data: { issues: BACKEND_ISSUES } } } }
  assert.equal(extractBatchConfirmIssues(axiosError).length, 2)
})

test('没有 issues 时返回空清单，不抛异常', () => {
  assert.deepEqual(extractBatchConfirmIssues(null), [])
  assert.deepEqual(extractBatchConfirmIssues({}), [])
  assert.deepEqual(extractBatchConfirmIssues({ data: { issues: [] } }), [])
})

test('issues 逐条文案说明「谁、缺什么」', () => {
  assert.equal(
    formatBatchConfirmIssue(BACKEND_ISSUES[0]),
    'EMP260002：请先刷新当月工资和人力成本分摊，再确认工资单'
  )
  assert.deepEqual(formatBatchConfirmIssueLines(BACKEND_ISSUES), [
    'EMP260002：请先刷新当月工资和人力成本分摊，再确认工资单',
    'EMP260003：该员工本月没有待确认的草稿工资单'
  ])
})

test('issues 的 HTML 版本每条一行，且原因被转义', () => {
  const html = formatBatchConfirmIssueHtml(BACKEND_ISSUES)
  assert.equal(
    html,
    '<p>EMP260002：请先刷新当月工资和人力成本分摊，再确认工资单</p><p>EMP260003：该员工本月没有待确认的草稿工资单</p>'
  )

  const injected = formatBatchConfirmIssueHtml([
    { employee_code: 'E1', reason: '<img src=x onerror=alert(1)>' }
  ])
  assert.equal(injected.includes('<img'), false)
  assert.equal(injected.includes('&lt;img'), true)
})

test('issues 缺少原因时也能给出可读文案', () => {
  assert.equal(
    formatBatchConfirmIssue({ employee_code: 'EMP260009', reason: '' }),
    'EMP260009：未说明原因'
  )
  assert.equal(
    formatBatchConfirmIssue({}),
    '未知员工：未说明原因'
  )
})

test('批量确认成功时能读到确认张数', () => {
  assert.equal(extractBatchConfirmSuccessCount({ data: { confirmed_count: 7 } }), 7)
  assert.equal(extractBatchConfirmSuccessCount({ confirmed_count: 2 }), 2)
  assert.equal(extractBatchConfirmSuccessCount(null), 0)
})

test('前端 API 提供整月批量确认入口', () => {
  assert.match(
    apiSource,
    /async confirmHrPayrollRecordsBatch\s*\(\s*data\s*\)\s*\{[\s\S]*?_post\(\s*'\/hr\/payroll-records\/confirm-batch'\s*,\s*data\s*\)/
  )
})

test('工资单页面提供「整月批量确认」入口并逐条展示 issues', () => {
  assert.match(salarySource, /整月批量确认/)
  assert.match(salarySource, /api\.confirmHrPayrollRecordsBatch\(\{\s*year_month:\s*selectedMonth\.value\s*\}\)/)
  assert.match(salarySource, /extractBatchConfirmIssues/)
  assert.match(salarySource, /formatBatchConfirmIssueHtml/)
  assert.match(salarySource, /已确认 \$\{confirmedCount\} 张工资单/)
  // 待办清单要渲染出来
  assert.match(salarySource, /batchConfirmIssues/)
})

test('工资单页面不再硬编码历史利润基数口径', () => {
  assert.equal(salarySource.includes("basis_version: 'A_PRE_COMMISSION_LABOR_V2'"), false)
  assert.match(salarySource, /formatBasisVersion\(laborCostPolicy\.basis_version\)/)
})
