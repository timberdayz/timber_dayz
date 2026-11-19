import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  EMPLOYEE_STATUS,
  EMPLOYEE_STATUS_LABEL,
  EMPLOYEE_STATUS_TAG_TYPE,
  EMPLOYEE_IDENTITY,
  EMPLOYEE_IDENTITY_LABEL,
  PAYROLL_STATUS_LABEL,
  PAYROLL_STATUS_TAG_TYPE,
  employeeStatusLabel,
  employeeStatusTagType,
  employeeIdentityLabel,
  payrollStatusLabel,
  payrollStatusTagType
} from '../src/constants/hr.js'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const constantsPath = path.resolve(__dirname, '../src/constants/hr.js')
const humanResourcesPath = path.resolve(
  __dirname,
  '../src/domains/business/views/HumanResources.vue'
)
const employeeTabPath = path.resolve(
  __dirname,
  '../src/domains/business/views/hr/EmployeeTab.vue'
)
const employeeSalaryPath = path.resolve(
  __dirname,
  '../src/domains/business/views/hr/EmployeeSalary.vue'
)
const employeeManagementPath = path.resolve(
  __dirname,
  '../src/domains/business/views/hr/EmployeeManagement.vue'
)
const userManagementPath = path.resolve(
  __dirname,
  '../src/domains/platform/views/UserManagement.vue'
)
const userApprovalPath = path.resolve(
  __dirname,
  '../src/domains/platform/views/admin/UserApproval.vue'
)

const constantsSource = fs.readFileSync(constantsPath, 'utf8')
const humanResourcesSource = fs.readFileSync(humanResourcesPath, 'utf8')
const employeeTabSource = fs.readFileSync(employeeTabPath, 'utf8')
const employeeSalarySource = fs.readFileSync(employeeSalaryPath, 'utf8')
const employeeManagementSource = fs.readFileSync(employeeManagementPath, 'utf8')
const userManagementSource = fs.readFileSync(userManagementPath, 'utf8')
const userApprovalSource = fs.readFileSync(userApprovalPath, 'utf8')

const ALLOWED_TAG_TYPES = ['success', 'warning', 'info', 'danger', 'primary', '']
const RAW_STATUS_VALUES = Object.values(EMPLOYEE_STATUS)

/**
 * 取某个按钮的开标签里的 :disabled 表达式（用于验证离职条件没有误伤结算按钮）。
 */
function findButtonDisabledExpression(source, label) {
  const labelIndex = source.indexOf(label)
  if (labelIndex === -1) return null
  const buttonStart = source.lastIndexOf('<el-button', labelIndex)
  if (buttonStart === -1) return null
  const buttonEnd = source.indexOf('>', buttonStart)
  if (buttonEnd === -1) return null
  const openTag = source.slice(buttonStart, buttonEnd)
  const match = openTag.match(/:disabled="([^"]*)"/)
  return match ? match[1] : null
}

test('hr constants expose one vocabulary without raw English user-facing labels', () => {
  for (const [key, label] of Object.entries(EMPLOYEE_STATUS_LABEL)) {
    assert.equal(typeof label, 'string', `employee status ${key} should have a text label`)
    assert.notEqual(label, key, `employee status ${key} must not display its raw value`)
    assert.equal(
      RAW_STATUS_VALUES.includes(label),
      false,
      `employee status label of ${key} must not be a raw status value`
    )
  }

  for (const [key, label] of Object.entries(EMPLOYEE_IDENTITY_LABEL)) {
    assert.equal(typeof label, 'string', `identity ${key} should have a text label`)
    assert.notEqual(label, key, `identity ${key} must not display its raw value`)
    assert.equal(
      Object.values(EMPLOYEE_IDENTITY).includes(label),
      false,
      `identity label of ${key} must not be a raw identity value`
    )
  }

  for (const [key, label] of Object.entries(PAYROLL_STATUS_LABEL)) {
    assert.equal(typeof label, 'string', `payroll status ${key} should have a text label`)
    assert.notEqual(label, key, `payroll status ${key} must not display its raw value`)
    assert.equal(
      Object.keys(PAYROLL_STATUS_LABEL).includes(label),
      false,
      `payroll label of ${key} must not be a raw payroll status value`
    )
  }

  // 作废（void）是第四个工资单状态，必须有中文展示
  assert.equal(PAYROLL_STATUS_LABEL.void, '已作废')
  assert.equal(PAYROLL_STATUS_TAG_TYPE.void, 'danger')

  for (const [key, type] of Object.entries(EMPLOYEE_STATUS_TAG_TYPE)) {
    assert.equal(
      ALLOWED_TAG_TYPES.includes(type),
      true,
      `employee status ${key} should use an Element Plus tag type`
    )
  }
  for (const [key, type] of Object.entries(PAYROLL_STATUS_TAG_TYPE)) {
    assert.equal(
      ALLOWED_TAG_TYPES.includes(type),
      true,
      `payroll status ${key} should use an Element Plus tag type`
    )
  }

  // 词表里不允许出现把原始英文值当文案用的写法
  assert.equal(
    /label\s*:\s*'(active|inactive|probation|leave|visitor|employee|draft|confirmed|paid|void)'/.test(
      constantsSource
    ),
    false,
    'constants/hr.js should not hardcode raw status values as labels'
  )
})

test('hr constants helpers are defensive with null, undefined and empty input', () => {
  for (const value of [null, undefined, '', '   ']) {
    assert.doesNotThrow(() => employeeStatusLabel(value))
    assert.doesNotThrow(() => employeeStatusTagType(value))
    assert.doesNotThrow(() => employeeIdentityLabel(value))
    assert.doesNotThrow(() => payrollStatusLabel(value))
    assert.doesNotThrow(() => payrollStatusTagType(value))
    assert.equal(typeof employeeStatusLabel(value), 'string')
    assert.equal(typeof employeeIdentityLabel(value), 'string')
    assert.equal(typeof payrollStatusLabel(value), 'string')
  }

  // 未知取值回退到原值，不抛错
  assert.equal(employeeStatusLabel('some_unknown_status'), 'some_unknown_status')
  assert.equal(employeeStatusTagType('some_unknown_status'), 'info')
  assert.equal(employeeIdentityLabel('some_unknown_identity'), 'some_unknown_identity')
  assert.equal(payrollStatusLabel('some_unknown_payroll'), 'some_unknown_payroll')
  assert.equal(payrollStatusTagType('some_unknown_payroll'), 'info')

  // 已知取值走中文词表
  assert.equal(employeeStatusLabel(EMPLOYEE_STATUS.INACTIVE), '已离职')
  assert.equal(employeeStatusTagType(EMPLOYEE_STATUS.INACTIVE), 'danger')
  assert.equal(employeeIdentityLabel(EMPLOYEE_IDENTITY.VISITOR), '访客')
  assert.equal(payrollStatusLabel('void'), '已作废')
})

test('hr pages import the shared vocabulary and never render raw status values', () => {
  for (const [name, source] of [
    ['HumanResources.vue', humanResourcesSource],
    ['EmployeeSalary.vue', employeeSalarySource],
    ['EmployeeTab.vue', employeeTabSource],
    ['EmployeeManagement.vue', employeeManagementSource]
  ]) {
    assert.equal(
      source.includes('from \'@/constants/hr\''),
      true,
      `${name} should import the shared HR vocabulary`
    )
    assert.equal(
      source.includes('employee.status || \'unknown\''),
      false,
      `${name} should not render a raw employee status value`
    )
  }

  assert.equal(
    employeeSalarySource.includes('employeeStatusLabel(employee.status)'),
    true,
    'EmployeeSalary.vue should render the employee status through the shared vocabulary'
  )
  assert.equal(
    employeeSalarySource.includes('employeeStatusTagType(employee.status)'),
    true,
    'EmployeeSalary.vue should color the employee status through the shared vocabulary'
  )
  assert.equal(
    employeeManagementSource.includes('employeeStatusLabel(profile.status)'),
    true,
    'EmployeeManagement.vue should render the profile status through the shared vocabulary'
  )
})

test('employee list defaults to active staff and separates visitors', () => {
  assert.equal(
    employeeTabSource.includes('showInactive'),
    true,
    'EmployeeTab.vue should expose the "show offboarded" switch'
  )
  assert.equal(
    employeeTabSource.includes('isInactiveEmployeeStatus'),
    true,
    'EmployeeTab.vue should hide offboarded employees by default'
  )
  assert.equal(
    employeeTabSource.includes('EMPLOYEE_IDENTITY.EMPLOYEE'),
    true,
    'EmployeeTab.vue should default the identity filter to formal employees'
  )
  assert.equal(
    employeeTabSource.includes('employeeIdentityLabel(scope.row.employee_identity_type)'),
    true,
    'EmployeeTab.vue should show the identity column through the shared vocabulary'
  )
  assert.equal(
    employeeTabSource.includes('last_payroll_month'),
    true,
    'EmployeeTab.vue should show the last payroll month column'
  )
  // 部门列只读档案侧真值（department_id），不展示账号上填的部门
  assert.equal(
    employeeTabSource.includes('getDepartmentName(scope.row.department_id)'),
    true,
    'EmployeeTab.vue should read the department from the employee profile'
  )
})

test('offboarding replaces the delete action and keeps the last payroll month', () => {
  for (const [name, source] of [
    ['HumanResources.vue', humanResourcesSource],
    ['EmployeeTab.vue', employeeTabSource]
  ]) {
    assert.equal(
      source.includes('办理离职'),
      true,
      `${name} should expose the "办理离职" wording`
    )
    assert.equal(
      source.includes('offboardHrEmployee'),
      true,
      `${name} should call the offboard endpoint`
    )
  }

  assert.equal(
    employeeTabSource.includes('last_payroll_month'),
    true,
    'EmployeeTab.vue should carry the last payroll month'
  )
  assert.equal(
    humanResourcesSource.includes('办理离职'),
    true,
    'HumanResources.vue should explain the offboard policy on the page'
  )

  assert.equal(
    employeeTabSource.includes('确定要删除该员工吗？'),
    false,
    'the hard delete confirmation should be replaced by the offboard dialog'
  )
  assert.equal(
    employeeTabSource.includes('leave_date') && employeeTabSource.includes('leave_reason'),
    true,
    'the offboard dialog should collect the leave date and the leave reason'
  )
})

test('offboarded employees can still settle payroll but cannot edit salary inputs', () => {
  assert.equal(
    employeeSalarySource.includes('显示离职员工'),
    true,
    'EmployeeSalary.vue should expose the "show offboarded employees" switch'
  )
  assert.equal(
    employeeSalarySource.includes('仅可结算至最后发薪月'),
    true,
    'EmployeeSalary.vue should explain the offboarded settlement boundary'
  )

  // 固定薪资与月度人工录入的保存按钮必须被离职条件置灰
  assert.equal(
    employeeSalarySource.includes(':disabled="!selectedEmployee || isInactiveEmployee"'),
    true,
    'the fixed salary save button should be disabled for offboarded employees'
  )
  assert.equal(
    employeeSalarySource.includes(
      ':disabled="!selectedEmployee || isLockedPayroll || isInactiveEmployee"'
    ),
    true,
    'the monthly input save button should be disabled for offboarded employees'
  )

  // 结算按钮不能被离职条件禁用
  const confirmDisabled = findButtonDisabledExpression(employeeSalarySource, '确认工资单')
  assert.notEqual(confirmDisabled, null, 'the payroll confirm button should exist')
  assert.equal(
    confirmDisabled.includes('isInactiveEmployee'),
    false,
    'the payroll confirm button must stay available for offboarded employees'
  )

  const markPaidDisabled = findButtonDisabledExpression(employeeSalarySource, '标记已发放')
  assert.notEqual(markPaidDisabled, null, 'the payroll paid button should exist')
  assert.equal(
    markPaidDisabled.includes('isInactiveEmployee'),
    false,
    'the payroll paid button must stay available for offboarded employees'
  )
})

test('payroll result area renders the shared payroll status vocabulary', () => {
  assert.equal(
    employeeSalarySource.includes('payrollStatusLabel(payrollRecord.status)'),
    true,
    'EmployeeSalary.vue should render the payroll status through the shared vocabulary'
  )
  assert.equal(
    employeeSalarySource.includes('payrollStatusTagType(payrollRecord.status)'),
    true,
    'EmployeeSalary.vue should color the payroll status through the shared vocabulary'
  )
  assert.equal(
    employeeSalarySource.includes('已作废'),
    true,
    'EmployeeSalary.vue should support the void payroll status'
  )
})

test('void payroll can be undone so a mistaken void never blocks a payment forever', () => {
  assert.equal(
    employeeSalarySource.includes('api.voidHrPayrollRecord'),
    true,
    'EmployeeSalary.vue should expose the void action'
  )
  assert.equal(
    employeeSalarySource.includes('api.unvoidHrPayrollRecord'),
    true,
    'EmployeeSalary.vue should expose the unvoid action'
  )

  // 作废只对草稿开放
  const voidDisabled = findButtonDisabledExpression(employeeSalarySource, '作废工资单')
  assert.notEqual(voidDisabled, null, 'the void button should exist')
  assert.equal(
    voidDisabled.includes("'draft'"),
    true,
    'only draft payroll records may be voided'
  )

  // 撤销作废只对作废单开放
  const unvoidDisabled = findButtonDisabledExpression(employeeSalarySource, '撤销作废')
  assert.notEqual(unvoidDisabled, null, 'the unvoid button should exist')
  assert.equal(
    unvoidDisabled.includes("'void'"),
    true,
    'only voided payroll records may be un-voided'
  )
})

test('employee tab tells the admin which accounts are still occupied by departed staff', () => {
  assert.equal(
    employeeTabSource.includes('occupied_by_departed_employee'),
    true,
    'EmployeeTab.vue should read the top-level occupied accounts key'
  )
  assert.equal(
    employeeTabSource.includes('occupiedByDepartedCount'),
    true,
    'EmployeeTab.vue should surface how many accounts are blocked by departed staff'
  )
})

test('user management links accounts to active employees only', () => {
  assert.equal(
    userManagementSource.includes('isInactiveEmployeeStatus'),
    true,
    'UserManagement.vue should filter out offboarded employees'
  )
  assert.equal(
    userManagementSource.includes('employeeIdentityLabel'),
    true,
    'UserManagement.vue should show the employee identity in the option label'
  )
  assert.equal(
    userManagementSource.includes('extractErrorMessage'),
    true,
    'UserManagement.vue should surface the backend binding conflict message'
  )
})

test('user approval can create the employee profile on approval', () => {
  for (const field of [
    'create_employee',
    'employee_department_id',
    'employee_position_id',
    'employee_hire_date',
    'employee_status'
  ]) {
    assert.equal(
      userApprovalSource.includes(field),
      true,
      `UserApproval.vue should send ${field} when approving`
    )
  }
  assert.equal(
    userApprovalSource.includes('同时建立员工档案'),
    true,
    'UserApproval.vue should expose the "create employee profile" checkbox'
  )
  assert.equal(
    userApprovalSource.includes('getHrDepartments') && userApprovalSource.includes('getHrPositions'),
    true,
    'UserApproval.vue should load the department and position options'
  )
})
