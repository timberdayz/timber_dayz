import test from 'node:test'
import assert from 'node:assert/strict'
import { pathToFileURL } from 'node:url'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const repoRoot = resolve(import.meta.dirname, '..')
const helpModulePath = resolve(
  repoRoot,
  'src/domains/business/views/productCenterFieldHelp.js'
)
const viewSource = readFileSync(
  resolve(repoRoot, 'src/domains/business/views/ProductCenter.vue'),
  'utf8'
)
const templateSource = viewSource.slice(0, viewSource.indexOf('<script setup>'))

const REQUIRED_KEYS = [
  'spu.logistics_damage_rate',
  'spu.return_loss_rate',
  'sku.spu_binding',
  'sku.min_selling_price',
  'sku.creator_commission_rate',
  'sku.selling_price_age_days',
  'operating.free_shipping',
  'operating.min_selling_price',
  'operating.warehouse_restock',
  'operating.ad_contribution_margin_rate',
  'operating.ad_rate',
  'operating.actual_recost_completeness',
  'fee.platform',
  'fee.platform_fee_rate',
  'fee.default_creator_commission_rate',
  'fee.other_cost_rate',
  'fee.cost_rate_total'
]

test('商品中心字段说明注册表覆盖所有已接入小问号的字段，且四个分区都非空', async () => {
  const helpModule = await import(pathToFileURL(helpModulePath).href)
  const { FIELD_HELP_STATUS, getFieldHelp, toHelpSections } = helpModule

  assert.deepEqual(Object.keys(FIELD_HELP_STATUS).sort(), [
    'manual',
    'observe',
    'stable'
  ])

  for (const key of REQUIRED_KEYS) {
    const meta = getFieldHelp(key)
    assert.ok(meta, `缺少字段说明: ${key}`)
    assert.equal(typeof meta.title, 'string')
    assert.ok(meta.title.length > 0, `${key} title 不应为空`)
    for (const field of ['definition', 'formulaText', 'businessValue', 'caution']) {
      assert.equal(typeof meta[field], 'string', `${key}.${field} 应为字符串`)
      assert.ok(meta[field].length > 0, `${key}.${field} 不应为空`)
    }
    assert.ok(
      Object.values(FIELD_HELP_STATUS).includes(meta.status),
      `${key} 的 status 必须是已知状态`
    )
    assert.ok(Array.isArray(meta.sourceRefs), `${key} sourceRefs 应为数组`)

    const sections = toHelpSections(meta)
    assert.equal(sections.length, 4, `${key} 应有四个分区`)
    for (const section of sections) {
      assert.ok(section.label.length > 0)
      assert.ok(section.text.length > 0)
    }
  }

  assert.equal(getFieldHelp('not_exist_key'), null)
})

test('占位符按当前筛选条件填充，未提供时保留原样', async () => {
  const helpModule = await import(pathToFileURL(helpModulePath).href)
  const { getFieldHelp } = helpModule

  const filled = getFieldHelp('sku.min_selling_price', { platform: 'TikTok' })
  assert.match(filled.formulaText, /TikTok/)
  assert.doesNotMatch(filled.formulaText, /\{platform\}/)

  const missing = getFieldHelp('sku.min_selling_price')
  assert.match(missing.formulaText, /\{platform\}/)
})

test('人工维护的字段必须标出「不是实测值」，且表头有可见状态标签', async () => {
  const helpModule = await import(pathToFileURL(helpModulePath).href)
  const { FIELD_HELP_STATUS, getFieldHelp } = helpModule

  for (const key of [
    'spu.logistics_damage_rate',
    'spu.return_loss_rate',
    'fee.platform_fee_rate',
    'fee.default_creator_commission_rate',
    'fee.other_cost_rate'
  ]) {
    const meta = getFieldHelp(key)
    assert.equal(meta.status, FIELD_HELP_STATUS.manual, `${key} 应标为人工维护`)
    assert.match(meta.caution, /人工维护/, `${key} 应写明人工维护`)
  }

  // 表头必须有**可见**的「人工维护」标签，不能只藏在 tooltip 里
  assert.match(templateSource, /人工维护<\/el-tag/)
})

test('行内不再重复渲染同一段口径说明', () => {
  // 这些文案以前写在行模板里，每行重复一遍 ⇒ 表格被撑爆。
  // 现在只能出现在注册表（productCenterFieldHelp.js）里，不能再出现在模板里。
  const movedOutOfTemplate = [
    '行业基准件损率：这个款在行业主流数据下',
    '人工覆盖按平台生效，各平台底线互相独立',
    '买家付尾程运费，尾程不计入底线',
    '不同平台底线不同',
    'currentWarehouseLabel(row)'
  ]
  for (const snippet of movedOutOfTemplate) {
    assert.equal(
      templateSource.includes(snippet),
      false,
      `模板里不应再出现重复说明: ${snippet}`
    )
  }

  const helpModuleSource = readFileSync(helpModulePath, 'utf8')
  assert.match(helpModuleSource, /发 100 件里坏几件/)
  assert.match(helpModuleSource, /发 100 件里退几件/)
})

test('小问号组件已接入表头与抽屉表单', () => {
  assert.equal(viewSource.includes('FieldHelpTip'), true)
  assert.equal(viewSource.includes('@/components/common/FieldHelpTip.vue'), true)
  assert.equal(viewSource.includes('productCenterFieldHelp'), true)
  assert.match(templateSource, /<FieldHelpTip/)
  assert.match(templateSource, /class="pc-col-head"/)
  assert.match(templateSource, /class="pc-field-label"/)
})

test('行相关的告警必须仍然可见，不得被挪进 tooltip', () => {
  const mustStayVisible = [
    'fulfillmentNotCountedHint(row)',
    'stale-hint',
    'roi-guard-hint',
    'deliveryCostHint(row)',
    'creatorCommissionHint(row)',
    'platformRateMissingHint(row)',
    'adCostMissingHint(row)',
    'warehouse-divergence-hint',
    'isBelowFloor(row)',
    'deliveryTierDuplicateHint(row)'
  ]
  for (const snippet of mustStayVisible) {
    assert.equal(
      templateSource.includes(snippet),
      true,
      `行内告警不得隐藏: ${snippet}`
    )
  }
})

test('表格紧凑度统一：单元格内边距收窄，且三张表不再各写各的', () => {
  assert.match(viewSource, /\.flat-table :deep\(\.el-table__cell\)\s*\{[^}]*padding: 5px 0/)
  assert.match(viewSource, /\.flat-table :deep\(\.cell\)\s*\{[^}]*padding: 0 8px/)
  // SKU 表原来的单独覆盖要去掉，避免三张表内边距不一致
  assert.equal(viewSource.includes('.sku-table :deep(.el-table__cell)'), false)
})

test('列宽收窄到位：说明文字移走后不再给这些列留宽', () => {
  const expectations = [
    // SPU 管理：两率列从 180 收到 165（表头要放得下「标签 + 人工维护标签 + 问号」）
    ['运输货损率', 'width="165"'],
    ['退货损失率', 'width="165"'],
    // SKU 资料：基准售价 260 → 180、最低售价 340 → 320
    ['基准售价', 'width="180"'],
    ['最低售价', 'width="320"'],
    // 利润测算：跨仓提示 280 → 190、广告分成率 225 → 185
    ['跨仓提示', 'width="190"'],
    ['广告分成率', 'width="185"']
  ]
  for (const [label, width] of expectations) {
    const pattern = new RegExp(`label="${label}"\\s+${width}`)
    assert.match(viewSource, pattern, `${label} 应为 ${width}`)
  }
})

test('最低售价列的人工覆盖编辑区默认收起，行高不再被顶到 190px', () => {
  // 常态只有「平台名 + 生效金额 + 来源 + 调整」一行；点「调整」才展开输入框与「保存覆盖」。
  assert.match(templateSource, /isOverrideEditing\(row, item\)/)
  assert.match(templateSource, /toggleOverrideEditing\(row, item\)/)
  assert.match(templateSource, />调整</)
  assert.match(templateSource, />收起</)
  // 展开状态不能挂在 row 上（row 重新拉取后会被整体替换）
  assert.match(viewSource, /const pricingOverrideEditing = reactive\(\{\}\)/)
  assert.match(viewSource, /closeOverrideEditing\(row, item\)/)
})

test('采购成本确认时间显示到分钟，不再把 ISO 串整段塞进单元格', () => {
  assert.match(
    templateSource,
    /formatConfirmedAt\(row\.purchase_cost_confirmed_at\)/
  )
  assert.equal(
    templateSource.includes('{{ row.purchase_cost_confirmed_at || "-" }}'),
    false
  )
})

test('SPU 管理表只有商品名称保留 min-width，避免剩余宽度被平摊到编码列', () => {
  const spuTab = templateSource.slice(
    templateSource.indexOf('name="spu"'),
    templateSource.indexOf('name="sku"')
  )
  const minWidthColumns = spuTab.match(/min-width="\d+"/g) || []
  assert.equal(
    minWidthColumns.length,
    1,
    `SPU 表应只有一列保留 min-width，实际: ${minWidthColumns.join(', ')}`
  )
  assert.match(spuTab, /label="商品名称" min-width="240"/)
})

test('SKU 资料页的 SPU 单元格默认只读，点「换款」才展开编辑', () => {
  // 存量行：只读编码 + 「换款」入口；编辑态：下拉 + 收起/取消
  assert.match(templateSource, /isSpuSwitchEditing\(row\)/)
  assert.match(templateSource, /startSpuEdit\(row\)/)
  assert.match(templateSource, /cancelSpuEdit\(row\)/)
  // 「换款」入口必须**看得见**，不能只做成 hover 才出现的动作
  assert.match(templateSource, />换款</)
  // 表头问号：归属口径说明（换款规则、归档、生效日）
  assert.match(templateSource, /:sections="skuSpuBindingHelp"/)
  // 编辑态 / 原值快照不能挂在 row 上（row 重新拉取后会被整体替换）
  assert.match(viewSource, /const spuSwitchEditing = reactive\(\{\}\)/)
  assert.match(viewSource, /const spuSwitchOriginals = reactive\(\{\}\)/)
  assert.match(viewSource, /resetSpuSwitchState\(\)/)
})

test('换款的「待保存」必须行内可见，不得藏进 tooltip', () => {
  assert.match(templateSource, /待保存/)
  assert.match(templateSource, /spu-binding-pending/)
  // 换款没保存之前，旧的生效日不能继续显示（会让人以为新归属已生效）
  assert.match(templateSource, /spuSwitchPending\(row\)/)
})

test('换款后新归属按保存当日生效；改回原值要恢复原生效日', () => {
  // 后端 effective_from 为空 ⇒ 归属从保存当日起算，所以文案不能写死日期
  assert.match(templateSource, /保存当日生效/)
  assert.equal(/保存后自 \d{4}-\d{2}-\d{2}/.test(templateSource), false)
  // 改回原值 ⇒ 撤销本次换款 ⇒ 原生效日恢复
  assert.match(viewSource, /row\.spu_effective_from = original\.spu_effective_from/)
})

test('取消换款只清换款标记，不清整行的其它改动', () => {
  // dirtyRows 是整行粒度的 ⇒ 取消换款不能把这一行其它字段的改动一起清掉
  assert.match(viewSource, /spuSwitchDirty\.value\.delete\(key\)/)
  const cancelBody = viewSource.slice(
    viewSource.indexOf('const cancelSpuEdit = (row) =>'),
    viewSource.indexOf('const cancelSpuEdit = (row) =>') + 700
  )
  assert.equal(
    /dirtyRows\.value\.delete/.test(cancelBody),
    false,
    '取消换款不得清掉整行的 dirty 标记'
  )
})

test('存量行的 SPU 下拉不给 clearable：后端不支持解绑', () => {
  assert.match(templateSource, /:clearable="row\.__new"/)
})
