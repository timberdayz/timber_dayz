/**
 * 语义层标准字段覆盖率巡检的**接口封装**(浏览器侧)。
 *
 * 与 ``semanticCoverage.js`` 分开的原因同 ``semanticFieldRegistryApi.js``:
 * ``semanticCoverage.js`` 是纯函数(不依赖 ``@/api``), 才能被 node 端脚本直接
 * import 做单测; 这里只负责发请求 + 把响应折叠成面板要用的结构。
 *
 * 只读:本模块只发 GET, 不做任何写操作。
 */

import api from '@/api'
import { normalizeSemanticCoverage } from './semanticCoverage.js'

/**
 * 巡检接口的 axios 超时(毫秒)。
 *
 * 为什么不用默认的 30s: 巡检要对 ``semantic.fact_*_atomic`` 做全量聚合
 * (三个域各一条聚合 SQL, 命中 0% 字段时再加一条真实列名采集 SQL),
 * 耗时与 Dashboard 家族同量级 ⇒ 按 ``TIMEOUTS.dashboard`` 的 120s 对齐。
 *
 * ⚠ 超时预算顺序: DB statement_timeout(默认 25s/条) < 前端 120s ⇒
 * DB 先放弃并给出**可读的**「巡检跳过」warning, 而不是前端先报「网络连接失败」。
 */
const SEMANTIC_COVERAGE_TIMEOUT_MS = 120000

/**
 * 拉取一次语义覆盖率巡检结果。
 *
 * 失败**不抛错**: 巡检面板是运维辅助视图, 拿不到数据时应当显示「无数据 + 提示」,
 * 而不是把整个页面打挂。调用方通过返回值的 ``ok`` 字段区分。
 *
 * @param {Object} [options]
 * @param {string} [options.domain] orders / products / analytics / all(默认 all)
 * @param {number} [options.threshold] 解析率告警阈值(0~1)
 * @returns {Promise<Object>} { ok, data, error }
 */
export async function fetchSemanticCoverage(options = {}) {
  const { domain = 'all', threshold = null } = options

  const params = { domain }
  if (threshold !== null && threshold !== undefined && threshold !== '') {
    params.threshold = threshold
  }

  try {
    const payload = await api._get('/data-pipeline/semantic-coverage', {
      params,
      timeout: SEMANTIC_COVERAGE_TIMEOUT_MS
    })
    return { ok: true, data: normalizeSemanticCoverage(payload), error: null }
  } catch (error) {
    console.warn(
      '[语义覆盖率] 巡检结果加载失败:',
      error?.message || error
    )
    return {
      ok: false,
      data: normalizeSemanticCoverage(null),
      error: error?.message || '巡检结果加载失败'
    }
  }
}
