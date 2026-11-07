/**
 * 标准字段注册表(前端唯一入口)。
 *
 * [*] 批次 D: 前端以前在 `headerBindings.js` 里**自己抄了一份**标准字段定义
 *     (360 行), 已经和后端漂了:
 *
 *       - 41 个字段里前端普遍缺 `domain` / `required` / `system_scope`
 *         ⇒ 前端算出来的 `required` 永远是 false, 与后端契约判定对不上;
 *       - `product_name` 前端叫「商品名」后端叫「商品名称」;
 *       - 5 个字段的别名列表对不上。
 *
 *     ⇒ 用户在前端看到的选项 ≠ 后端实际认定(FE-1), 前端推断与后端各写各的(FE-2)。
 *
 * 现在: 标准字段定义只有后端一份(`backend/services/semantic_field_registry.py`),
 * 前端通过 API-1(`/field-mapping/semantic-fields/definitions`)取。
 *
 * 本模块负责:
 *   1. 持有当前生效的定义(接口返回优先, 快照兜底);
 *   2. 提供访问器(其它模块只准用访问器, 不准直接读常量);
 *   3. 归一化与推断 —— 与后端**同一套规则**。
 *
 * 归一化为什么前端也要有一份:
 *   前端要在浏览器里查别名索引, 必须自己算一次归一化。
 *   两边各写一份必然漂 ⇒ 快照里带 `normalization_samples`,
 *   由 `frontend/scripts/dataSyncSemanticRegistry.test.mjs` 逐条断言,
 *   由 `backend/tests/data_pipeline/test_semantic_translation_guardrails.py` 重新生成比对。
 */

import { reactive } from 'vue'
import { SEMANTIC_FIELD_REGISTRY_SNAPSHOT } from './semanticFieldRegistrySnapshot.js'

const FULLWIDTH_PUNCTUATION = {
  '（': '(',
  '）': ')',
  '：': ':',
  '，': ',',
  '、': ',',
  '。': '.',
  '％': '%',
  '＋': '+',
  '－': '-',
  '／': '/',
  '＿': '_',
}

//: 末尾括号里是 3 个字母(如 `(RMB)`)⇒ 币种后缀。
const CURRENCY_SUFFIX_PATTERN = /[(（]\s*[A-Za-z]{3}\s*[)）]\s*$/
//: 末尾括号里是短文本(如 `(人民币)`)⇒ 需要再判断是不是币种。
const CURRENCY_NO_PAREN_PATTERN = /[(（][^（()）]{0,12}[)）]\s*$/
const CURRENCY_LIKE_CN = /(元|币|美元|人民币|美金|欧元|日元)/

/**
 * 把列名/别名归一化成「可比较」的形态。
 *
 * 与 `backend/services/semantic_field_registry.py::normalize_semantic_alias`
 * **逐条对应**(顺序固定):
 *   1. 去首尾空白;
 *   2. 全角标点 → 半角;
 *   3. 去掉末尾的币种括号后缀(`(RMB)` / `（美元）`);
 *   4. 去掉必填星号(`*`);
 *   5. 去掉所有空白(含换行、全角空格);
 *   6. 去掉下划线;
 *   7. 大小写折叠。
 *
 * @param {*} value 原始列名
 * @returns {string} 归一化后的字符串; 空值返回空字符串
 */
export function normalizeSemanticAlias(value) {
  let text = String(value ?? '').trim()
  if (!text) return ''

  for (const [source, target] of Object.entries(FULLWIDTH_PUNCTUATION)) {
    text = text.split(source).join(target)
  }

  let match = CURRENCY_SUFFIX_PATTERN.exec(text)
  if (!match) {
    const candidate = CURRENCY_NO_PAREN_PATTERN.exec(text)
    if (candidate) {
      const inner = candidate[0].replace(/^[()]+/, '').replace(/[()]+$/, '').trim()
      const isCurrencyLike = /^[A-Za-z]{3}$/.test(inner) || CURRENCY_LIKE_CN.test(inner)
      if (isCurrencyLike) match = candidate
    }
  }
  if (match) {
    text = text.slice(0, match.index).trim()
  }

  text = text.replace(/\*/g, '')
  text = text.replace(/\s+/g, '')
  text = text.replace(/_/g, '')
  return text.trim().toLowerCase()
}

/**
 * 当前生效的标准字段注册表状态。
 *
 * `source` 标明数据来源:
 *   - `snapshot` —— 还没拿到接口数据(兜底);
 *   - `api`     —— 已经从 API-1 刷新过(权威)。
 */
export const semanticFieldRegistry = reactive({
  fields: {},
  optionGroups: [],
  aliasIndex: {},
  domainAliasIndex: {},
  domainColumnIndex: {},
  runtimeAliasIndex: {},
  runtimeBuiltinAliasIndex: {},
  systemHashScopeFields: [],
  hashIdentityKeys: [],
  loaded: false,
  source: 'snapshot',
  version: 0,
})

function indexFields(payload) {
  const fields = {}
  for (const field of payload?.fields || []) {
    fields[field.semantic_key] = field
  }
  return fields
}

/**
 * 用一份载荷刷新注册表。
 *
 * @param {Object} payload API-1 的返回体(或快照)
 * @param {Object} [options]
 * @param {string} [options.source] 数据来源标记
 * @returns {Object} 刷新后的注册表状态
 */
export function hydrateSemanticFieldRegistry(payload, options = {}) {
  if (!payload || typeof payload !== 'object') {
    return semanticFieldRegistry
  }

  semanticFieldRegistry.fields = indexFields(payload)
  semanticFieldRegistry.optionGroups = Array.isArray(payload.option_groups)
    ? payload.option_groups
    : []
  semanticFieldRegistry.aliasIndex = payload.alias_index || {}
  semanticFieldRegistry.domainAliasIndex = payload.domain_alias_index || {}
  semanticFieldRegistry.domainColumnIndex = payload.domain_column_index || {}
  semanticFieldRegistry.runtimeAliasIndex = payload.runtime_alias_index || {}
  semanticFieldRegistry.runtimeBuiltinAliasIndex = payload.runtime_builtin_alias_index || {}
  semanticFieldRegistry.systemHashScopeFields = payload.system_hash_scope_fields || []
  semanticFieldRegistry.hashIdentityKeys = payload.hash_identity_keys || []
  semanticFieldRegistry.loaded = true
  semanticFieldRegistry.source = options.source || 'api'
  semanticFieldRegistry.version += 1
  return semanticFieldRegistry
}

// 兜底: 模块加载时先用快照铺一遍, 保证接口回来之前页面不是空白。
// 接口数据一到就会覆盖(见 semanticFieldRegistryApi.js)。
hydrateSemanticFieldRegistry(SEMANTIC_FIELD_REGISTRY_SNAPSHOT, { source: 'snapshot' })

/**
 * 取一个标准字段的定义。
 *
 * @param {string} semanticKey 语义键
 * @returns {Object|null} 字段定义; 不存在返回 null
 */
export function getSemanticFieldMeta(semanticKey) {
  const key = String(semanticKey ?? '').trim()
  if (!key) return null
  return semanticFieldRegistry.fields[key] || null
}

/**
 * 该语义键是否属于 hash 的系统作用域(来自采集上下文, 不是文件里的列)。
 *
 * @param {string} semanticKey 语义键
 * @returns {boolean}
 */
export function isSystemScopeSemanticKey(semanticKey) {
  const key = String(semanticKey ?? '').trim()
  if (!key) return false
  if (semanticFieldRegistry.systemHashScopeFields.includes(key)) return true
  const meta = getSemanticFieldMeta(key)
  return Boolean(meta?.system_scope)
}

/**
 * 该语义键是否允许参与 data_hash。
 *
 * @param {string} semanticKey 语义键
 * @returns {boolean}
 */
export function isHashEligibleSemanticKey(semanticKey) {
  const meta = getSemanticFieldMeta(semanticKey)
  return Boolean(meta?.hash_eligible) && !isSystemScopeSemanticKey(semanticKey)
}

/**
 * 取某个数据域可用的语义字段分组(下拉框用)。
 *
 * @param {string} dataDomain 数据域
 * @returns {Array<{label: string, options: Array}>}
 */
export function getSemanticFieldOptionGroupsForDomain(dataDomain = '') {
  const domain = String(dataDomain || '').trim().toLowerCase()
  const domainAliases = new Set([domain])
  if (domain === 'traffic') domainAliases.add('analytics')
  if (domain === 'analytics') domainAliases.add('traffic')

  const isAllowedForDomain = (option) => {
    const optionDomain = String(option?.domain || 'common').trim().toLowerCase()
    if (!optionDomain || optionDomain === 'common') return true
    if (!domain) return true
    return domainAliases.has(optionDomain)
  }

  return (semanticFieldRegistry.optionGroups || [])
    .map(group => ({
      label: group.label,
      options: (group.options || []).filter(isAllowedForDomain),
    }))
    .filter(group => group.options.length > 0)
}

/**
 * 全量语义字段选项(下拉框用, 不按域过滤)。
 *
 * @returns {Array<Object>}
 */
export function getSemanticFieldOptions() {
  const options = []
  for (const group of semanticFieldRegistry.optionGroups || []) {
    options.push(...(group.options || []))
  }
  return options
}

function lookup(index, normalized) {
  if (!index || !normalized) return null
  return index[normalized] || null
}

function lookupByDomain(index, domain, normalized) {
  if (!index || !normalized) return null
  const bucket = index[domain]
  if (bucket && bucket[normalized]) return bucket[normalized]
  const globalBucket = index['*']
  if (globalBucket && globalBucket[normalized]) return globalBucket[normalized]
  return null
}

/**
 * 按列名推断语义键(全局口径, 不带域限定)。
 *
 * @param {...*} values 候选列名(逐个尝试)
 * @returns {string|null}
 */
export function inferSemanticKey(...values) {
  for (const rawValue of values) {
    const value = String(rawValue ?? '').trim()
    if (!value) continue
    const direct = semanticFieldRegistry.fields[value] ? value : null
    if (direct) return direct
    const normalized = normalizeSemanticAlias(value)
    if (!normalized) continue
    const matched = lookup(semanticFieldRegistry.aliasIndex, normalized)
    if (matched) return matched
  }
  return null
}

/**
 * 按数据域推断列名对应的语义键。
 *
 * 查找顺序与后端 `infer_semantic_key_for_domain` **完全一致**:
 *   1. 域限定列名表;
 *   2. 用户确认过的全局别名(运行时);
 *   3. 域限定别名表;
 *   4. 运行时内置别名;
 *   5. 全局别名表。
 *
 * @param {string} dataDomain 数据域
 * @param {...*} values 候选列名
 * @returns {string|null}
 */
export function inferSemanticKeyForDomain(dataDomain, ...values) {
  const domain = String(dataDomain || '').trim().toLowerCase()
  for (const rawValue of values) {
    const normalized = normalizeSemanticAlias(rawValue)
    if (!normalized) continue

    const override = lookupByDomain(semanticFieldRegistry.domainColumnIndex, domain, normalized)
    if (override) return override

    const confirmed = lookupByDomain(semanticFieldRegistry.runtimeAliasIndex, domain, normalized)
    if (confirmed) return confirmed

    const domainAlias = lookupByDomain(semanticFieldRegistry.domainAliasIndex, domain, normalized)
    if (domainAlias) return domainAlias

    const builtin = lookupByDomain(semanticFieldRegistry.runtimeBuiltinAliasIndex, domain, normalized)
    if (builtin) return builtin
  }
  return inferSemanticKey(...values)
}

/**
 * 一个语义键的「要求」(required / hash 参与资格)。
 *
 * @param {string} semanticKey 语义键
 * @returns {Object}
 */
export function semanticRequirements(semanticKey) {
  const meta = getSemanticFieldMeta(semanticKey)
  return {
    required: Boolean(meta?.required),
    // 批次 E(D2): hash_participates 已下线 ——
    // 「参与去重」由版本级核心字段清单(core_fields)的 in_hash 表达。
    hash_eligible: Boolean(meta?.hash_eligible),
    semantic_kind: meta?.kind || '',
    system_scope: Boolean(meta?.system_scope),
    identity_strength: meta?.identity_strength || '',
    hash_warning: meta?.hash_warning || '',
  }
}
