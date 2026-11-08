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

test('访客数(UV)必须写明两平台口径基本一致可横向比较, 且用到访客数的指标标为观察口径', async () => {
  const metaModule = await import(pathToFileURL(metaModulePath).href)
  const { KPI_HELP_STATUS, getKpiHelpMeta } = metaModule

  // [*] 2026-11-10 复核后回正(实测, 开发库):
  //   * 两平台月报都是「一店一天一行」(shopee 2354 行 = 2354 个店×日;
  //     tiktok 1374 行 = 45 个店×月 桶, 每桶整月 28~31 天);
  //   * shopee「访客数」= 新访客 + 现有访客, 2354/2354 行**精确相等**
  //     ⇒ 可证明是去重访客人数;
  //   * tiktok「商品访客数」≤ 该行「去重商品曝光次数」0/1374 行违反
  //     ⇒ 同样是访客量(不是人次, 也不是曝光)。
  //   ⇒ 两边都是「店铺当天的访客数」, 口径基本一致, **可以横向比较**。
  //   之前写的「跨平台不可直接比大小」是**基于推测的错结论**, 已回正。
  //   仍未定的一点点: tiktok 列名定义为「当天访问过商品的访客」,
  //   是否等于店铺全部访客 ⇒ 待确认(所以也不能写成「完全等价」)。
  const visitorMeta = getKpiHelpMeta('visitor_count')
  assert.equal(visitorMeta?.status, KPI_HELP_STATUS.observe)
  assert.match(visitorMeta?.caution ?? '', /口径基本一致/)
  assert.match(visitorMeta?.caution ?? '', /可横向比较/)
  assert.match(visitorMeta?.caution ?? '', /待确认/)
  // 错结论不得复活
  assert.doesNotMatch(visitorMeta?.caution ?? '', /不可直接比大小/)
  assert.doesNotMatch(visitorMeta?.caution ?? '', /口径不同/)
  assert.doesNotMatch(visitorMeta?.definition ?? '', /访客人次/)

  // 分母/分子用到访客数的指标同样受「待确认项」影响 ⇒ 都要标「观察口径」。
  for (const key of ['uv_conversion_rate', 'visit_rate', 'browse_depth']) {
    const meta = getKpiHelpMeta(key)
    assert.equal(meta?.status, KPI_HELP_STATUS.observe, `${key} 应标为观察口径`)
    assert.match(meta?.caution ?? '', /访客数/, `${key} 的说明应点明访客数口径`)
    assert.match(meta?.caution ?? '', /口径基本一致/, `${key} 应写明口径基本一致`)
    assert.doesNotMatch(
      meta?.caution ?? '',
      /不可直接横向比较/,
      `${key} 不得保留已回正的错结论`
    )
  }
})

test('流量排名表的访客数列必须带口径提示', () => {
  assert.equal(viewSource.includes('访客数(UV)'), true)
  assert.match(viewSource, /两平台都是「店铺当天的访客数」/)
  assert.match(viewSource, /口径基本一致/)
  assert.doesNotMatch(viewSource, /不可直接比大小/)
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
