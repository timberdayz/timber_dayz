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
