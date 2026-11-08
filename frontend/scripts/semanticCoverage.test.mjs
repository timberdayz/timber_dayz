/**
 * 语义覆盖率巡检前端工具函数的单元测试。
 *
 * 用 ``node --test`` 运行（与 frontend/scripts/*.test.mjs 同一套写法）：
 *   node --test frontend/scripts/semanticCoverage.test.mjs
 *
 * 覆盖面板要展示的四类结论的折叠逻辑：
 * 1. 解析率格式化 / 状态分类 / 健康度文案；
 * 2. 解析率为 0 的字段 + **源表真实列名候选**的关联；
 * 3. 按平台的解析率聚合（最差的平台排最前）；
 * 4. 整体响应的健康度归并。
 */

import test from 'node:test'
import assert from 'node:assert/strict'

import {
  SEMANTIC_COVERAGE_DEFAULT_THRESHOLD,
  buildPlatformRows,
  buildZeroRateRows,
  classifyResolutionRate,
  formatResolutionRate,
  healthLabel,
  healthTagType,
  normalizeSemanticCoverage
} from '../src/domains/data_platform/utils/semanticCoverage.js'

// ── 1. 格式化与分类 ────────────────────────────────────────────────────

test('formatResolutionRate renders percentages with one decimal', () => {
  assert.equal(formatResolutionRate(0), '0.0%')
  assert.equal(formatResolutionRate(0.5), '50.0%')
  assert.equal(formatResolutionRate(1), '100.0%')
  assert.equal(formatResolutionRate(undefined), '-')
  assert.equal(formatResolutionRate('abc'), '-')
})

test('classifyResolutionRate separates zero / low / ok', () => {
  assert.equal(classifyResolutionRate(0), 'zero')
  assert.equal(classifyResolutionRate(0.2, 0.5), 'low')
  assert.equal(classifyResolutionRate(0.9, 0.5), 'ok')
  // 阈值可传 ⇒ 口径跟着调用方走。
  assert.equal(classifyResolutionRate(0.6, 0.9), 'low')
})

test('health helpers map health values to tag type and label', () => {
  assert.equal(healthTagType('healthy'), 'success')
  assert.equal(healthTagType('degraded'), 'warning')
  assert.equal(healthTagType('unknown'), 'info')
  assert.equal(healthLabel('healthy'), '健康')
  assert.equal(healthLabel('degraded'), '存在缺口')
  assert.equal(healthLabel('unknown'), '无法判定')
})

// ── 2. 解析率为 0 的字段 + 真实列名候选 ────────────────────────────────

test('buildZeroRateRows keeps only zero rate entries and attaches candidates', () => {
  const report = {
    entries: [
      {
        platform_code: 'tiktok',
        granularity: 'monthly',
        standard_field: 'profit',
        resolved_rows: 0,
        total_rows: 50,
        resolution_rate: 0
      },
      {
        platform_code: 'tiktok',
        granularity: 'monthly',
        standard_field: 'paid_amount',
        resolved_rows: 50,
        total_rows: 50,
        resolution_rate: 1
      }
    ],
    column_candidates: {
      'tiktok/monthly/profit': ['利润合计', '利润总额']
    }
  }

  const rows = buildZeroRateRows(report)

  assert.equal(rows.length, 1)
  assert.equal(rows[0].standard_field, 'profit')
  assert.deepEqual(rows[0].column_candidates, ['利润合计', '利润总额'])
})

test('buildZeroRateRows tolerates missing candidates and entries', () => {
  const rows = buildZeroRateRows({
    entries: [
      {
        platform_code: 'shopee',
        granularity: 'daily',
        standard_field: 'profit',
        resolved_rows: 0,
        total_rows: 10,
        resolution_rate: 0
      }
    ]
  })

  assert.equal(rows.length, 1)
  assert.deepEqual(rows[0].column_candidates, [])
  assert.deepEqual(buildZeroRateRows(null), [])
  assert.deepEqual(buildZeroRateRows({}), [])
})

// ── 3. 按平台的解析率聚合 ──────────────────────────────────────────────

test('buildPlatformRows aggregates rates per platform and sorts worst first', () => {
  const report = {
    entries: [
      { platform_code: 'shopee', standard_field: 'a', resolution_rate: 1 },
      { platform_code: 'shopee', standard_field: 'b', resolution_rate: 0.5 },
      { platform_code: 'tiktok', standard_field: 'a', resolution_rate: 0 },
      { platform_code: 'tiktok', standard_field: 'b', resolution_rate: 0 }
    ],
    platforms: [
      {
        platform_code: 'tiktok',
        zero_rate: 1,
        zero_standard_fields: ['a', 'b']
      }
    ]
  }

  const rows = buildPlatformRows(report)

  assert.equal(rows.length, 2)
  // 最差的平台排最前 —— 面板一打开就能看到问题。
  assert.equal(rows[0].platform_code, 'tiktok')
  assert.equal(rows[0].average_resolution_rate, 0)
  assert.equal(rows[0].zero_field_count, 2)
  assert.deepEqual(rows[0].always_zero_fields, ['a', 'b'])

  assert.equal(rows[1].platform_code, 'shopee')
  assert.equal(rows[1].average_resolution_rate, 0.75)
  assert.equal(rows[1].zero_field_count, 0)
})

test('buildPlatformRows tolerates empty report', () => {
  assert.deepEqual(buildPlatformRows(null), [])
  assert.deepEqual(buildPlatformRows({ entries: [] }), [])
})

// ── 4. 整体响应归并 ────────────────────────────────────────────────────

test('normalizeSemanticCoverage merges domain reports and warnings', () => {
  const normalized = normalizeSemanticCoverage({
    domain: 'all',
    threshold: 0.5,
    reports: [
      {
        domain: 'orders',
        generated_at: '2026-11-08T10:00:00+00:00',
        warnings: ['orders 告警'],
        summary: { health: 'healthy' }
      },
      {
        domain: 'products',
        generated_at: '2026-11-08T10:00:01+00:00',
        warnings: ['products 告警'],
        summary: { health: 'degraded' }
      }
    ]
  })

  assert.equal(normalized.domain, 'all')
  assert.equal(normalized.threshold, 0.5)
  assert.equal(normalized.reports.length, 2)
  assert.deepEqual(normalized.warnings, ['orders 告警', 'products 告警'])
  // 任一域有缺口 ⇒ 整体就是 degraded。
  assert.equal(normalized.health, 'degraded')
})

test('normalizeSemanticCoverage reports healthy only when every domain is healthy', () => {
  const normalized = normalizeSemanticCoverage({
    reports: [
      { domain: 'orders', warnings: [], summary: { health: 'healthy' } },
      { domain: 'products', warnings: [], summary: { health: 'healthy' } }
    ]
  })

  assert.equal(normalized.health, 'healthy')
})

test('normalizeSemanticCoverage falls back to unknown on empty payload', () => {
  const normalized = normalizeSemanticCoverage(null)

  assert.equal(normalized.domain, 'all')
  assert.equal(normalized.threshold, SEMANTIC_COVERAGE_DEFAULT_THRESHOLD)
  assert.deepEqual(normalized.reports, [])
  assert.deepEqual(normalized.warnings, [])
  assert.equal(normalized.health, 'unknown')
})
