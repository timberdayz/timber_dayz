/**
 * 标准字段注册表的**加载器**(浏览器侧)。
 *
 * 与 ``semanticFieldRegistry.js`` 分开的原因:
 * ``semanticFieldRegistry.js`` 必须能被 node 端脚本直接 import
 * (不依赖 vite 的 ``import.meta.env``), 所以它不碰 ``@/api``。
 *
 * [*] 批次 D: 运行时用接口的数据(权威), 快照只作兜底。
 *     接口数据里额外带**运行时别名索引** —— 用户在模板里沉淀一次,
 *     别的模板就能自动命中, 这份数据是活的, 快照里没有。
 */

import api from '@/api'
import {
  hydrateSemanticFieldRegistry,
  semanticFieldRegistry,
} from './semanticFieldRegistry.js'

let inflightPromise = null

/**
 * 加载标准字段定义(幂等, 并发调用共用同一个请求)。
 *
 * @param {Object} [options]
 * @param {boolean} [options.force] 即使已经加载过也强制刷新
 * @returns {Promise<Object>} 注册表状态
 */
export async function loadSemanticFieldRegistry(options = {}) {
  const { force = false } = options
  if (!force && semanticFieldRegistry.loaded && semanticFieldRegistry.source === 'api') {
    return semanticFieldRegistry
  }
  if (inflightPromise) return inflightPromise

  inflightPromise = (async () => {
    try {
      const payload = await api.getSemanticFieldDefinitions()
      if (payload && typeof payload === 'object') {
        hydrateSemanticFieldRegistry(payload, { source: 'api' })
      }
      return semanticFieldRegistry
    } catch (error) {
      // 兜底: 接口失败时保留快照数据, 页面不至于空白。
      // 这里**不抛错** —— 标准字段拿不到不应该让整个模板工作台打不开。
      console.warn('[语义字段] 标准字段定义加载失败, 继续使用快照兜底:', error?.message || error)
      return semanticFieldRegistry
    } finally {
      inflightPromise = null
    }
  })()

  return inflightPromise
}

/**
 * 用后端解析一批列名(前端不再自己猜 ⇒ 前后端同一套规则)。
 *
 * @param {string} dataDomain 数据域
 * @param {Array<string>} columns 列名
 * @returns {Promise<Object>} { 列名: semantic_key }
 */
export async function resolveSemanticColumns(dataDomain, columns) {
  const list = (Array.isArray(columns) ? columns : []).filter(item => String(item ?? '').trim())
  if (!list.length) return {}

  try {
    const payload = await api.resolveSemanticColumns({
      data_domain: dataDomain || '',
      columns: list,
    })
    const results = payload?.results || []
    const mapping = {}
    for (const item of results) {
      if (item?.column && item?.semantic_key) {
        mapping[item.column] = item.semantic_key
      }
    }
    return mapping
  } catch (error) {
    console.warn('[语义字段] 列名语义解析失败, 回退到本地推断:', error?.message || error)
    return {}
  }
}
