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

// ---------------------------------------------------------------------------
// 以下是**防回归**断言：它们守的是「一旦回退就会出错」的具体约束，
// 而不只是「某个字符串还在不在」。
// ---------------------------------------------------------------------------

test('旧口径残留不得复活：availableShops / 本地同名函数', () => {
  // availableShops 是被 allShops + operatingShops 取代的旧集合名，
  // 一旦复活就会丢掉「在营 vs 全部」的区别（停用店会重新拿到空白行）。
  assert.ok(
    !pageSource.includes('availableShops'),
    'availableShops 已被 allShops/operatingShops 取代，不得残留'
  )
  // view-model 已经导出同名函数，组件里再声明一次会造成重复声明，构建直接失败。
  assert.ok(
    !/const buildExpenseRowKey\s*=/.test(pageSource),
    'buildExpenseRowKey 必须来自 @/utils/expenseViewModel.js，组件内不得重复声明'
  )
  assert.ok(
    !/const distributeEvenly\s*=/.test(pageSource),
    'distributeEvenly 必须来自 @/utils/expenseViewModel.js，组件内不得重复声明'
  )
})

test('年度店铺记录集合必须在早退之前刷新（否则停用店进不了下拉）', () => {
  const loadShopExpenses = pageSource.slice(
    pageSource.indexOf('const loadShopExpenses = async () => {')
  )
  const refreshAt = loadShopExpenses.indexOf('await loadShopViewRecordedShops(')
  const earlyReturnAt = loadShopExpenses.indexOf('if (!selectedShopId.value)')

  assert.ok(refreshAt >= 0, 'loadShopExpenses 必须刷新年度有记录的店铺集合')
  assert.ok(earlyReturnAt >= 0, 'loadShopExpenses 必须保留未选店铺的早退分支')
  assert.ok(
    refreshAt < earlyReturnAt,
    '年度记录集合必须在早退分支之前刷新，否则停用店永远进不了下拉（鸡生蛋死循环）'
  )
})

test('拆分店铺数与实际分摊必须同源', () => {
  assert.ok(
    pageSource.includes('countSplitTargets(visibleMonthlyRows'),
    '界面计数必须读可见行 + 同一个 scope'
  )
  assert.ok(
    pageSource.includes('resolveQuickSplitTargets(visibleMonthlyRows'),
    '实际分摊目标必须读可见行 + 同一个 scope'
  )
})

test('停用店铺不参与分摊：分摊集合口径由 view-model 保证', () => {
  // 组件不得自己再实现一套「在营」判定，否则两套口径会漂移。
  const applySplit = pageSource.slice(
    pageSource.indexOf('const handleApplyQuickSplit = async () => {')
  )
  assert.ok(
    applySplit.includes('resolveQuickSplitTargets'),
    '快速拆分必须走 view-model 的目标集合解析'
  )
  assert.ok(
    !/enabled\s*===\s*true[\s\S]{0,200}\.(filter|forEach)\(/.test(applySplit),
    '不得在拆分里另写一套启用状态过滤'
  )
})

test('月度表格数据源必须是分段过滤后的行', () => {
  assert.ok(
    pageSource.includes(':data="visibleMonthlyRows"'),
    '月度表格必须渲染 visibleMonthlyRows，否则平台分段完全不生效'
  )
})

test('空白行只由在营店铺生成', () => {
  assert.ok(
    /const newRows = operatingShops\.value/.test(pageSource),
    '空白行源必须是 operatingShops（在营店）；用 allShops 会让停用店重新拿到空白行'
  )
})

test('删除行必须按行对象定位，不能用过滤后下标', () => {
  // 表格数据源是 visibleMonthlyRows（分段过滤后），$index 是过滤后下标，
  // 拿它去 splice 全量数据会删错行。
  assert.ok(
    pageSource.includes('monthlyTableData.value.indexOf(row)'),
    '删除行必须按行对象在全量数据中定位'
  )
})
