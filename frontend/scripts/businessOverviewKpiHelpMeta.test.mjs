import test from 'node:test'
import assert from 'node:assert/strict'
import { pathToFileURL } from 'node:url'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const repoRoot = resolve(import.meta.dirname, '..')
const metaModulePath = resolve(
  repoRoot,
  'src/domains/business/views/businessOverviewKpiMeta.js'
)
const viewSource = readFileSync(
  resolve(repoRoot, 'src/domains/business/views/BusinessOverview.vue'),
  'utf8'
)

test('business overview kpi help meta covers all displayed cards with stable statuses', async () => {
  const metaModule = await import(pathToFileURL(metaModulePath).href)
  const { KPI_HELP_STATUS, businessOverviewKpiMeta, getKpiHelpMeta } = metaModule

  assert.equal(typeof getKpiHelpMeta, 'function')
  assert.deepEqual(Object.keys(KPI_HELP_STATUS).sort(), ['blocked', 'observe', 'stable'])

  const expectedKeys = [
    'gmv',
    'order_count',
    'uv_conversion_rate',
    'avg_order_value',
    'impressions',
    'page_views',
    'visitor_count',
    'visit_rate',
    'browse_depth',
    'pv_conversion_rate',
    'exposure_order_rate',
    'attach_rate',
    'labor_efficiency'
  ]

  assert.deepEqual(
    businessOverviewKpiMeta.map((item) => item.key),
    expectedKeys
  )

  for (const key of expectedKeys) {
    const meta = getKpiHelpMeta(key)
    assert.ok(meta, `missing meta for ${key}`)
    assert.equal(typeof meta.definition, 'string')
    assert.equal(typeof meta.formulaText, 'string')
    assert.equal(typeof meta.businessValue, 'string')
    assert.ok(meta.formulaText.length > 0, `${key} formulaText should not be empty`)
    assert.ok(meta.businessValue.length > 0, `${key} businessValue should not be empty`)
    assert.ok(Array.isArray(meta.sourceRefs), `${key} sourceRefs should be an array`)
  }

  assert.equal(
    getKpiHelpMeta('attach_rate')?.status,
    KPI_HELP_STATUS.observe
  )
  assert.equal(
    getKpiHelpMeta('labor_efficiency')?.status,
    KPI_HELP_STATUS.blocked
  )
  assert.match(
    getKpiHelpMeta('labor_efficiency')?.caution ?? '',
    /当前不建议用于经营判断/
  )
  assert.equal(getKpiHelpMeta('missing_key'), null)
})

test('访客数(UV)必须标注两平台口径差异, 且分母用到访客数的指标标为观察口径', async () => {
  const metaModule = await import(pathToFileURL(metaModulePath).href)
  const { KPI_HELP_STATUS, getKpiHelpMeta } = metaModule

  // [*] 2026-11-10: Shopee 的「访客数」是全店去重访客人数, TikTok 的
  //   「商品访客数」是按商品统计的访客人次 —— 两者都叫 visitor_count,
  //   但**不是同一个事实** ⇒ 看板必须显式标注, 否则会被当成可比数字。
  const visitorMeta = getKpiHelpMeta('visitor_count')
  assert.equal(visitorMeta?.status, KPI_HELP_STATUS.observe)
  assert.match(visitorMeta?.caution ?? '', /Shopee/)
  assert.match(visitorMeta?.caution ?? '', /TikTok/)
  assert.match(visitorMeta?.caution ?? '', /不可直接比大小/)

  // 分母/分子用到访客数的指标同样受口径差异影响 ⇒ 都要标「观察口径」。
  for (const key of ['uv_conversion_rate', 'visit_rate', 'browse_depth']) {
    const meta = getKpiHelpMeta(key)
    assert.equal(meta?.status, KPI_HELP_STATUS.observe, `${key} 应标为观察口径`)
    assert.match(meta?.caution ?? '', /访客数/, `${key} 的说明应点明访客数口径`)
  }
})

test('流量排名表的访客数列必须带口径提示', () => {
  assert.equal(viewSource.includes('访客数(UV)'), true)
  assert.match(viewSource, /Shopee 为全店去重访客人数/)
  assert.match(viewSource, /TikTok 为商品访客人次/)
})

test('BusinessOverview renders KPI help popovers and status-driven caution content', () => {
  assert.equal(viewSource.includes('businessOverviewKpiMeta'), true)
  assert.equal(viewSource.includes('getKpiHelpMeta'), true)
  assert.equal(viewSource.includes('<el-popover'), true)
  assert.equal(viewSource.includes('trigger="hover"'), true)
  assert.equal(viewSource.includes(':teleported="false"'), false)
  assert.equal(viewSource.includes('kpi-help-popover'), true)
  assert.equal(viewSource.includes('kpi-help-trigger'), true)
  assert.equal(viewSource.includes('kpi-help-status'), true)
  assert.equal(viewSource.includes('QuestionFilled'), true)
  assert.equal(viewSource.includes('@keydown.enter.prevent'), true)
  assert.equal(viewSource.includes('@keydown.space.prevent'), true)
  assert.equal(viewSource.includes('aria-label="查看指标说明"'), true)
})
