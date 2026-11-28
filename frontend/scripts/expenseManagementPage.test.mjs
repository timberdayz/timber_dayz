import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const pageSource = readFileSync(
  new URL('../src/domains/business/views/finance/ExpenseManagement.vue', import.meta.url),
  'utf8'
)

test('首屏先等店铺列表就绪再加载月度费用', () => {
  assert.ok(pageSource.includes('await loadShops()'), 'onMounted 必须 await loadShops()')
  assert.ok(
    !/onMounted\([\s\S]{0,400}loadShops\(\)\s*\n\s*loadMonthlyExpenses/.test(pageSource),
    '不得在 loadShops() 未完成时直接加载月度费用'
  )
})

test('店铺集合拆成全部与在营两组', () => {
  assert.ok(pageSource.includes('splitShopsByAvailability'))
  assert.ok(pageSource.includes('operatingShops'))
  assert.ok(pageSource.includes('allShops'))
})

test('月度表格支持平台分段与租户维度', () => {
  assert.ok(pageSource.includes('platformScope'))
  assert.ok(pageSource.includes('main_account_id'))
  assert.ok(pageSource.includes('租户'))
})

test('已停用店铺有明确标注', () => {
  assert.ok(pageSource.includes('已停用'))
  assert.ok(pageSource.includes('shop_enabled'))
})

test('快速拆分使用 view-model 的范围解析', () => {
  assert.ok(pageSource.includes('resolveQuickSplitTargets'))
  assert.ok(pageSource.includes('countSplitTargets'))
})

test('快速拆分提供范围选择且只覆盖目标集合', () => {
  assert.ok(pageSource.includes('quickSplitScope'))
  assert.ok(pageSource.includes('仅 Shopee'))
  assert.ok(pageSource.includes('仅 TikTok'))
  assert.ok(pageSource.includes('按租户'))
  assert.ok(
    pageSource.includes('resolveQuickSplitTargets'),
    '必须用 view-model 解析目标集合'
  )
})

test('按店铺视图默认选店且有空状态提示', () => {
  assert.ok(pageSource.includes('el-empty'))
  assert.ok(pageSource.includes('请先选择店铺'))
  assert.ok(pageSource.includes('暂无费用记录'))
  assert.ok(pageSource.includes('handleShopSelectChange'))
})
