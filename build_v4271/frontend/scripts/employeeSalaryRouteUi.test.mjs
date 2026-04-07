import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const routerSource = fs.readFileSync(
  path.resolve(__dirname, '../src/router/index.js'),
  'utf8'
)
const menuSource = fs.readFileSync(
  path.resolve(__dirname, '../src/config/menuGroups.js'),
  'utf8'
)
const apiSource = fs.readFileSync(
  path.resolve(__dirname, '../src/api/index.js'),
  'utf8'
)

test('frontend API exposes employee salary helpers', () => {
  assert.equal(apiSource.includes('async getHrSalaryStructureHistory(employeeCode)'), true)
  assert.equal(apiSource.includes('async updateHrSalaryStructure(employeeCode, data)'), true)
  assert.equal(apiSource.includes('async refreshHrPayrollRecord(employeeCode, yearMonth)'), true)
})

test('router exposes dedicated employee salary page', () => {
  assert.equal(routerSource.includes("path: '/employee-salary'"), true)
  assert.equal(routerSource.includes("name: 'EmployeeSalary'"), true)
  assert.equal(routerSource.includes("views/hr/EmployeeSalary.vue"), true)
})

test('human resources menu includes employee salary entry', () => {
  assert.equal(menuSource.includes('/employee-salary'), true)
})
