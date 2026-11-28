import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const pageSource = readFileSync(
  new URL('../src/domains/business/views/finance/ExpenseManagement.vue', import.meta.url),
  'utf8'
)

test('首屏先等店铺列表就绪再加载月度费用', () => {
  assert.ok(pageSource.includes('await loadShops()'), 'onMounted 必须 await loadShops()')
  assert.ok(
    !/onMounted\([\s\S]{0,400}loadShops\(\)\s*\n\s*loadMonthlyExpenses/.test(pageSource),
    '不得在 loadShops() 未完成时直接加载月度费用'
  )
})

test('店铺集合拆成全部与在营两组', () => {
  assert.ok(pageSource.includes('splitShopsByAvailability'))
  assert.ok(pageSource.includes('operatingShops'))
  assert.ok(pageSource.includes('allShops'))
})

test('月度表格支持平台分段与租户维度', () => {
  assert.ok(pageSource.includes('platformScope'))
  assert.ok(pageSource.includes('main_account_id'))
  assert.ok(pageSource.includes('租户'))
})

test('已停用店铺有明确标注', () => {
  assert.ok(pageSource.includes('已停用'))
  assert.ok(pageSource.includes('shop_enabled'))
})

test('快速拆分使用 view-model 的范围解析', () => {
  assert.ok(pageSource.includes('resolveQuickSplitTargets'))
  assert.ok(pageSource.includes('countSplitTargets'))
})

test('快速拆分提供范围选择且只覆盖目标集合', () => {
  assert.ok(pageSource.includes('quickSplitScope'))
  assert.ok(pageSource.includes('仅 Shopee'))
  assert.ok(pageSource.includes('仅 TikTok'))
  assert.ok(pageSource.includes('按租户'))
  assert.ok(
    pageSource.includes('resolveQuickSplitTargets'),
    '必须用 view-model 解析目标集合'
  )
})

test('按店铺视图默认选店且有空状态提示', () => {
  assert.ok(pageSource.includes('el-empty'))
  assert.ok(pageSource.includes('请先选择店铺'))
  assert.ok(pageSource.includes('暂无费用记录'))
  assert.ok(pageSource.includes('handleShopSelectChange'))
})

// ---------------------------------------------------------------------------
// 以下是**防回归**断言：它们守的是「一旦回退就会出错」的具体约束，
// 而不只是「某个字符串还在不在」。
// ---------------------------------------------------------------------------

test('旧口径残留不得复活：availableShops / 本地同名函数', () => {
  // availableShops 是被 allShops + operatingShops 取代的旧集合名，
  // 一旦复活就会丢掉「在营 vs 全部」的区别（停用店会重新拿到空白行）。
  assert.ok(
    !pageSource.includes('availableShops'),
    'availableShops 已被 allShops/operatingShops 取代，不得残留'
  )
  // view-model 已经导出同名函数，组件里再声明一次会造成重复声明，构建直接失败。
  assert.ok(
    !/const buildExpenseRowKey\s*=/.test(pageSource),
    'buildExpenseRowKey 必须来自 @/utils/expenseViewModel.js，组件内不得重复声明'
  )
  assert.ok(
    !/const distributeEvenly\s*=/.test(pageSource),
    'distributeEvenly 必须来自 @/utils/expenseViewModel.js，组件内不得重复声明'
  )
})

test('年度店铺记录集合必须在早退之前刷新（否则停用店进不了下拉）', () => {
  const loadShopExpenses = pageSource.slice(
    pageSource.indexOf('const loadShopExpenses = async () => {')
  )
  const refreshAt = loadShopExpenses.indexOf('await loadShopViewRecordedShops(')
  const earlyReturnAt = loadShopExpenses.indexOf('if (!selectedShopId.value)')

  assert.ok(refreshAt >= 0, 'loadShopExpenses 必须刷新年度有记录的店铺集合')
  assert.ok(earlyReturnAt >= 0, 'loadShopExpenses 必须保留未选店铺的早退分支')
  assert.ok(
    refreshAt < earlyReturnAt,
    '年度记录集合必须在早退分支之前刷新，否则停用店永远进不了下拉（鸡生蛋死循环）'
  )
})

test('拆分店铺数与实际分摊必须同源', () => {
  assert.ok(
    pageSource.includes('countSplitTargets(visibleMonthlyRows'),
    '界面计数必须读可见行 + 同一个 scope'
  )
  assert.ok(
    pageSource.includes('resolveQuickSplitTargets(visibleMonthlyRows'),
    '实际分摊目标必须读可见行 + 同一个 scope'
  )
})

test('停用店铺不参与分摊：分摊集合口径由 view-model 保证', () => {
  // 组件不得自己再实现一套「在营」判定，否则两套口径会漂移。
  const applySplit = pageSource.slice(
    pageSource.indexOf('const handleApplyQuickSplit = async () => {')
  )
  assert.ok(
    applySplit.includes('resolveQuickSplitTargets'),
    '快速拆分必须走 view-model 的目标集合解析'
  )
  assert.ok(
    !/enabled\s*===\s*true[\s\S]{0,200}\.(filter|forEach)\(/.test(applySplit),
    '不得在拆分里另写一套启用状态过滤'
  )
})

test('月度表格数据源必须是分段过滤后的行', () => {
  assert.ok(
    pageSource.includes(':data="visibleMonthlyRows"'),
    '月度表格必须渲染 visibleMonthlyRows，否则平台分段完全不生效'
  )
})

test('空白行只由在营店铺生成', () => {
  assert.ok(
    /const newRows = operatingShops\.value/.test(pageSource),
    '空白行源必须是 operatingShops（在营店）；用 allShops 会让停用店重新拿到空白行'
  )
})

test('删除行必须按行对象定位，不能用过滤后下标', () => {
  // 表格数据源是 visibleMonthlyRows（分段过滤后），$index 是过滤后下标，
  // 拿它去 splice 全量数据会删错行。
  assert.ok(
    pageSource.includes('monthlyTableData.value.indexOf(row)'),
    '删除行必须按行对象在全量数据中定位'
  )
})

// ---------------------------------------------------------------------------
// 紧凑密度 + 用户侧备注字段退役
// ---------------------------------------------------------------------------

// 取某个组件的开始标签（含属性），例如 <el-input-number ... />
const openTagBlocks = (tag) =>
  pageSource.match(new RegExp(`<${tag}(?=[\\s/>])[\\s\\S]*?>`, 'g')) || []

// 取承载某个数据源的 el-table 开始标签
const tableOpenTag = (dataAttr) => {
  const idx = pageSource.indexOf(dataAttr)
  assert.ok(idx >= 0, `页面里找不到 ${dataAttr}`)
  const start = pageSource.lastIndexOf('<el-table', idx)
  const end = pageSource.indexOf('>', idx)
  return pageSource.slice(start, end)
}

test('两张录入表都进入紧凑档（erp-compact）', () => {
  const monthlyTag = tableOpenTag(':data="visibleMonthlyRows"')
  assert.ok(monthlyTag.includes('erp-compact'), '月度表必须声明 erp-compact')

  const shopTag = tableOpenTag(':data="shopTableData"')
  assert.ok(shopTag.includes('erp-compact'), '按店铺表必须声明 erp-compact')

  // ⚠️ 密度 SSOT 的选择器是后代选择器 `.erp-compact .el-table`，
  //    而 Element Plus 的 el-table 根节点**就是** .el-table 本身 ——
  //    class 只挂在表格根节点上不会命中任何规则（实测行高 42px，不是 34px）。
  //    ⇒ 祖先容器也必须声明 erp-compact，否则紧凑档整体失效。
  const compactAncestors = pageSource.match(/<el-card class="erp-compact">/g) || []
  assert.ok(
    compactAncestors.length >= 2,
    '两张表的祖先容器都必须带 erp-compact，否则紧凑档不生效'
  )
})

test('用户侧备注字段已退役：页面不再有备注列与 note 绑定', () => {
  assert.ok(!pageSource.includes('label="备注"'), '不得再出现「备注」列标题')
  assert.ok(!pageSource.includes('prop="note"'), '不得再有 prop="note" 的列')
  assert.ok(!pageSource.includes('v-model="row.note"'), '不得再绑定 row.note')
  assert.ok(!pageSource.includes('备注'), '页面上不得再出现「备注」字样')
})

test('保存 payload 不再提交 note（remark 归后端系统所有）', () => {
  const payloads = pageSource.match(/const payload = \{[\s\S]*?^\s*\}/gm) || []
  assert.equal(payloads.length, 3, '应有三处保存 payload（单行 / 批量 / 按店铺行）')
  payloads.forEach((block, index) => {
    assert.ok(!/\bnote\b/.test(block), `第 ${index + 1} 处 payload 不得再带 note 字段`)
  })
})

test('isMeaningfulExpenseRow 只看六项金额', () => {
  const start = pageSource.indexOf('const isMeaningfulExpenseRow')
  const end = pageSource.indexOf('const laborCostForPayload')
  assert.ok(start >= 0 && end > start, '必须保留 isMeaningfulExpenseRow')
  const fn = pageSource.slice(start, end)
  assert.ok(!fn.includes('note'), '不得再引用 note')
  assert.ok(!fn.includes('attachments'), '不得再引用 attachments')
  ;['rent', 'marketing_fee', 'utilities', 'ai_token_cost', 'labor_cost', 'other_costs'].forEach(
    (field) => {
      assert.ok(fn.includes(`row.${field}`), `必须保留 ${field} 的判定`)
    }
  )
})

test('统计指标条不再用栅格卡片', () => {
  assert.ok(!pageSource.includes(':span="4"'), '不得再有栅格列宽（:span）')
  assert.ok(!pageSource.includes('<el-row'), '不得再用 el-row 栅格')
  assert.ok(!pageSource.includes('<el-col'), '不得再用 el-col 栅格')

  const firstBar = pageSource.indexOf('class="stat-metrics erp-mb-md"')
  assert.ok(firstBar >= 0, '必须存在指标条容器')
  const monthlyBar = pageSource.slice(firstBar, pageSource.indexOf('<!-- 月度费用表格 -->'))
  assert.ok(!monthlyBar.includes('<el-card'), '月度指标条不得再用卡片')

  const secondBar = pageSource.indexOf('class="stat-metrics erp-mb-md"', firstBar + 1)
  assert.ok(secondBar > firstBar, '按店铺视图也必须有指标条')
  const shopBar = pageSource.slice(secondBar, pageSource.indexOf('<!-- 店铺费用表格'))
  assert.ok(!shopBar.includes('<el-card'), '按店铺指标条不得再用卡片')

  // 指标条容器：flex + 可换行 + 8px 间隙（7 个指标等宽铺满一行）
  assert.ok(/\.stat-metrics\s*\{[^}]*display:\s*flex/.test(pageSource), '指标条必须是 flex 容器')
  assert.ok(
    /\.stat-metrics\s*\{[^}]*flex-wrap:\s*wrap/.test(pageSource),
    '指标条必须允许换行'
  )
  assert.ok(/\.stat-metrics\s*\{[^}]*gap:\s*8px/.test(pageSource), '指标条间隙应为 8px')

  const metricCount = (monthlyBar.match(/class="stat-metric[ "]/g) || []).length
  assert.equal(metricCount, 7, '月度指标条必须有 7 个指标（原来第 7 个会换行）')
})

test('行内控件统一 small 尺寸', () => {
  const inputNumbers = openTagBlocks('el-input-number')
  assert.ok(inputNumbers.length >= 15, `el-input-number 至少 15 处，实际 ${inputNumbers.length}`)
  inputNumbers.forEach((tag, index) => {
    assert.ok(tag.includes('size="small"'), `第 ${index + 1} 处 el-input-number 必须 size="small"`)
  })

  const selects = openTagBlocks('el-select')
  assert.ok(selects.length >= 4, `el-select 至少 4 处，实际 ${selects.length}`)
  selects.forEach((tag, index) => {
    assert.ok(tag.includes('size="small"'), `第 ${index + 1} 处 el-select 必须 size="small"`)
  })

  const tags = openTagBlocks('el-tag')
  tags.forEach((tag, index) => {
    assert.ok(tag.includes('size="small"'), `第 ${index + 1} 处 el-tag 必须 size="small"`)
  })

  const smallCount = (pageSource.match(/size="small"/g) || []).length
  assert.ok(smallCount >= 15, `size="small" 至少 15 处，实际 ${smallCount}`)
})

test('店铺列压成一行：下拉 + 租户 + 状态标签横排', () => {
  assert.ok(pageSource.includes('class="shop-cell-main"'), '店铺列必须有横排容器')
  assert.ok(
    /\.shop-cell-main\s*\{[^}]*display:\s*flex[^}]*align-items:\s*center[^}]*gap:\s*6px/.test(
      pageSource
    ),
    '横排容器必须是 flex + 居中 + 6px 间隙'
  )
  assert.ok(
    /\.shop-cell-tenant\s*\{[^}]*white-space:\s*nowrap[^}]*overflow:\s*hidden[^}]*text-overflow:\s*ellipsis/.test(
      pageSource
    ),
    '租户文字必须单行省略'
  )
  // 口径不变：租户副标题仍在
  assert.ok(pageSource.includes('租户：'), '租户信息不能丢')
  // 孤儿行的原始店铺 ID 不能丢
  assert.ok(pageSource.includes('原始店铺ID'), '孤儿行的原始店铺ID 不能丢')
})

test('两张表的列宽收紧（横向不留大片空白）', () => {
  const tableBlock = (dataAttr) => {
    const idx = pageSource.indexOf(dataAttr)
    assert.ok(idx >= 0, `页面里找不到 ${dataAttr}`)
    const start = pageSource.lastIndexOf('<el-table', idx)
    const end = pageSource.indexOf('</el-table>', start)
    return pageSource.slice(start, end)
  }
  const widthsOf = (source) =>
    [...source.matchAll(/width="(\d+)"/g)].map((match) => Number(match[1]))

  const monthlyWidths = widthsOf(tableBlock(':data="visibleMonthlyRows"'))
  const shopWidths = widthsOf(tableBlock(':data="shopTableData"'))

  assert.ok(monthlyWidths.length >= 10, '月度表应当有 10 列')
  assert.ok(shopWidths.length >= 10, '按店铺表应当有 10 列')

  const monthlyTotal = monthlyWidths.reduce((sum, width) => sum + width, 0)
  const shopTotal = shopWidths.reduce((sum, width) => sum + width, 0)
  // 备注列（min-width 220）退役后总宽必须明显收窄
  assert.ok(monthlyTotal <= 1400, `月度表总列宽应 ≤1400，实际 ${monthlyTotal}`)
  assert.ok(shopTotal <= 1200, `按店铺表总列宽应 ≤1200，实际 ${shopTotal}`)
  assert.ok(
    Math.max(...monthlyWidths) <= 240,
    `月度表最宽列应 ≤240，实际 ${Math.max(...monthlyWidths)}`
  )
  assert.ok(
    Math.max(...shopWidths) <= 160,
    `按店铺表最宽列应 ≤160，实际 ${Math.max(...shopWidths)}`
  )
  assert.ok(monthlyWidths.includes(150), '月度表操作列应收紧到 150')
  assert.ok(shopWidths.includes(150), '按店铺表操作列应收紧到 150')
})
