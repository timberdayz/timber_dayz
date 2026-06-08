import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const repoRoot = resolve(process.cwd(), 'frontend')
const viewSource = readFileSync(resolve(repoRoot, 'src/domains/business/views/BusinessOverview.vue'), 'utf8')
const apiSource = readFileSync(resolve(repoRoot, 'src/api/index.js'), 'utf8')

test('BusinessOverview exposes KPI granularity controls and forwards granularity/date', () => {
  assert.equal(viewSource.includes('v-model="kpiGranularity"'), true)
  assert.equal(viewSource.includes('<el-radio-button label="daily">日</el-radio-button>'), true)
  assert.equal(viewSource.includes('<el-radio-button label="weekly">周</el-radio-button>'), true)
  assert.equal(viewSource.includes('<el-radio-button label="monthly">月</el-radio-button>'), true)
  assert.equal(viewSource.includes('api.getBusinessOverviewKPI({'), true)
  assert.equal(viewSource.includes('granularity: kpiGranularity.value'), true)
  assert.equal(viewSource.includes('period_key: kpiDateStr'), true)
})

test('BusinessOverview operational metrics use month semantics in UI and API', () => {
  assert.equal(viewSource.includes('v-model="operationalDate"'), true)
  assert.equal(viewSource.includes('type="month"'), true)
  assert.equal(viewSource.includes('period_key: operationalDate.value || undefined'), true)
})

test('BusinessOverview API helper serializes KPI granularity/date', () => {
  assert.equal(apiSource.includes("if (params.granularity) queryParams.append('granularity', params.granularity)"), true)
  assert.equal(apiSource.includes("if (params.date) queryParams.append('date', params.date)"), true)
})

test('BusinessOverview top refresh tolerates partial module failures', () => {
  assert.equal(viewSource.includes('Promise.allSettled(['), true)
  assert.equal(viewSource.includes("ElMessage.warning('部分模块刷新失败，已显示可用数据')"), true)
})

test('BusinessOverview global date sync refreshes KPI for all granularities', () => {
  assert.equal(viewSource.includes("if (useGlobalDate.value.kpi) tasks.push(loadKPIData())"), true)
  assert.equal(viewSource.includes("else if (module === 'kpi') loadKPIData()"), true)
  assert.equal(viewSource.includes('kpiGranularity.value = gr'), true)
  assert.equal(viewSource.includes('useGlobalDate.value = {'), true)
  assert.equal(viewSource.includes("watch("), true)
  assert.equal(viewSource.includes("_globalAutoRefreshReady.value = true"), true)
  assert.equal(viewSource.includes("refreshData()"), true)
})

test('BusinessOverview removes remaining KPI placeholder garble', () => {
  assert.equal(viewSource.includes("return 'YYYY 第 ww 周'"), true)
  assert.equal(viewSource.includes("return '选择月份'"), true)
  assert.equal(viewSource.includes("return '选择周'"), true)
  assert.equal(viewSource.includes("return '选择日期'"), true)
  assert.equal(viewSource.includes("return '当月'"), true)
  assert.equal(viewSource.includes('return `${month}月`'), true)
})

test('BusinessOverview page refresh forces global sync and refreshes all modules', () => {
  assert.equal(viewSource.includes('applyGlobalToModules()'), true)
  assert.equal(viewSource.includes('const results = await Promise.allSettled(['), true)
  assert.equal(viewSource.includes('loadComparisonData()'), true)
  assert.equal(viewSource.includes('loadShopRacingData()'), true)
  assert.equal(viewSource.includes('loadTrafficRanking()'), true)
  assert.equal(viewSource.includes('loadOperationalMetrics()'), true)
})

test('BusinessOverview defines comparison loader used by global refresh', () => {
  assert.match(viewSource, /const loadComparisonData = async \(\) => \{/)
  assert.equal(viewSource.includes('api.getBusinessOverviewComparison({'), true)
})

test('BusinessOverview global date sync includes inventory backlog follow mode', () => {
  assert.equal(viewSource.includes('inventory: true'), true)
  assert.equal(viewSource.includes("if (useGlobalDate.value.inventory) tasks.push(loadInventoryBacklog())"), true)
})

test('BusinessOverview operational metrics fall back to monthly fields in month mode', () => {
  assert.equal(viewSource.includes('today_sales: response.today_sales ?? response.monthly_total_achieved ?? null'), true)
  assert.equal(viewSource.includes('today_order_count: response.today_order_count ?? response.monthly_order_count ?? null'), true)
})

test('BusinessOverview shop racing maps API fields to table fields', () => {
  assert.equal(viewSource.includes('gmv: toNullableNumber(row.gmv)'), true)
  assert.equal(viewSource.includes('profit: toNullableNumber(row.profit)'), true)
  assert.equal(viewSource.includes('profit_margin: calculateProfitMargin(row.profit, row.gmv)'), true)
  assert.equal(viewSource.includes('order_count: toNullableNumber(row.order_count)'), true)
  assert.equal(viewSource.includes('avg_order_value: toNullableNumber(row.avg_order_value)'), true)
  assert.equal(viewSource.includes('target_amount: toNullableNumber(row.target_amount)'), true)
  assert.equal(viewSource.includes('Number(row.achievement_rate) > 1'), true)
})

test('BusinessOverview shop racing exposes lightweight operating sort controls', () => {
  assert.equal(viewSource.includes("const shopRacingSortBy = ref('sales')"), true)
  assert.equal(viewSource.includes('const sortedShopRacingData = computed(() => {'), true)
  assert.equal(viewSource.includes("shopRacingSortBy.value === 'profit'"), true)
  assert.equal(viewSource.includes("shopRacingSortBy.value === 'orders'"), true)
  assert.equal(viewSource.includes("shopRacingSortBy.value === 'achievement'"), true)
})

test('BusinessOverview shop racing handles targetless rows without zero-percent completion', () => {
  assert.equal(viewSource.includes('hasShopRacingTarget(row)'), true)
  assert.equal(viewSource.includes("未设目标"), true)
  assert.equal(viewSource.includes('getShopRacingProgressPercentage(row)'), true)
  assert.equal(viewSource.includes('getShopRacingAchievementText(row)'), true)
})

test('BusinessOverview shop racing keeps account dimension and unmatched shop warning styling', () => {
  assert.equal(viewSource.includes('<el-radio-button label="account">账号</el-radio-button>'), true)
  assert.equal(viewSource.includes('shop-display-cell--unmatched'), true)
  assert.equal(viewSource.includes('未匹配店铺'), true)
})
