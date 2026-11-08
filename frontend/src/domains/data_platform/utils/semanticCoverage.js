/**
 * 语义层标准字段覆盖率巡检（只读）的**前端数据处理**。
 *
 * 为什么单独放一个 util
 * --------------------
 * 后端 ``GET /api/data-pipeline/semantic-coverage`` 返回的是**原始巡检结果**
 * （逐 平台 × 粒度 × 标准字段 的解析率条目 + 平台诊断 + 列名候选 + 告警）。
 * 面板要展示的是**结论**（域健康度 / 按平台解析率 / 解析率为 0 的字段及其
 * 源表真实列名候选 / 告警列表）⇒ 这里的纯函数负责把原始结构折叠成结论,
 * 组件只负责渲染。
 *
 * 纯函数（不碰 Vue、不发请求）⇒ 可以直接被 node --test 覆盖。
 */

/** 域级健康度取值（与后端 ``summary.health`` 一致）。 */
export const SEMANTIC_COVERAGE_HEALTH = {
  HEALTHY: 'healthy',
  DEGRADED: 'degraded',
  UNKNOWN: 'unknown'
}

/** 解析率低于该值即视为「不健康」（与后端默认阈值一致）。 */
export const SEMANTIC_COVERAGE_DEFAULT_THRESHOLD = 0.5

/** 面板可选的语义域（``all`` = 两个域都看）。 */
export const SEMANTIC_COVERAGE_DOMAIN_OPTIONS = [
  { label: '全部域', value: 'all' },
  { label: '订单域', value: 'orders' },
  { label: '商品域', value: 'products' }
]

/**
 * 把解析率转成百分比文本。
 *
 * @param {number} rate 解析率（0~1）
 * @returns {string} 百分比文本（保留一位小数）
 */
export function formatResolutionRate(rate) {
  const value = Number(rate)
  if (!Number.isFinite(value)) return '-'
  return `${(value * 100).toFixed(1)}%`
}

/**
 * 解析率对应的语义状态（用于表格着色）。
 *
 * @param {number} rate 解析率（0~1）
 * @param {number} threshold 告警阈值
 * @returns {string} ``zero`` / ``low`` / ``ok``
 */
export function classifyResolutionRate(rate, threshold = SEMANTIC_COVERAGE_DEFAULT_THRESHOLD) {
  const value = Number(rate)
  if (!Number.isFinite(value)) return 'zero'
  if (value <= 0) return 'zero'
  if (value < Number(threshold)) return 'low'
  return 'ok'
}

/**
 * 域级健康度对应的 Element Plus 标签类型。
 *
 * @param {string} health healthy / degraded / unknown
 * @returns {string} success / warning / info
 */
export function healthTagType(health) {
  if (health === SEMANTIC_COVERAGE_HEALTH.HEALTHY) return 'success'
  if (health === SEMANTIC_COVERAGE_HEALTH.DEGRADED) return 'warning'
  return 'info'
}

/**
 * 域级健康度的中文文案。
 *
 * @param {string} health healthy / degraded / unknown
 * @returns {string} 中文文案
 */
export function healthLabel(health) {
  if (health === SEMANTIC_COVERAGE_HEALTH.HEALTHY) return '健康'
  if (health === SEMANTIC_COVERAGE_HEALTH.DEGRADED) return '存在缺口'
  return '无法判定'
}

/**
 * 取出「解析率为 0 的字段」及其**源表真实列名候选**。
 *
 * 运维真正要回答的是「源表里到底叫啥」⇒ 光给「解析率 0%」没有行动价值。
 * 列名候选的 key 形如 ``{platform}/{granularity}/{standard_field}``。
 *
 * @param {Object} report 单个域的巡检报告
 * @returns {Array<Object>} 行数组（每行含平台/粒度/字段/解析率/列名候选）
 */
export function buildZeroRateRows(report) {
  const entries = Array.isArray(report?.entries) ? report.entries : []
  const candidates = report?.column_candidates || {}
  const rows = []

  for (const entry of entries) {
    const rate = Number(entry?.resolution_rate)
    if (!Number.isFinite(rate) || rate > 0) continue
    const key = `${entry.platform_code}/${entry.granularity}/${entry.standard_field}`
    rows.push({
      platform_code: entry.platform_code,
      granularity: entry.granularity,
      standard_field: entry.standard_field,
      resolved_rows: entry.resolved_rows,
      total_rows: entry.total_rows,
      resolution_rate: rate,
      column_candidates: Array.isArray(candidates[key]) ? candidates[key] : []
    })
  }

  return rows
}

/**
 * 按平台汇总解析率（面板的「按平台的解析率」区块）。
 *
 * 后端 ``platforms`` 里已有平台诊断（哪些字段所有粒度都解析不出来）,
 * 但**平均解析率**按平台展示更直观 ⇒ 这里以 entries 为准重新聚合,
 * 与后端 ``average_resolution_rate`` 保持同一口径。
 *
 * @param {Object} report 单个域的巡检报告
 * @returns {Array<Object>} 行数组（按平均解析率升序 ⇒ 最差的排最前）
 */
export function buildPlatformRows(report) {
  const entries = Array.isArray(report?.entries) ? report.entries : []
  const diagnostics = new Map()
  for (const item of Array.isArray(report?.platforms) ? report.platforms : []) {
    diagnostics.set(item.platform_code, item)
  }

  const buckets = new Map()
  for (const entry of entries) {
    const bucket = buckets.get(entry.platform_code) || {
      platform_code: entry.platform_code,
      rates: [],
      zero_fields: 0
    }
    const rate = Number(entry.resolution_rate) || 0
    bucket.rates.push(rate)
    if (rate <= 0) bucket.zero_fields += 1
    buckets.set(entry.platform_code, bucket)
  }

  const rows = []
  for (const bucket of buckets.values()) {
    const diagnostic = diagnostics.get(bucket.platform_code)
    const total = bucket.rates.length || 1
    rows.push({
      platform_code: bucket.platform_code,
      average_resolution_rate: bucket.rates.reduce((sum, rate) => sum + rate, 0) / total,
      field_count: bucket.rates.length,
      zero_field_count: bucket.zero_fields,
      // 「所有粒度都解析不出来」的字段（平台级缺口，比逐粒度告警更值得优先处理）。
      always_zero_fields: Array.isArray(diagnostic?.zero_standard_fields)
        ? diagnostic.zero_standard_fields
        : [],
      zero_rate: Number(diagnostic?.zero_rate) || 0
    })
  }

  // 最差的平台排最前 —— 面板一打开就能看到问题。
  return rows.sort((left, right) => left.average_resolution_rate - right.average_resolution_rate)
}

/**
 * 把后端响应整理成面板直接可用的结构。
 *
 * @param {Object} payload 后端 ``data`` 字段
 * @returns {Object} { domain, threshold, reports, warnings, health }
 */
export function normalizeSemanticCoverage(payload) {
  const reports = Array.isArray(payload?.reports) ? payload.reports : []
  const warnings = []
  for (const report of reports) {
    for (const warning of Array.isArray(report?.warnings) ? report.warnings : []) {
      warnings.push(warning)
    }
  }

  const healthValues = reports
    .map((report) => report?.summary?.health)
    .filter(Boolean)

  let health = SEMANTIC_COVERAGE_HEALTH.UNKNOWN
  if (healthValues.includes(SEMANTIC_COVERAGE_HEALTH.DEGRADED)) {
    health = SEMANTIC_COVERAGE_HEALTH.DEGRADED
  } else if (healthValues.length && healthValues.every((value) => value === SEMANTIC_COVERAGE_HEALTH.HEALTHY)) {
    health = SEMANTIC_COVERAGE_HEALTH.HEALTHY
  }

  return {
    domain: payload?.domain || 'all',
    threshold: Number(payload?.threshold ?? SEMANTIC_COVERAGE_DEFAULT_THRESHOLD),
    reports,
    warnings,
    health
  }
}
