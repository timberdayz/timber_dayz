export function normalizeDeduplicationSelection(
  fields,
  bindings,
  fieldParseRules = [],
  preferredSemanticKey = null,
) {
  const bindingByRaw = new Map()
  const semanticKeys = new Set()
  const derivedKeys = new Set()

  for (const binding of Array.isArray(bindings) ? bindings : []) {
    const rawName = String(binding?.raw_name || '').trim()
    const semanticKey = String(binding?.semantic_key || '').trim()
    if (rawName) {
      bindingByRaw.set(rawName.toLowerCase(), binding)
    }
    if (
      semanticKey &&
      binding?.semantic_review_status === 'confirmed_semantic' &&
      binding?.hash_eligible !== false
    ) {
      semanticKeys.add(semanticKey)
    }
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
      if (
        rawBinding.semantic_review_status !== 'confirmed_semantic' ||
        rawBinding.hash_eligible === false
      ) {
        continue
      }
      const semanticKey = String(rawBinding.semantic_key || '').trim()
      if (semanticKey) {
        pushField(semanticKey)
      }
      continue
    }

    if (derivedKeys.has(value)) {
      continue
    }

    if (semanticKeys.has(value)) {
      pushField(value)
    }
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
} = {}) {
  const headerBindings = mergeHeaderBindingsForSave(baseBindings, editedBindings)
  const deduplicationFields = normalizeDeduplicationSelection(
    selectedFields,
    headerBindings,
    fieldParseRules,
    preferredSemanticKey,
  )

  return {
    headerBindings,
    deduplicationFields,
  }
}
