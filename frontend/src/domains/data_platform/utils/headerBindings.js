/**
 * 表头绑定与语义字段的推断工具。
 *
 * [*] 批次 D: 这里以前**自己抄了一份**标准字段定义(``SEMANTIC_FIELD_META``,
 *     360 行)与一套逐字相等的推断算法, 已经和后端漂了 ——
 *     前端算出来的 `required` 永远是 false, `product_name` 叫「商品名」,
 *     5 个字段的别名对不上, 前端「已自动识别」后端却不认。
 *
 *     现在标准字段定义**只有后端一份**, 前端通过 API-1 取
 *     (``/field-mapping/semantic-fields/definitions``),
 *     本模块只保留「绑定结构」相关的逻辑, 字段相关的全部走
 *     ``semanticFieldRegistry.js`` 的访问器。
 */

import {
  getSemanticFieldMeta,
  getSemanticFieldOptionGroupsForDomain,
  inferSemanticKey,
  inferSemanticKeyForDomain,
  isHashEligibleSemanticKey,
  isSystemScopeSemanticKey,
  normalizeSemanticAlias,
  semanticRequirements,
  semanticFieldRegistry,
} from './semanticFieldRegistry.js'
import { SEMANTIC_FIELD_REGISTRY_SNAPSHOT } from './semanticFieldRegistrySnapshot.js'

function looksLikeUnnamedHeader(columnName) {
  return String(columnName ?? '').trim().toLowerCase().startsWith('unnamed:')
}

/**
 * hash 的系统作用域字段(来自采集上下文, 不是文件里的列)。
 *
 * 取自**生成物**快照(``scripts/generate_semantic_field_snapshot.py``),
 * 不是手抄的常量 ⇒ 不会与后端漂。
 * 运行期的权威值在 ``semanticFieldRegistry.systemHashScopeFields``。
 */
export const SYSTEM_HASH_SCOPE_FIELDS = [
  ...(SEMANTIC_FIELD_REGISTRY_SNAPSHOT?.system_hash_scope_fields || []),
]

export const NON_SEMANTIC_FIELD_VALUE = '__non_semantic__'

export const NON_SEMANTIC_FIELD_OPTION = {
  value: NON_SEMANTIC_FIELD_VALUE,
  label: '仅保留原始字段，不作为系统语义字段',
  description: '保留 raw_data，不参与 Data Hash。',
}

export {
  getSemanticFieldMeta,
  getSemanticFieldOptionGroupsForDomain,
  inferSemanticKey,
  inferSemanticKeyForDomain,
  isHashEligibleSemanticKey,
  isSystemScopeSemanticKey,
  normalizeSemanticAlias,
  semanticRequirements,
  semanticFieldRegistry,
}

function looksLikeDateValue(rawValue) {
  const text = String(rawValue ?? '').trim()
  if (!text) return false

  const normalized = text.replace(/\//g, '-').replace('Z', '+00:00')
  if (/^\d{4}-\d{1,2}-\d{1,2}(?:[ tT]\d{1,2}:\d{2}(?::\d{2})?)?$/.test(normalized)) {
    return true
  }

  const timestamp = Date.parse(normalized)
  return !Number.isNaN(timestamp)
}

function looksLikeNumberValue(rawValue) {
  const text = String(rawValue ?? '').trim()
  if (!text) return false
  return !Number.isNaN(Number(text.replaceAll(',', '')))
}

export function inferHeaderBindings({
  headerColumns = [],
  sampleData = {},
  dataDomain = '',
} = {}) {
  return (Array.isArray(headerColumns) ? headerColumns : []).map((rawName, position) => {
    const sampleValue = sampleData?.[rawName]
    let sampleType = 'string'
    let confidence = 0.5
    let displayName = rawName
    let semanticKey = null
    let semanticRole = null
    let aliases = []

    if (looksLikeDateValue(sampleValue)) {
      sampleType = 'date'
      confidence = 0.98
    } else if (looksLikeNumberValue(sampleValue)) {
      sampleType = 'number'
      confidence = 0.7
    }

    if (looksLikeUnnamedHeader(rawName) && sampleType === 'date') {
      displayName = '日期'
      semanticKey = 'metric_date'
      semanticRole = 'metric_date'
      aliases = ['日期', '统计日期']
    }

    semanticKey = semanticKey || inferSemanticKeyForDomain(dataDomain, rawName, displayName, ...aliases)
    const meta = semanticKey ? getSemanticFieldMeta(semanticKey) : null
    if (meta?.aliases?.length) {
      aliases = Array.from(new Set([...aliases, ...meta.aliases]))
    }
    const requirements = semanticRequirements(semanticKey)

    return {
      raw_name: rawName,
      display_name: displayName,
      semantic_key: semanticKey,
      semantic_role: semanticRole,
      aliases,
      required: requirements.required,
      hash_participates: requirements.hash_participates,
      hash_eligible: requirements.hash_eligible,
      semantic_kind: requirements.semantic_kind,
      identity_strength: requirements.identity_strength,
      hash_warning: requirements.hash_warning,
      semantic_review_status: semanticKey ? 'confirmed_semantic' : 'pending',
      // 来源标记：批量推断出来的语义键不等于用户确认过。
      // 只有用户在界面上明确确认过的绑定，才允许被提升成语义身份，
      // 否则「产品ID」这种中文列名会被当成 product_id，与语义键模板判成口径一致。
      semantic_review_source: 'inferred',
      position,
      sample_type: sampleType,
      confidence,
    }
  })
}

export function updateHeaderBindingSemantic(headerBindings = [], rawName, semanticKey) {
  return (Array.isArray(headerBindings) ? headerBindings : []).map((binding) => {
    if (binding?.raw_name !== rawName) return binding
    if (semanticKey === NON_SEMANTIC_FIELD_VALUE) {
      return {
        ...binding,
        semantic_key: null,
        semantic_role: null,
        aliases: [],
        required: false,
        hash_participates: false,
        hash_eligible: false,
        semantic_kind: '',
        semantic_review_status: 'confirmed_non_semantic',
        semantic_review_source: 'user',
        display_name: binding?.display_name || binding?.raw_name,
      }
    }
    const normalizedKey = semanticKey || null
    const meta = normalizedKey ? getSemanticFieldMeta(normalizedKey) : null
    const requirements = semanticRequirements(normalizedKey)
    return {
      ...binding,
      semantic_key: normalizedKey,
      semantic_role: normalizedKey === 'metric_date' ? 'metric_date' : binding?.semantic_role || null,
      aliases: meta?.aliases ? [...meta.aliases] : [],
      required: requirements.required,
      hash_participates: requirements.hash_participates,
      hash_eligible: requirements.hash_eligible,
      semantic_kind: requirements.semantic_kind,
      identity_strength: requirements.identity_strength,
      hash_warning: requirements.hash_warning,
      semantic_review_status: normalizedKey ? 'confirmed_semantic' : 'pending',
      // 用户在下拉框里明确改过 ⇒ 属于「用户确认」，可被提升成语义身份。
      semantic_review_source: 'user',
      display_name: binding?.display_name || binding?.raw_name,
    }
  })
}

export function formatHeaderBindingLabel(field, headerBindings = []) {
  const binding = (Array.isArray(headerBindings) ? headerBindings : []).find(
    item => item?.raw_name === field || item?.semantic_key === field
  )

  if (!binding) return field
  const meta = getSemanticFieldMeta(binding.semantic_key)
  if (meta) {
    return `${meta.label} (${binding.raw_name || field})`
  }
  if (binding.display_name && binding.display_name !== binding.raw_name) {
    return `${binding.display_name} (${binding.raw_name})`
  }
  return binding.raw_name || field
}
