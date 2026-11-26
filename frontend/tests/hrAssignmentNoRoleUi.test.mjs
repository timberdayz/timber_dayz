import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import {
  POSITION_UNSET_LABEL,
  buildBatchCreateItems,
  buildBatchUpdatePayload,
  buildPositionNameMap,
  collectAssignmentIds,
  resolvePositionName,
  summarizeEmployeeCommissions
} from '../src/domains/business/views/hr/shopAssignmentRules.js'

const repoRoot = resolve(import.meta.dirname, '..')
const viewSource = readFileSync(
  resolve(repoRoot, 'src/domains/business/views/hr/ShopAssignment.vue'),
  'utf8'
)
const rulesSource = readFileSync(
  resolve(repoRoot, 'src/domains/business/views/hr/shopAssignmentRules.js'),
  'utf8'
)
const apiSource = readFileSync(resolve(repoRoot, 'src/api/index.js'), 'utf8')

test('添加人员弹窗不再有角色下拉，表单也不再带 role', () => {
  assert.equal(viewSource.includes('label="角色"'), false)
  assert.equal(viewSource.includes('form.role'), false)
  assert.doesNotMatch(viewSource, /\brole\b/)
  assert.equal(viewSource.includes('supervisor'), false)
  assert.equal(viewSource.includes('operator'), false)
  assert.match(viewSource, /添加人员/)
})

test('页面上不再出现「主管」「操作员」标签', () => {
  assert.equal(viewSource.includes('主管'), false)
  assert.equal(viewSource.includes('操作员'), false)
  assert.equal(viewSource.includes('item.role'), false)
})

test('层级只读展示员工档案的职位名', () => {
  assert.match(viewSource, /position_name/)
  assert.match(viewSource, /（未设岗位）/)
  assert.match(viewSource, /positionNameOf/)
  assert.match(viewSource, /item\.position_name/)
})

test('汇总区返回职位名而不是角色', () => {
  const summary = summarizeEmployeeCommissions(
    [{ employee_code: 'EMP260001', employee_name: '泽伟' }],
    { EMP260001: '主管' }
  )
  assert.equal(summary[0].position_name, '主管')
  assert.equal('role' in summary[0], false)
})

test('职位名取不到时显示「（未设岗位）」', () => {
  assert.equal(resolvePositionName('EMP260001', {}), POSITION_UNSET_LABEL)
  assert.equal(resolvePositionName('EMP260001', { EMP260001: '总经理' }), '总经理')

  const map = buildPositionNameMap([
    { employee_code: 'EMP260001', position_name: '主管' },
    { employee_code: 'EMP260002', position_name: null },
    { employee_code: 'EMP260003', position_name: ' 专员 ' }
  ])
  assert.equal(map.EMP260001, '主管')
  assert.equal('EMP260002' in map, false)
  assert.equal(map.EMP260003, '专员')
})

test('职位映射必须用全量员工名单：离职员工的归属行是历史事实，要看得出他的职位', () => {
  assert.match(
    viewSource,
    /buildPositionNameMap\(employees\.value\)/,
    '职位映射必须取全量员工（含离职）；若只取在职名单，离职员工在归属行里会误显示「（未设岗位）」'
  )
  assert.equal(
    /buildPositionNameMap\(employeesActive\.value\)/.test(viewSource),
    false,
    '职位映射不得只用在职名单'
  )
})

test('规则文件不再导出角色推断', () => {
  assert.equal(rulesSource.includes('inferAssignmentRole'), false)
  assert.equal(rulesSource.includes('supervisor'), false)
})

test('表格支持多选店铺，并显示已选店铺数', () => {
  assert.match(viewSource, /type="selection"/)
  assert.match(viewSource, /已选/)
  assert.match(viewSource, /家店铺/)
})

test('批量三能力入口都在页面上', () => {
  assert.match(viewSource, /批量挂靠/)
  assert.match(viewSource, /批量调整比例/)
  assert.match(viewSource, /批量移除/)
})

test('批量操作统一走同一个后端批量端点', () => {
  assert.match(
    apiSource,
    /async batchHrEmployeeShopAssignments\s*\(data\)\s*\{\s*return await this\._post\('\/hr\/employee-shop-assignments\/batch',\s*data\)\s*\}/
  )
  assert.match(viewSource, /api\.batchHrEmployeeShopAssignments\(/)
  assert.match(viewSource, /mode:\s*'create'/)
  assert.match(viewSource, /mode:\s*'update'/)
  assert.match(viewSource, /mode:\s*'delete'/)
})

test('批量保存并行提交，失败不中断其余行', () => {
  assert.match(viewSource, /Promise\.allSettled/)
  assert.match(viewSource, /成功/)
  assert.match(viewSource, /失败/)
})

test('批量提交前按店铺合计做超限预检', () => {
  assert.match(viewSource, /validateShopAssignmentRatio/)
})

test('批量挂靠 items 只带定位键和比例', () => {
  const items = buildBatchCreateItems(
    [{ platform_code: 'Shopee', shop_id: 'S1' }],
    'EMP260001',
    0.05
  )
  assert.deepEqual(items, [
    {
      employee_code: 'EMP260001',
      platform_code: 'shopee',
      shop_id: 'S1',
      commission_ratio: 0.05
    }
  ])
})

test('批量改比例的 items 与 assignment_ids 一一对应', () => {
  const payload = buildBatchUpdatePayload(
    [
      { id: 7, employee_code: 'EMP260001', platform_code: 'shopee', shop_id: 'S1' },
      { id: 9, employee_code: 'EMP260002', platform_code: 'tiktok', shop_id: 'S2' }
    ],
    0.1
  )
  assert.equal(payload.items.length, 2)
  assert.deepEqual(payload.assignment_ids, [7, 9])
  assert.equal(payload.items[0].commission_ratio, 0.1)
  assert.equal(payload.items[1].platform_code, 'tiktok')
})

test('没落库的人员行不进批量提交（items 与 ids 保持等长）', () => {
  const payload = buildBatchUpdatePayload(
    [
      { id: 7, employee_code: 'EMP260001', platform_code: 'shopee', shop_id: 'S1' },
      { employee_code: 'EMP260002', platform_code: 'shopee', shop_id: 'S1' }
    ],
    0.1
  )
  assert.equal(payload.items.length, 1)
  assert.deepEqual(payload.assignment_ids, [7])
})

test('批量移除收集选中店铺下全部归属 id', () => {
  const ids = collectAssignmentIds([
    { assignments: [{ id: 1 }, { id: 2 }] },
    { assignments: [{ id: 3 }] },
    { assignments: [] }
  ])
  assert.deepEqual(ids, [1, 2, 3])
})
