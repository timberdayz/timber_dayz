import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const dashboardApiPath = path.resolve(__dirname, '../src/api/dashboard.js')
const routerPath = path.resolve(__dirname, '../src/router/index.js')
const viewPath = path.resolve(__dirname, '../src/views/finance/BCostAnalysis.vue')
const menuGroupsPath = path.resolve(__dirname, '../src/config/menuGroups.js')

const dashboardSource = fs.readFileSync(dashboardApiPath, 'utf8')
const routerSource = fs.readFileSync(routerPath, 'utf8')
const viewSource = fs.readFileSync(viewPath, 'utf8')
const menuGroupsSource = fs.readFileSync(menuGroupsPath, 'utf8')

function extractBlock(source, marker) {
  const markerIndex = source.indexOf(marker)
  assert.notEqual(markerIndex, -1, `marker not found: ${marker}`)

  const blockStart = source.indexOf('{', markerIndex)
  assert.notEqual(blockStart, -1, `block start not found for: ${marker}`)

  let depth = 0
  for (let index = blockStart; index < source.length; index += 1) {
    const char = source[index]
    if (char === '{') depth += 1
    if (char === '}') depth -= 1
    if (depth === 0) {
      return source.slice(blockStart + 1, index)
    }
  }

  assert.fail(`block end not found for: ${marker}`)
}

test('dashboard API exposes B cost analysis query methods', () => {
  assert.equal(
    dashboardSource.includes('async queryBCostAnalysisOverview(params = {})'),
    true,
    'dashboard API should expose queryBCostAnalysisOverview'
  )
  assert.equal(
    dashboardSource.includes('async queryBCostAnalysisShopMonth(params = {})'),
    true,
    'dashboard API should expose queryBCostAnalysisShopMonth'
  )
  assert.equal(
    dashboardSource.includes('async queryBCostAnalysisOrderDetail(params = {})'),
    true,
    'dashboard API should expose queryBCostAnalysisOrderDetail'
  )
})

test('router registers /b-cost-analysis route with required auth metadata', () => {
  assert.equal(
    routerSource.includes("path: '/b-cost-analysis'"),
    true,
    'router should register /b-cost-analysis path'
  )
  assert.equal(
    routerSource.includes("name: 'BCostAnalysis'"),
    true,
    'router should register BCostAnalysis route name'
  )
  assert.equal(
    routerSource.includes("permission: 'b-cost-analysis'"),
    true,
    'router should protect page with b-cost-analysis permission'
  )
  assert.equal(
    routerSource.includes("roles: ['admin', 'manager', 'finance']"),
    true,
    'router should restrict page roles to admin/manager/finance'
  )
})

test('finance menu group exposes /b-cost-analysis entry', () => {
  assert.equal(
    menuGroupsSource.includes("'/b-cost-analysis'"),
    true,
    'finance menu group should expose /b-cost-analysis'
  )
})

test('B cost page defaults to shop-month summary and requests overview + shop-month on first load', () => {
  assert.equal(
    viewSource.includes("const periodMonth = ref(getCurrentMonth())"),
    true,
    'page should default period_month to current month'
  )
  assert.equal(
    viewSource.includes("const activeView = ref('shop-month')"),
    true,
    'page should default to shop-month summary view'
  )
  assert.equal(
    viewSource.includes('await Promise.all([loadOverview(), loadShopMonth()])'),
    true,
    'first load should request overview and shop-month together'
  )
})

test('clicking view order detail opens drawer and requests order detail', () => {
  assert.equal(
    viewSource.includes('查看订单明细'),
    true,
    'page should provide a view-order-detail action in the table'
  )
  assert.equal(
    viewSource.includes('orderDetailDrawerVisible.value = true'),
    true,
    'view-order-detail action should open drawer'
  )
  assert.equal(
    viewSource.includes('await loadOrderDetail(row)'),
    true,
    'view-order-detail action should trigger order-detail request'
  )
  assert.equal(
    viewSource.includes('platform: row?.platform_code'),
    true,
    'order-detail request should use row.platform_code as platform param source'
  )
  assert.equal(
    viewSource.includes('shop_id: row?.shop_id'),
    true,
    'order-detail request should use row.shop_id'
  )
  assert.equal(
    viewSource.includes('page:'),
    true,
    'order-detail request should include page'
  )
  assert.equal(
    viewSource.includes('page_size:'),
    true,
    'order-detail request should include page_size'
  )
})

test('empty states are explicit for shop-month and order-detail areas', () => {
  assert.equal(
    viewSource.includes('暂无店铺月汇总数据'),
    true,
    'shop-month empty state text should be explicit'
  )
  assert.equal(
    viewSource.includes('暂无订单明细数据'),
    true,
    'order-detail empty state text should be explicit'
  )
})

test('query payload must align to backend contract and never send shop_name', () => {
  const toOverviewPayloadBody = extractBlock(viewSource, 'const toOverviewPayload = () => ({')
  const toOrderDetailPayloadBody = extractBlock(viewSource, 'const toOrderDetailPayload = (row) => ({')

  assert.equal(
    viewSource.includes('shop_name: filters.shop_name'),
    false,
    'query payload should not include shop_name from filters'
  )
  assert.equal(
    viewSource.includes('shop_name: row?.shop_name'),
    false,
    'order-detail payload should not include row.shop_name'
  )
  assert.equal(
    viewSource.includes('const toOverviewPayload = () => ({'),
    true,
    'overview/shop-month should use dedicated payload builder'
  )
  assert.equal(
    viewSource.includes('const toOrderDetailPayload = (row) => ({'),
    true,
    'order-detail should use dedicated payload builder'
  )
  assert.equal(
    toOverviewPayloadBody.includes('page'),
    false,
    'overview payload should not contain page'
  )
  assert.equal(
    toOverviewPayloadBody.includes('page_size'),
    false,
    'overview payload should not contain page_size'
  )
  assert.equal(
    toOrderDetailPayloadBody.includes('page: orderDetailPage.value'),
    true,
    'order-detail payload should contain page'
  )
  assert.equal(
    toOrderDetailPayloadBody.includes('page_size: orderDetailPageSize.value'),
    true,
    'order-detail payload should contain page_size'
  )
  assert.equal(
    viewSource.includes('const shopMonthPage = ref('),
    false,
    'shop-month path should not retain pagination state'
  )
  assert.equal(
    viewSource.includes('const shopMonthPageSize = ref('),
    false,
    'shop-month path should not retain page_size state'
  )
  assert.equal(
    viewSource.includes('toOverviewPayload())') && !viewSource.includes('queryBCostAnalysisOverview(toOrderDetailPayload('),
    true,
    'overview call should use overview payload without page/page_size'
  )
  assert.equal(
    viewSource.includes('queryBCostAnalysisShopMonth(toOverviewPayload())'),
    true,
    'shop-month call should use overview payload without page/page_size'
  )
})

test('view uses backend field names for KPI, shop-month, and order-detail data', () => {
  assert.equal(
    viewSource.includes('total_cost_b'),
    true,
    'kpi should map total_cost_b'
  )
  assert.equal(
    viewSource.includes('warehouse_operation_fee'),
    true,
    'kpi/order detail should map warehouse_operation_fee'
  )
  assert.equal(
    viewSource.includes('platform_total_cost_itemized'),
    true,
    'kpi/order detail should map platform_total_cost_itemized'
  )
  assert.equal(
    viewSource.includes('platform_code'),
    true,
    'shop-month table should render platform_code'
  )
  assert.equal(
    viewSource.includes('shop_id'),
    true,
    'shop-month table should render shop_id'
  )
})

test('KPI section shows explicit error state when overview fails', () => {
  assert.equal(
    viewSource.includes('v-if="overviewError"'),
    true,
    'kpi section should render explicit overview error UI'
  )
})

test('kpi formatting does not coerce null/undefined to 0', () => {
  const kpiCardsBody = extractBlock(viewSource, 'const kpiCards = computed(() => {')

  assert.equal(
    viewSource.includes('Number(value ?? 0)'),
    false,
    'formatters should not coerce null/undefined to 0'
  )
  assert.equal(
    viewSource.includes("return '--'"),
    true,
    'currency formatter should show -- for missing value'
  )
  assert.equal(
    viewSource.includes("return 'N/A'"),
    true,
    'percent formatter should show N/A for missing value'
  )
  assert.equal(
    kpiCardsBody.includes('let bCostRatio = null'),
    true,
    'bCostRatio should start as null instead of 0'
  )
  assert.equal(
    kpiCardsBody.includes('totalCostBValue !== null') &&
      kpiCardsBody.includes('totalCostBValue !== undefined') &&
      kpiCardsBody.includes('gmvValue !== null') &&
      kpiCardsBody.includes('gmvValue !== undefined'),
    true,
    'bCostRatio should only compute when both total_cost_b and gmv exist'
  )
  assert.equal(
    kpiCardsBody.includes('!Number.isNaN(totalCostB) && !Number.isNaN(gmv) && gmv !== 0'),
    true,
    'bCostRatio should only compute when both values are valid numbers and gmv is non-zero'
  )
  assert.equal(
    kpiCardsBody.includes('bCostRatio = 0'),
    false,
    'bCostRatio should not fallback to 0 when data is missing'
  )
})
