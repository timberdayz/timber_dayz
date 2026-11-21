import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const source = fs.readFileSync(
  path.resolve(__dirname, '../src/domains/business/views/hr/ShopAssignment.vue'),
  'utf8'
)

test('ShopAssignment page shows order profit and settlement basis as a reference value', () => {
  assert.equal(source.includes('当月利润'), true)
  // 列标题必须是「结算基数（参考）」：这一列对不参与考核的店是现场估算参考值，
  // 叫「提成计算基数」会让人以为它就是提成实际用的数。
  assert.equal(source.includes('结算基数（参考）'), true)
  assert.equal(source.includes('提成计算基数'), false)
  assert.equal(source.includes('profit_basis_amount'), true)
  assert.equal(source.includes('PROFIT_BASIS_REFERENCE_HINT'), true)
})

test('ShopAssignment page uses net-profit wording for allocation and payout labels', () => {
  assert.equal(source.includes('可分配净利润率'), true)
  // 提成口径已归一：三列合并为一列「预计提成（实发口径）」，
  // 不再并列展示「主管/操作员提成（未含结算系数）」这种旧口径。
  assert.equal(source.includes('预计提成（实发口径）'), true)
  assert.equal(source.includes('未含结算系数'), false)
})

test('Employee salary page distinguishes draft previews from locked payrolls', () => {
  const salarySource = fs.readFileSync(
    path.resolve(__dirname, '../src/domains/business/views/hr/EmployeeSalary.vue'),
    'utf8'
  )

  assert.equal(salarySource.includes('提成预览，未锁定'), true)
  assert.equal(salarySource.includes('成本与提成已锁定'), true)
})
