import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const repoRoot = resolve(import.meta.dirname, '..')
const read = (relativePath) => readFileSync(resolve(repoRoot, relativePath), 'utf8')

const viewSource = read('src/domains/business/views/hr/MonthlySettlement.vue')
const apiSource = read('src/api/index.js')
const routerSource = read('src/router/index.js')
const rulesSource = read('src/domains/business/views/hr/settlementDisplayRules.js')

test('月度结算单页面调用 /hr/monthly-settlement 接口并带上结算月份', () => {
  assert.match(
    apiSource,
    /async getHrMonthlySettlement\s*\(\s*params\s*=\s*\{\s*\}\s*\)\s*\{[\s\S]*?_get\('\/hr\/monthly-settlement'\s*,\s*\{\s*params\s*\}\s*\)/
  )
  assert.match(
    viewSource,
    /api\.getHrMonthlySettlement\(\s*\{\s*year_month:\s*yearMonth\.value\s*\}\s*\)/
  )
  // 页面不直接用 axios，统一走 frontend/src/api
  assert.doesNotMatch(viewSource, /from 'axios'/)
})

test('汇总卡片直接展示后端 summary 里的合计数，前端不做二次计算', () => {
  assert.match(viewSource, /summary\.employee_count/)
  assert.match(viewSource, /summary\.formal_count/)
  assert.match(viewSource, /summary\.not_participating_count/)
  assert.match(viewSource, /summary\.pending_count/)
  assert.match(viewSource, /summary\.payroll_confirmed_count/)
  assert.match(viewSource, /summary\.payroll_draft_count/)
  assert.match(viewSource, /summary\.shop_count/)
  assert.match(viewSource, /formatMoney\(summary\.total_commission\)/)
  assert.match(viewSource, /formatMoney\(summary\.total_performance_salary\)/)
  assert.match(viewSource, /formatMoney\(summary\.total_net_salary\)/)
  // 金额不允许在前端做加减乘除
  assert.doesNotMatch(viewSource, /summary\.total_(commission|performance_salary|net_salary)\s*[-+*/]/)
})

test('不参与考核、亏损、待补数据都有各自不同的徽标', () => {
  // 员工考核状态：不参与考核（info）
  assert.match(rulesSource, /case 'not_participating':[\s\S]{0,120}label: '不参与考核'/)
  assert.match(rulesSource, /case 'not_participating':[\s\S]{0,120}type: 'info'/)
  // 员工考核状态：待补个人绩效 / 待补店铺绩效（warning）
  assert.match(rulesSource, /case 'pending_personal_input':[\s\S]{0,200}label: '待补数据'/)
  // 店铺考核状态：不参与考核（info）与待补数据（warning）
  assert.match(rulesSource, /case 'not_applicable':[\s\S]{0,120}label: '本月不参与考核'/)
  assert.match(rulesSource, /case 'partial':[\s\S]{0,120}label: '待补数据'/)
  // 利润状态：亏损必须是 danger
  assert.match(rulesSource, /case 'loss':[\s\S]{0,120}label: '亏损',\s*type: 'danger'/)
  // 页面按后端状态渲染徽标，并允许后端返回页面上没覆盖的状态
  assert.match(viewSource, /employeeCalculationStatusTag/)
  assert.match(viewSource, /shopCalculationStatusTag/)
  assert.match(viewSource, /profitStatusTag/)
  assert.match(viewSource, /:type="row\.status_tag\.type"/)
  assert.match(viewSource, /:type="row\.profit_tag\.type"/)
  assert.match(viewSource, /EMPLOYEE_STATUS_FALLBACK/)
  assert.match(viewSource, /missing: \{ label: '缺记录', type: 'danger' \}/)
})

test('提成为 0 的业务原因（commission_zero_reason）能显示出来', () => {
  assert.match(viewSource, /row\.commission_zero_reason/)
  assert.match(viewSource, /formatCommissionZeroReason\(row\.commission_zero_reason\)/)
  assert.match(viewSource, /row\.zero_reason/)
  assert.match(viewSource, /提成为 0 的原因/)
})

test('「未配置可分配率」与「可分配率为 0」显示成不同状态', () => {
  assert.match(
    viewSource,
    /describeAllocatableRate\(row\.is_allocatable_rate_configured,\s*row\.allocatable_profit_rate\)/
  )
  assert.match(rulesSource, /export function describeAllocatableRate\(isConfigured, rate\)/)
  assert.match(
    rulesSource,
    /if \(!isConfigured\) \{[\s\S]*?label: '未配置'[\s\S]*?\}\s*if \(numeric <= 0\) \{[\s\S]*?label: '0%'/
  )
  // 两者的业务原因文案也必须不同
  assert.match(rulesSource, /text: '未配置可分配率，该店本月不参与提成分配'/)
  assert.match(rulesSource, /text: '可分配率为 0，该店本月不参与提成分配'/)
})

test('阻断项逐条列出：谁、缺什么、去哪补', () => {
  assert.match(viewSource, /settlement\.value\?\.blocking_issues/)
  assert.match(viewSource, /:data="blockingIssueRows"/)
  assert.match(viewSource, /<el-table-column prop="employee_code" label="员工编号"/)
  assert.match(viewSource, /<el-table-column prop="employee_name" label="姓名"/)
  assert.match(viewSource, /<el-table-column prop="reason" label="缺什么"/)
  assert.match(viewSource, /<el-table-column prop="action" label="去哪补"/)
})

test('是否可结算用状态条表达，并区分加载态、错误态与空态', () => {
  assert.match(viewSource, /summary\.value\.is_settlement_ready === true/)
  assert.match(viewSource, /settlement-banner--ready/)
  assert.match(viewSource, /settlement-banner--blocked/)
  assert.match(viewSource, /el-skeleton/)
  assert.match(viewSource, /errorMessage/)
  assert.match(viewSource, /el-empty/)
})

test('路由已追加一条指向月度结算单页面的记录', () => {
  assert.match(
    routerSource,
    /path: '\/hr-monthly-settlement'[\s\S]{0,200}name: 'HRMonthlySettlement'[\s\S]{0,200}MonthlySettlement\.vue/
  )
})

test('api/index.js 同时保留结算预览方法与月度结算单方法', () => {
  assert.match(apiSource, /async getHrCommissionSettlementPreview\s*\(/)
  assert.match(apiSource, /async getHrMonthlySettlement\s*\(/)
})

test('三种系数分开显示：分数档位 / 绩效工资 / 店铺结算，不再混成「结算系数」一列', () => {
  // 员工行：分数档位系数（提成与绩效工资共同的约束项）
  assert.match(viewSource, /label="分数档位系数"/)
  assert.match(viewSource, /formatCoefficient\(row\.score_coefficient\)/)
  // 员工行：绩效工资系数（只用于绩效工资）
  assert.match(viewSource, /label="绩效工资系数"/)
  assert.match(viewSource, /formatCoefficient\(row\.performance_salary_coefficient\)/)
  // 旧的含糊列名不能再出现
  assert.doesNotMatch(viewSource, /label="结算系数"/)
  // 店铺行仍然是「店铺结算系数」
  assert.match(viewSource, /label="店铺结算系数"/)
})

test('提成构成逐店列出，能自己把提成金额加出来', () => {
  assert.match(viewSource, /label="提成构成"/)
  assert.match(viewSource, /row\.shop_breaks/)
  assert.match(viewSource, /function shopBreakSummary\(row\)/)
  assert.match(viewSource, /function shopBreakHint\(row\)/)
  // 逐店金额不许在前端做二次计算，只展示后端下发的数
  assert.match(viewSource, /formatMoney\(item\.commission_amount\)/)
  assert.doesNotMatch(viewSource, /shop_breaks[\s\S]{0,200}item\.commission_amount\s*[-+*/]/)
})
