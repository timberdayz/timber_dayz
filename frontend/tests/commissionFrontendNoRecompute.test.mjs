import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'

const repoRoot = resolve(import.meta.dirname, '..')
const srcRoot = join(repoRoot, 'src')

/**
 * 前端金额公式守护（批次 5）。
 *
 * 背景（ADR-2026-11-21）：提成与绩效工资的口径必须**只有一份实现**，
 * 真源在 `backend/services/commission_caliber.py`。
 * 前端一旦自己再乘一遍，页面上的钱就会和工资单上的钱对不上
 * （历史上就是这么出现「页面看到 ≠ 工资单拿到」的）。
 *
 * 本守护做源码扫描：前端任何地方出现金额公式字面量，即失败。
 */

/** 允许出现这些字面量的文件（本守护自身 + 说明性文案）。 */
const ALLOWED_FILES = new Set([
  'tests/commissionFrontendNoRecompute.test.mjs'
])

/**
 * 禁止出现的公式特征。
 *
 * 判定原则：只有「金额型因子」与「提成比/系数」相乘才算违规，
 * 单纯的比例换算（× 100 / ÷ 100）不算。
 */
const FORBIDDEN_PATTERNS = [
  {
    label: '金额 × 提成比',
    regex: /\w*(?:allocatable_profit|allocatableProfit|profit_basis|profitBasis|commission_amount|commissionAmount)\w*\s*\*\s*[\w.]*commission_ratio/i
  },
  {
    label: '提成比 × 金额',
    regex: /commission_ratio\w*\s*\*\s*[\w.]*(?:allocatable_profit|allocatableProfit|profit_basis|profitBasis|commission_amount|commissionAmount)/i
  },
  {
    label: '结算系数参与乘法',
    regex: /\*\s*[\w.]*settlement_coefficient/i
  },
  {
    label: '赛马/档位系数参与乘法',
    regex: /\*\s*[\w.]*(?:score_coefficient|performance_coefficient)/i
  },
  {
    label: '绩效包参与乘法',
    regex: /performance_package_amount\s*\*|\*\s*[\w.]*performance_package_amount/i
  }
]

const SOURCE_EXTENSIONS = new Set(['.js', '.mjs', '.ts', '.vue'])

function collectSourceFiles(dir, acc = []) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    const stats = statSync(full)
    if (stats.isDirectory()) {
      collectSourceFiles(full, acc)
      continue
    }
    const dot = entry.lastIndexOf('.')
    if (dot < 0) continue
    if (!SOURCE_EXTENSIONS.has(entry.slice(dot))) continue
    acc.push(full)
  }
  return acc
}

test('前端源码不得复刻提成 / 绩效工资公式', () => {
  const violations = []
  for (const file of collectSourceFiles(srcRoot)) {
    const rel = relative(repoRoot, file).split('\\').join('/')
    if (ALLOWED_FILES.has(rel)) continue
    const lines = readFileSync(file, 'utf8').split('\n')
    for (let index = 0; index < lines.length; index += 1) {
      const raw = lines[index]
      const line = raw
        .replace(/\/\/.*$/, '')
        .replace(/\/\*.*?\*\//g, '')
      if (!line.trim()) continue
      for (const { label, regex } of FORBIDDEN_PATTERNS) {
        if (regex.test(line)) {
          violations.push(`${rel}:${index + 1} [${label}] ${raw.trim()}`)
        }
      }
    }
  }
  assert.equal(
    violations.length,
    0,
    '前端复刻了金额公式（SSOT 违规）：\n' +
      violations.join('\n') +
      '\n\n金额公式的真源是 backend/services/commission_caliber.py —— ' +
      '前端只应渲染后端返回的金额；需要试算时调后端试算接口。'
  )
})

test('归属页不得保留前端本地试算函数', () => {
  const rules = readFileSync(
    join(srcRoot, 'domains/business/views/hr/shopAssignmentRules.js'),
    'utf8'
  )
  assert.equal(rules.includes('calculateTrialCommission'), false)
  assert.equal(rules.includes('resolveEstimatedCommission({ backendEstimatedCommission: 60, dirty:'), false)
  // 试算只能走后端：收集输入 + 渲染返回金额
  assert.match(rules, /export function collectEstimateOverrides/)
  assert.match(rules, /export function indexEstimateRows/)
})

test('归属页试算走后端接口', () => {
  const source = readFileSync(
    join(srcRoot, 'domains/business/views/hr/ShopAssignment.vue'),
    'utf8'
  )
  assert.match(source, /api\.postHrCommissionSettlementEstimate\(/)
  assert.match(source, /year_month:\s*configMonth\.value/)
  assert.match(source, /overrides/)
})

test('页面不再并列展示两套提成口径', () => {
  const files = [
    'domains/business/views/hr/ShopAssignment.vue',
    'domains/business/views/hr/MonthlySettlement.vue',
    'domains/business/views/hr/PerformanceManagement.vue',
    'domains/business/views/hr/PerformanceDisplay.vue',
    'domains/business/views/hr/IncomeAudit.vue'
  ]
  for (const rel of files) {
    const source = readFileSync(join(srcRoot, rel), 'utf8')
    assert.equal(
      source.includes('未含结算系数'),
      false,
      `${rel} 还在展示「未含结算系数」旧口径`
    )
  }
})

test('赛马评级在页面上必须标明不参与提成计算', () => {
  const files = [
    'domains/business/views/hr/PerformanceManagement.vue',
    'domains/business/views/hr/PerformanceDisplay.vue'
  ]
  for (const rel of files) {
    const source = readFileSync(join(srcRoot, rel), 'utf8')
    assert.match(source, /赛马评级（不参与提成计算）/)
  }
  const settlement = readFileSync(
    join(srcRoot, 'domains/business/views/hr/MonthlySettlement.vue'),
    'utf8'
  )
  assert.match(settlement, /赛马评级（不参与提成计算）/)
})

test('看板页要能解释「空白属预期」', () => {
  const source = readFileSync(
    join(srcRoot, 'domains/business/views/finance-dashboard/FinanceDashboardView.vue'),
    'utf8'
  )
  assert.match(source, /data_status/)
  assert.match(source, /data_status_note/)
})
