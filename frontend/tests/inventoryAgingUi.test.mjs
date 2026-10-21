import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const repoRoot = resolve(import.meta.dirname, '..')
const apiSource = readFileSync(resolve(repoRoot, 'src/api/inventoryDomain.js'), 'utf8')
const viewSource = readFileSync(
  resolve(repoRoot, 'src/domains/business/views/inventory/InventoryAging.vue'),
  'utf8',
)

test('库龄看板页新增滞销清单页签', () => {
  assert.match(viewSource, /<el-tabs v-model="activeTab"/)
  assert.match(viewSource, /<el-tab-pane label="滞销清单" name="clearance">/)
  assert.match(viewSource, /<el-tab-pane label="库龄明细" name="aging">/)
  assert.match(viewSource, /@tab-change="handleTabChange"/)
})

test('滞销清单前端 API 封装指向专用端点', () => {
  assert.match(
    apiSource,
    /async getClearanceRanking\s*\(\s*params\s*=\s*\{\s*\}\s*\)\s*\{[\s\S]*?_get\('\/inventory\/clearance-ranking',\s*\{\s*params\s*\}\s*\)/,
  )
  assert.match(viewSource, /inventoryDomainApi\.getClearanceRanking\(/)
})

test('滞销清单明细表列齐全', () => {
  assert.match(viewSource, /prop="clearance_priority_score" label="优先级"/)
  assert.match(viewSource, /prop="product_sku" label="SKU"/)
  assert.match(viewSource, /prop="product_name" label="商品名"/)
  assert.match(viewSource, /label="库龄"[\s\S]{0,200}?row\.age_days/)
  assert.match(viewSource, /label="起算日"[\s\S]{0,200}?row\.age_anchor_date/)
  assert.match(viewSource, /label="重置原因"/)
  assert.match(viewSource, /prop="current_qty" label="可用库存"/)
  assert.match(viewSource, /label="库存金额"[\s\S]{0,200}?row\.inventory_value/)
  assert.match(viewSource, /label="周转天数"[\s\S]{0,200}?row\.estimated_turnover_days/)
  assert.match(viewSource, /label="日均销量"[\s\S]{0,200}?row\.daily_avg_sales/)
  assert.match(viewSource, /label="风险"[\s\S]{0,200}?row\.risk_level/)
  assert.match(viewSource, /label="档位"[\s\S]{0,200}?row\.pricing_tier_label/)
  assert.match(viewSource, /label="当前可优惠"[\s\S]{0,200}?row\.current_discount_rate/)
  assert.match(viewSource, /label="最低售价"[\s\S]{0,300}?row\.min_selling_price/)
  assert.match(viewSource, /label="清货回款"[\s\S]{0,400}?row\.clearance_recovery_amount/)
})

test('清货回款缺失时显示缺参考售价而不是占位符', () => {
  assert.match(
    viewSource,
    /row\.clearance_recovery_amount === null[\s\S]{0,300}?缺参考售价/,
  )
  assert.match(
    viewSource,
    /v-else>\{\{ formatMoney\(row\.clearance_recovery_amount\) \}\}/,
  )
  assert.match(viewSource, /class="missing-price-hint"/)
})

test('缺参考售价的 SKU 数量在界面上有明确提示', () => {
  assert.match(viewSource, /clearanceSummary\.missing_reference_price_count > 0/)
  assert.match(viewSource, /个 SKU 缺参考售价，无法计算清货回款/)
})

test('滞销清单汇总卡覆盖 SKU 数 压资金额 在库数量 高风险数', () => {
  assert.match(viewSource, /title="滞销 SKU 数"/)
  assert.match(viewSource, /title="压资金额"/)
  assert.match(viewSource, /title="在库数量"/)
  assert.match(viewSource, /title="高风险数"/)
  assert.match(viewSource, /clearanceSummary\.by_risk_level \|\| \{\}\)\.high/)
})

test('风险分布与库龄档位分布来自汇总数据', () => {
  assert.match(viewSource, /const clearanceRiskDistribution = computed/)
  assert.match(viewSource, /const clearanceBucketDistribution = computed/)
  assert.match(viewSource, /clearanceSummary\.by_risk_level/)
  assert.match(viewSource, /clearanceSummary\.by_age_bucket/)
  assert.match(viewSource, /<template #header>风险分布<\/template>/)
  assert.match(viewSource, /<template #header>库龄档位分布<\/template>/)
})

test('滞销清单筛选参数真的传给后端', () => {
  assert.match(viewSource, /min_age_days: clearanceFilters\.min_age_days/)
  assert.match(viewSource, /max_age_days: clearanceFilters\.max_age_days \?\? undefined/)
  assert.match(viewSource, /risk_level: clearanceFilters\.risk_level \|\| undefined/)
  assert.match(viewSource, /platform_code: clearanceFilters\.platform_code \|\| undefined/)
  assert.match(viewSource, /keyword: clearanceFilters\.keyword \|\| undefined/)
  assert.match(viewSource, /sort_by: clearanceFilters\.sort_by/)
  assert.match(viewSource, /sort_order: clearanceFilters\.sort_order/)
  assert.match(viewSource, /limit: clearancePage\.limit/)
  assert.match(viewSource, /offset: clearancePage\.offset/)
})

test('库龄下限默认取 0 避免单帧数据白屏', () => {
  assert.match(viewSource, /const clearanceFilters = reactive\(\{[\s\S]{0,200}?min_age_days: 0/)
  assert.match(
    viewSource,
    /resetClearanceFilters[\s\S]{0,400}?min_age_days: 0/,
  )
})

test('滞销清单支持按后端白名单字段排序', () => {
  assert.match(viewSource, /value="clearance_priority_score"/)
  assert.match(viewSource, /value="age_days"/)
  assert.match(viewSource, /value="inventory_value"/)
  assert.match(viewSource, /value="estimated_turnover_days"/)
  assert.match(viewSource, /value="high"/)
  assert.match(viewSource, /value="medium"/)
  assert.match(viewSource, /value="low"/)
})

test('滞销清单分页按 offset 传给后端', () => {
  assert.match(viewSource, /<el-pagination[\s\S]{0,400}?v-model:current-page="clearanceCurrentPage"/)
  assert.match(viewSource, /:total="clearanceTotal"/)
  assert.match(
    viewSource,
    /const handleClearancePageChange[\s\S]{0,200}?clearancePage\.offset = \(page - 1\) \* clearancePageSize\.value/,
  )
})

test('reset_reason 五个取值全部中文化', () => {
  assert.match(viewSource, /case 'first_positive':\s*return '首次有货'/)
  assert.match(viewSource, /case 'stock_increase':\s*return '补货归零'/)
  assert.match(viewSource, /case 'reappeared_after_zero':\s*return '卖空重现'/)
  assert.match(viewSource, /case 'zero_stock':\s*return '库存归零'/)
  assert.match(viewSource, /case 'continued':\s*return '持续累加'/)
})

test('未匹配 ERP 主数据的 SKU 在清单里标出来', () => {
  assert.match(viewSource, /v-if="!row\.pricing_matched_erp"/)
  assert.match(viewSource, />未匹配主数据</)
})

test('周转哨兵值与最低售价来源都有可读展示', () => {
  assert.match(viewSource, /const formatTurnoverDays[\s\S]{0,400}?return '无动销'/)
  assert.match(viewSource, /row\.min_selling_price_source/)
  assert.match(viewSource, /const minSellingPriceSourceLabel/)
  assert.match(viewSource, /case 'cost_floor':\s*return '成本底线'/)
  assert.match(viewSource, /case 'discount_guard':\s*return '折扣护栏'/)
})

test('原有库龄明细页签功能未变', () => {
  assert.match(viewSource, /inventoryDomainApi\.getAging\(/)
  assert.match(viewSource, /inventoryDomainApi\.getAgingBuckets\(/)
  assert.match(viewSource, /inventoryDomainApi\.getAgingHistory\(/)
  assert.match(viewSource, /const openHistory = async/)
  assert.match(viewSource, /<template #header>库龄分布<\/template>/)
  assert.match(viewSource, /<template #header>SKU 连续库龄明细<\/template>/)
  assert.match(viewSource, /onMounted\(reload\)/)
  assert.match(viewSource, /const resetFilters = \(\) =>/)
})
