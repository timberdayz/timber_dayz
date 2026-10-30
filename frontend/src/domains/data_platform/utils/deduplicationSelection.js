/**
 * 模板更新工作台的去重字段选择工具。
 *
 * 设计原则（2026-10-30 审查后确立）：
 * 1. **不静默剔除用户已选的字段**。只有三类字段允许被剔除，且都必须给出原因：
 *    - `derived_by_parse_rule`：由解析规则派生（如 metric_date），不作为去重字段提交；
 *    - `confirmed_non_semantic`：用户/系统已明确否定其语义身份；
 *    - `not_hash_eligible`：已确认语义，但该字段被策略层判定为不可参与 Data Hash。
 * 2. **"当前绑定集里找不到 confirmed 绑定"不等于"该字段非法"**。这种情况一律保留字段，
 *    并通过 diagnostics.unresolved 汇报，避免把"绑定被截断"这类故障伪装成"用户选错了"。
 */

export const DEDUPLICATION_DIAGNOSTIC_REASONS = {
  DERIVED: 'derived_by_parse_rule',
  NON_SEMANTIC: 'confirmed_non_semantic',
  NOT_HASH_ELIGIBLE: 'not_hash_eligible',
  BINDING_NOT_CONFIRMED: 'binding_not_confirmed',
}

function recordRemoval(diagnostics, field, reason, detail) {
  if (!diagnostics || !Array.isArray(diagnostics.removed)) return
  diagnostics.removed.push({ field, reason, detail: detail || '' })
}

function recordUnresolved(diagnostics, field, reason, detail) {
  if (!diagnostics || !Array.isArray(diagnostics.unresolved)) return
  diagnostics.unresolved.push({ field, reason, detail: detail || '' })
}

export function normalizeDeduplicationSelection(
  fields,
  bindings,
  fieldParseRules = [],
  preferredSemanticKey = null,
  eligibleSemanticKeys = [],
  diagnostics = null,
) {
  const bindingByRaw = new Map()
  const semanticKeys = new Set()
  const nonSemanticKeys = new Set()
  const ineligibleKeys = new Set()
  const derivedKeys = new Set()
  const policyEligibleKeys = new Set(
    (Array.isArray(eligibleSemanticKeys) ? eligibleSemanticKeys : [])
      .map(field => String(field || '').trim())
      .filter(Boolean)
  )

  // 资格判定以**后端 hash_options 返回的 eligible 列表**为权威
  // （后端 evaluate_option 已排除 metric / system_scope 字段）。
  // 只有在后端未给出列表时才回落到绑定自身的 hash_eligible 标记。
  const isHashEligible = (semanticKey, binding) => {
    if (policyEligibleKeys.size > 0) {
      return policyEligibleKeys.has(semanticKey)
    }
    return binding?.hash_eligible !== false
  }

  for (const binding of Array.isArray(bindings) ? bindings : []) {
    const rawName = String(binding?.raw_name || '').trim()
    const semanticKey = String(binding?.semantic_key || '').trim()
    if (rawName) {
      bindingByRaw.set(rawName.toLowerCase(), binding)
    }
    if (!semanticKey) continue

    const reviewStatus = String(binding?.semantic_review_status || '').trim()
    if (reviewStatus === 'confirmed_non_semantic') {
      nonSemanticKeys.add(semanticKey)
      continue
    }
    if (reviewStatus !== 'confirmed_semantic') continue
    if (!isHashEligible(semanticKey, binding)) {
      ineligibleKeys.add(semanticKey)
      continue
    }
    semanticKeys.add(semanticKey)
  }

  for (const rule of Array.isArray(fieldParseRules) ? fieldParseRules : []) {
    const targetField = String(rule?.target_field || '').trim()
    if (targetField) {
      derivedKeys.add(targetField)
    }
  }

  const normalized = []
  const seen = new Set()
  const pushField = (field) => {
    const value = String(field || '').trim()
    if (!value) return
    const lowered = value.toLowerCase()
    if (seen.has(lowered)) return
    seen.add(lowered)
    normalized.push(value)
  }

  for (const field of Array.isArray(fields) ? fields : []) {
    const value = String(field || '').trim()
    if (!value) continue

    const rawBinding = bindingByRaw.get(value.toLowerCase())
    if (rawBinding) {
      // 用户选的是原始表头名：必须先落到已确认的语义绑定上，否则不允许提交表头名。
      if (rawBinding.semantic_review_status !== 'confirmed_semantic') {
        recordRemoval(
          diagnostics,
          value,
          rawBinding.semantic_review_status === 'confirmed_non_semantic'
            ? DEDUPLICATION_DIAGNOSTIC_REASONS.NON_SEMANTIC
            : DEDUPLICATION_DIAGNOSTIC_REASONS.BINDING_NOT_CONFIRMED,
          '该表头尚未确认为语义字段',
        )
        continue
      }
      if (!isHashEligible(String(rawBinding.semantic_key || '').trim(), rawBinding)) {
        recordRemoval(
          diagnostics,
          value,
          DEDUPLICATION_DIAGNOSTIC_REASONS.NOT_HASH_ELIGIBLE,
          '该语义字段不参与 Data Hash',
        )
        continue
      }
      const semanticKey = String(rawBinding.semantic_key || '').trim()
      if (semanticKey) {
        pushField(semanticKey)
      }
      continue
    }

    if (derivedKeys.has(value)) {
      recordRemoval(
        diagnostics,
        value,
        DEDUPLICATION_DIAGNOSTIC_REASONS.DERIVED,
        '该字段由解析规则派生，不作为去重字段提交',
      )
      continue
    }

    if (nonSemanticKeys.has(value)) {
      recordRemoval(
        diagnostics,
        value,
        DEDUPLICATION_DIAGNOSTIC_REASONS.NON_SEMANTIC,
        '该字段已被标记为非语义字段',
      )
      continue
    }

    if (ineligibleKeys.has(value)) {
      recordRemoval(
        diagnostics,
        value,
        DEDUPLICATION_DIAGNOSTIC_REASONS.NOT_HASH_ELIGIBLE,
        '该语义字段不参与 Data Hash',
      )
      continue
    }

    if (semanticKeys.has(value)) {
      pushField(value)
      continue
    }

    // 当前绑定集中找不到该字段的已确认绑定：保留字段并汇报，避免静默丢弃。
    pushField(value)
    recordUnresolved(
      diagnostics,
      value,
      DEDUPLICATION_DIAGNOSTIC_REASONS.BINDING_NOT_CONFIRMED,
      '当前绑定集中缺少该字段的已确认绑定，已保留选择，请确认字段映射',
    )
  }

  if (
    preferredSemanticKey &&
    semanticKeys.has(preferredSemanticKey) &&
    !derivedKeys.has(preferredSemanticKey) &&
    normalized.length === 0
  ) {
    pushField(preferredSemanticKey)
  }

  return normalized
}

export function mergeHeaderBindingsForSave(baseBindings = [], editedBindings = []) {
  const editedByRaw = new Map()
  for (const binding of Array.isArray(editedBindings) ? editedBindings : []) {
    const rawName = String(binding?.raw_name || '').trim()
    if (!rawName) continue
    editedByRaw.set(rawName.toLowerCase(), binding)
  }

  const merged = []
  const seen = new Set()
  for (const binding of Array.isArray(baseBindings) ? baseBindings : []) {
    const rawName = String(binding?.raw_name || '').trim()
    const key = rawName.toLowerCase()
    if (!rawName || seen.has(key)) continue
    seen.add(key)
    merged.push({ ...binding, ...(editedByRaw.get(key) || {}) })
  }

  for (const [key, binding] of editedByRaw.entries()) {
    if (seen.has(key)) continue
    seen.add(key)
    merged.push({ ...binding })
  }
  return merged
}

export function buildTemplateUpdateSubmissionState({
  baseBindings = [],
  editedBindings = [],
  selectedFields = [],
  fieldParseRules = [],
  preferredSemanticKey = null,
  eligibleSemanticKeys = [],
} = {}) {
  const headerBindings = mergeHeaderBindingsForSave(baseBindings, editedBindings)
  const diagnostics = { removed: [], unresolved: [] }
  const deduplicationFields = normalizeDeduplicationSelection(
    selectedFields,
    headerBindings,
    fieldParseRules,
    preferredSemanticKey,
    eligibleSemanticKeys,
    diagnostics,
  )

  return {
    headerBindings,
    deduplicationFields,
    diagnostics,
  }
}
