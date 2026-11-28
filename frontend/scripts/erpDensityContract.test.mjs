import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const read = (relativePath) =>
  readFileSync(new URL(`../${relativePath}`, import.meta.url), 'utf8')

const layoutCss = read('src/assets/erp-layout.css')
const densityCss = read('src/assets/erp-density.css')
const mainJs = read('src/main.js')
const expensePage = read('src/domains/business/views/finance/ExpenseManagement.vue')
const assignmentPage = read('src/domains/business/views/hr/ShopAssignment.vue')

// ---------------------------------------------------------------------------
// 密度规范本身
// ---------------------------------------------------------------------------

test('三档密度都在 erp-density.css 里定义', () => {
  for (const level of ['erp-compact', 'erp-comfortable', 'erp-spacious']) {
    assert.ok(
      densityCss.includes(`.${level}`),
      `密度档 ${level} 必须在 erp-density.css 里定义`
    )
  }
})

test('密度文件必须被入口真正引入（否则规范进不了浏览器）', () => {
  // 2026-11-28 真机复核发现：密度规则寄居在 erp-layout.css，而那个文件从未被
  // 任何入口 import ⇒ .erp-compact 只是一枚类名，td padding 仍是默认 8px、
  // 行高 41px，静态断言却全绿。⇒ 必须断言「文件被引入」。
  assert.ok(
    mainJs.includes('import \'./assets/erp-density.css\''),
    'main.js 必须 import 密度文件，否则紧凑档不会生效'
  )
})

test('密度规则只有一份出处（erp-layout.css 不再另存一份）', () => {
  assert.ok(
    !/\.erp-compact\s*\.el-table\s*\{/.test(layoutCss),
    'erp-layout.css 不得再保存密度规则副本，避免与 erp-density.css 双份漂移'
  )
  assert.ok(
    layoutCss.includes('erp-density.css'),
    'erp-layout.css 应留下指向密度唯一出处的说明'
  )
})

test('密度档同时支持「祖先声明」与「表格自身声明」两种写法', () => {
  // Element Plus 的 el-table 根节点就是 .el-table 本身：
  // 只写后代选择器时，把类挂在表格根节点上一条规则都命中不了（实测行高 41px）。
  assert.ok(
    densityCss.includes('.erp-compact.el-table'),
    '紧凑档必须支持把 erp-compact 直接挂在 el-table 根节点上'
  )
  assert.ok(
    densityCss.includes('.erp-compact .el-table'),
    '紧凑档必须支持把 erp-compact 挂在祖先容器上'
  )
})

test('宽松档的选择器没有把 th 写成 comfortable', () => {
  // 2026-11-28 修：原文 `.erp-spacious .el-table td, .erp-comfortable .el-table th`
  // 让「宽松档的表头」永远不生效（宽松档只改了 td，th 落在舒适档规则上）。
  // 锚点用真实规则选择器，别用类名（文件头注释里也提到了类名）。
  const spaciousBlock = densityCss.slice(densityCss.indexOf('.erp-spacious .el-table'))
  assert.ok(
    !spaciousBlock.includes('.erp-comfortable .el-table th'),
    '宽松档的表头选择器不得指向舒适档'
  )
  assert.ok(
    spaciousBlock.includes('.erp-spacious .el-table th'),
    '宽松档必须同时收紧表头与表体'
  )
})

test('紧凑档给出可量化的密度指标', () => {
  const compactBlock = densityCss.slice(
    densityCss.indexOf('.erp-compact .el-table'),
    densityCss.indexOf('.erp-comfortable .el-table')
  )
  assert.ok(
    compactBlock.includes('padding: 4px 0'),
    '紧凑档必须把单元格上下内边距压到 4px（否则行高下不来）'
  )
  assert.ok(
    compactBlock.includes('font-size: 13px'),
    '紧凑档必须给出明确字号（13px 是密而不糊的下限）'
  )
})

// ---------------------------------------------------------------------------
// 规范必须被真正采用 —— 否则又是一次「定义了没人用」
// ---------------------------------------------------------------------------

test('费用管理页与人员归属页都声明了紧凑档', () => {
  assert.ok(
    expensePage.includes('erp-compact'),
    '费用管理页必须用 erp-compact，否则它就退回默认密度'
  )
  assert.ok(
    assignmentPage.includes('erp-compact'),
    '人员归属页必须用 erp-compact，否则它就退回默认密度'
  )
})

test('行内控件统一小尺寸（与紧凑行高匹配）', () => {
  // 紧凑档行高 ~34px；默认尺寸控件 32px + 上下 4px 内边距就撑到 40px 以上。
  const smallCount = (source) => (source.match(/size="small"/g) || []).length
  assert.ok(
    smallCount(expensePage) >= 15,
    `费用页的小尺寸控件偏少（当前 ${smallCount(expensePage)} 处），行高压不下来`
  )
  assert.ok(
    smallCount(assignmentPage) >= 1,
    '人员归属页的表格控件必须用小尺寸'
  )
})

test('用户侧「备注」字段已退役（remark 转系统所有）', () => {
  assert.ok(
    !expensePage.includes('label="备注"'),
    '费用页不得再出现「备注」列 —— 该字段实测人工使用 0 条'
  )
  assert.ok(
    !expensePage.includes('prop="note"'),
    '费用页不得再暴露 note 字段'
  )
})

test('人员归属页接入全站页头 SSOT（PageHeader）', () => {
  assert.ok(
    assignmentPage.includes('PageHeader'),
    '人员归属页必须使用 PageHeader 组件，不得再写裸 <h1 style=...>'
  )
  assert.ok(
    !/<h1 style=/.test(assignmentPage),
    '不得保留裸 <h1 style=...> 页头'
  )
})
