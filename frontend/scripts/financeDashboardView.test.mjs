import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const frontendRoot = path.resolve(scriptDir, '..')
const dashboardDir = path.join(frontendRoot, 'src/domains/business/views/finance-dashboard')

const readSource = (...segments) => readFileSync(path.join(frontendRoot, ...segments), 'utf8')

const viewSource = readSource('src/domains/business/views/finance-dashboard/FinanceDashboardView.vue')
const cardsSource = readSource('src/domains/business/views/finance-dashboard/ProfitOverviewCards.vue')
const tableSource = readSource('src/domains/business/views/finance-dashboard/ShopAllocationTable.vue')
const panelSource = readSource('src/domains/business/views/finance-dashboard/AdjustmentPanel.vue')
const shellSource = readSource('src/domains/business/views/FinancialManagement.vue')
const storeSource = readSource('src/stores/financeDashboard.js')
const financeApiSource = readSource('src/api/finance.js')
const routerSource = readSource('src/router/index.js')
const menuGroupsSource = readSource('src/config/menuGroups.js')

const dashboardSources = [viewSource, cardsSource, tableSource, panelSource]
const allDashboardSources = [...dashboardSources, storeSource]

/** 从源码里抽出函数体（按大括号配对，忽略字符串字面量）。 */
function extractFunctionSource(source, functionName) {
  const declarationIndex = source.indexOf(`function ${functionName}(`)
  assert.ok(declarationIndex !== -1, `未找到函数：${functionName}`)
  const bodyStart = source.indexOf('{', declarationIndex)
  let depth = 0
  for (let index = bodyStart; index < source.length; index += 1) {
    const character = source[index]
    if (character === '{') depth += 1
    if (character === '}') {
      depth -= 1
      if (depth === 0) return source.slice(declarationIndex, index + 1)
    }
  }
  throw new Error(`函数体未闭合：${functionName}`)
}

function loadStoreFunction(functionName) {
  const functionSource = extractFunctionSource(storeSource, functionName)
  return new Function(`return (${functionSource})`)()
}

function collectSourceFiles(rootDir) {
  const collected = []
  for (const entry of readdirSync(rootDir)) {
    const absolute = path.join(rootDir, entry)
    if (statSync(absolute).isDirectory()) {
      collected.push(...collectSourceFiles(absolute))
      continue
    }
    if (/\.(vue|js|mjs|ts)$/.test(entry)) collected.push(absolute)
  }
  return collected
}

test('看板不提供预算比例输入', () => {
  for (const source of allDashboardSources) {
    assert.ok(!source.includes('target_ratio'), '看板不得出现目标比例输入')
    assert.ok(!source.includes('预算(%)'), '看板不得出现预算百分比输入')
  }
})

test('看板不承载口径计算', () => {
  for (const source of allDashboardSources) {
    assert.ok(!/company_retained_amount\s*=/.test(source), '前端不得重算公司留存')
    assert.ok(!/allocation_ratio\s*=/.test(source), '前端不得重算分配占比')
    assert.ok(!source.includes('difference_amount'), '看板不得保留预算差异金额')
    assert.ok(!source.includes('difference_ratio'), '看板不得保留预算差异比例')
  }
})

test('看板移除审批、回退与跟投交互', () => {
  const forbidden = ['审批通过', '回退草稿', '重建月结', '查询月结', '保存目标', '跟投']
  for (const source of allDashboardSources) {
    for (const token of forbidden) {
      assert.ok(!source.includes(token), `看板不得出现旧交互：${token}`)
    }
    assert.ok(!source.includes('follow'), '看板不得包含跟投切片')
  }
})

test('store 只提供看板只读动作与人工调整写入口', () => {
  assert.ok(storeSource.includes('fetchDashboard'))
  assert.ok(storeSource.includes('addAdjustment'))
  assert.ok(storeSource.includes('removeAdjustment'))
  assert.ok(!storeSource.includes('follow'))
  assert.ok(!storeSource.includes('rebuildMonthlyProfitSettlement'))
  assert.ok(!storeSource.includes('approveMonthlyProfitSettlement'))
  assert.ok(!storeSource.includes('reopenMonthlyProfitSettlement'))
})

test('store 把请求异常写进 error 状态，失败对页面可见', () => {
  assert.ok(storeSource.includes('this.error ='))
  assert.ok(storeSource.includes('this.actionError ='))
  assert.ok(storeSource.includes('catch (error)'))
  assert.ok(viewSource.includes('<el-alert'))
  assert.ok(viewSource.includes('store.error'))
  assert.ok(panelSource.includes('error'))
})

test('调整项失败要把后端 detail 显示出来', () => {
  assert.ok(storeSource.includes('extractDashboardError'))
  assert.ok(storeSource.includes('detail'))
  assert.ok(panelSource.includes(':title="error"'))
})

test('结果区展示后端下发的全部金额与标记', () => {
  for (const field of [
    'net_profit_amount',
    'performance_salary_amount',
    'commission_amount',
    'employee_allocation_amount',
    'manual_adjustment_amount',
    'company_retained_amount',
    'allocation_ratio',
    'over_allocation_flag'
  ]) {
    assert.ok(cardsSource.includes(field), `结果区必须渲染后端字段：${field}`)
  }
})

test('人工调整笔数与总额在结果区可见', () => {
  assert.ok(cardsSource.includes('manual_adjustment_count'))
  assert.ok(cardsSource.includes('笔人工调整'))
  assert.ok(cardsSource.includes('manual_adjustment_amount'))
})

test('店铺分布表渲染后端字段且缺失值留占位', () => {
  for (const field of [
    'profit_basis_amount',
    'performance_amount',
    'commission_amount',
    'allocation_amount',
    'allocation_ratio',
    'over_allocation_flag'
  ]) {
    assert.ok(tableSource.includes(field), `店铺分布必须渲染后端字段：${field}`)
  }
  assert.ok(tableSource.includes('—'))
})

test('调整项类型枚举与后端一致，原因必填，符号含义写在界面上', () => {
  for (const type of ['manual_adjustment', 'cross_period_expense', 'one_off_gain_loss', 'correction']) {
    assert.ok(panelSource.includes(type), `调整类型必须覆盖：${type}`)
  }
  assert.ok(panelSource.includes('请写明调整原因'))
  assert.ok(panelSource.includes('正数'))
  assert.ok(panelSource.includes('负数'))
  assert.ok(panelSource.includes('扣减'))
  assert.ok(panelSource.includes('追加'))
})

test('金额格式化：千分位 + 币种符号，负数可见且不截断', () => {
  const formatAmount = loadStoreFunction('formatDashboardAmount')

  assert.equal(formatAmount(1234.5), '¥1,234.50')
  assert.equal(formatAmount(0), '¥0.00')
  assert.equal(formatAmount(-500), '-¥500.00')
  assert.equal(formatAmount(-1234.5), '-¥1,234.50')
  assert.equal(formatAmount(null), '—')
  assert.equal(formatAmount(undefined), '—')
  assert.equal(formatAmount(''), '—')
  assert.equal(formatAmount('not-a-number'), '—')
})

test('比率格式化统一为百分比，缺失值留占位', () => {
  const formatRatio = loadStoreFunction('formatDashboardRatio')

  assert.equal(formatRatio(0.1053), '10.53%')
  assert.equal(formatRatio(1), '100.00%')
  assert.equal(formatRatio(0), '0.00%')
  assert.equal(formatRatio(null), '—')
  assert.equal(formatRatio(undefined), '—')
})

test('负数显红的样式存在', () => {
  assert.ok(cardsSource.includes('negative'))
  assert.ok(cardsSource.includes('#f56c6c'))
  assert.ok(tableSource.includes('negative'))
})

test('API 封装指向看板契约', () => {
  assert.ok(financeApiSource.includes('getFinanceDashboard'))
  assert.ok(financeApiSource.includes("api._get('/finance/monthly-profit-settlement'"))
  assert.ok(financeApiSource.includes('createFinanceAdjustment'))
  assert.ok(financeApiSource.includes("api._post('/finance/monthly-profit-settlement/adjustments'"))
  assert.ok(financeApiSource.includes('deleteFinanceAdjustment'))
  assert.ok(financeApiSource.includes('/finance/monthly-profit-settlement/adjustments/${adjustmentId}'))
  assert.ok(!financeApiSource.includes('rebuildMonthlyProfitSettlement'))
  assert.ok(!financeApiSource.includes('updateMonthlyProfitSettlementTargets'))
  assert.ok(!financeApiSource.includes('approveMonthlyProfitSettlement'))
  assert.ok(!financeApiSource.includes('reopenMonthlyProfitSettlement'))
})

test('路由标题与菜单显示名改为月度利润看板', () => {
  assert.ok(routerSource.includes("title: '月度利润看板'"))
  assert.ok(routerSource.includes("title: '财务概览'"))
  assert.ok(!routerSource.includes("title: '??????'"))
  assert.ok(menuGroupsSource.includes("'/financial-management': '月度利润看板'"))
  assert.ok(!menuGroupsSource.includes('财务结算中心'))
})

test('财务页面改成只挂载看板的薄壳', () => {
  assert.ok(shellSource.includes('FinanceDashboardView'))
  assert.ok(!shellSource.includes('MonthlySettlementPanel'))
  assert.ok(!shellSource.includes('SettlementWorkspacePanel'))
  assert.ok(!shellSource.includes('financeSettlement'))
})

test('前端不再引用旧结算目录与旧 store 标识符', () => {
  const sourceFiles = collectSourceFiles(path.join(frontendRoot, 'src'))
  for (const file of sourceFiles) {
    const content = readFileSync(file, 'utf8')
    assert.ok(!content.includes('finance-settlement'), `仍有 finance-settlement 引用：${file}`)
    assert.ok(!content.includes('financeSettlement'), `仍有 financeSettlement 引用：${file}`)
  }
})
