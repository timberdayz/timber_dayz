import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const pageSource = readFileSync(
  new URL('../src/domains/business/views/hr/ShopAssignment.vue', import.meta.url),
  'utf8'
)

test('接入全站页头 SSOT（PageHeader）', () => {
  assert.ok(
    pageSource.includes('import PageHeader from \'@/components/common/PageHeader.vue\''),
    '必须引入 PageHeader 组件'
  )
  assert.ok(pageSource.includes('<PageHeader'), '必须使用 PageHeader 组件')
  assert.ok(
    !/<h1 style=/.test(pageSource),
    '不得保留裸 <h1 style="font-size: 24px..."> 页头'
  )
  assert.ok(
    pageSource.includes('人员店铺归属和提成比'),
    '页头标题必须保留'
  )
  assert.ok(
    pageSource.includes('页面上的钱一律由后端算'),
    '「钱一律由后端算」这条口径说明不得随页头改造丢失'
  )
})

test('表格落到紧凑档', () => {
  // ⚠️ 必须用前瞻：`el-table` 是 `el-table-column` 的前缀，直接 `<el-table` 会把列也算进来
  const tables = pageSource.match(/<el-table(?=[\s>])[\s\S]{0,400}?>/g) || []
  assert.ok(tables.length >= 4, `页面应有多张表格（实际 ${tables.length} 张）`)
  const compactTables = tables.filter((table) => table.includes('erp-compact'))
  assert.equal(
    compactTables.length,
    tables.length,
    '所有表格都要声明 erp-compact，否则会退回默认密度（行高 ~50px）'
  )
})

test('成本明细压成一行摘要，完整明细进 tooltip', () => {
  assert.ok(
    pageSource.includes('cost-summary-text'),
    '成本明细列必须有一行摘要'
  )
  assert.ok(
    pageSource.includes('<el-tooltip'),
    '成本明细的完整明细必须放进 tooltip'
  )
  // 三项金额标签仍要出现（tooltip 里逐项列出）
  for (const label of ['其他经营成本', '提成前人力成本', 'A类成本']) {
    assert.ok(pageSource.includes(label), `tooltip 里必须保留「${label}」`)
  }
  // 缺少人力成本分摊的警示不得丢
  assert.ok(
    pageSource.includes('缺少人力成本分摊'),
    '「缺少人力成本分摊」警示必须保留'
  )
  assert.ok(
    pageSource.includes('共同承接店铺目标'),
    '人员标签的完整文案不得丢失（应进 tooltip）'
  )
})

test('大段内联样式已外提', () => {
  assert.ok(
    !/style="margin-bottom: 20px; display: flex/.test(pageSource),
    '操作栏的大段内联样式必须进 scoped CSS'
  )
  assert.ok(
    !pageSource.includes('style="margin-left: 10px;"'),
    '按钮间距不得再逐个写 margin-left（由 gap 统一）'
  )
  assert.ok(
    pageSource.includes('.action-bar {'),
    'scoped CSS 里必须有 .action-bar 规则'
  )
})

test('行内控件用小尺寸（与紧凑行高匹配）', () => {
  const smallCount = (pageSource.match(/size="small"/g) || []).length
  assert.ok(
    smallCount >= 5,
    `小尺寸控件偏少（当前 ${smallCount} 处），紧凑行的行高压不下来`
  )
})

test('「+ 添加人员」入口放在固定左侧的店铺列（否则按钮落在横向滚动区外）', () => {
  // 表宽 2446px > 视口 ~1268px，人员列在滚动区之外；
  // 入口原先挂在人员列 ⇒ 未横向滚动时整行看起来是空的。
  const shopColumn = pageSource.slice(
    pageSource.indexOf('<el-table-column label="店铺"'),
    pageSource.indexOf('<el-table-column label="当月销售额"')
  )
  assert.ok(
    shopColumn.includes('add-person-button'),
    '「+ 添加人员」必须在固定左侧的店铺列里'
  )
  assert.ok(
    shopColumn.includes('openAddForShop'),
    '按钮必须仍然调用 openAddForShop'
  )
  const personColumn = pageSource.slice(
    pageSource.indexOf('<el-table-column label="人员"'),
    pageSource.indexOf('<el-table-column label="提成比例"')
  )
  assert.ok(
    !personColumn.includes('openAddForShop'),
    '人员列不再承载添加入口（同一入口不出现两次）'
  )
})

test('「可分配净利润率」的输入与状态标签同行（否则整行被撑到 57px）', () => {
  // 真机实测：.allocatable-rate-wrap 是 width:100% 的 inline-flex，
  // 会把「未配置 / 待保存」标签挤到第二行 ⇒ 单元格 48px ⇒ 整行 57px。
  // 标签是必须可见的状态，不能挪进 tooltip，只能压到同一行。
  assert.ok(
    pageSource.includes('allocatable-rate-cell'),
    '必须用 .allocatable-rate-cell 把输入框与状态标签收进同一行'
  )
  assert.ok(
    /\.allocatable-rate-cell\s+\.allocatable-rate-wrap\s*\{[^}]*width:\s*auto/.test(pageSource),
    '.allocatable-rate-cell 内的输入框必须让出宽度（width:auto），否则标签仍会被挤到第二行'
  )
  assert.ok(
    /\.allocatable-rate-cell\s+\.rate-status-cell\s*\{[^}]*flex:\s*0 0 auto/.test(pageSource),
    '状态标签不可压缩 —— 「未配置 / 待保存」必须始终可见'
  )
})
