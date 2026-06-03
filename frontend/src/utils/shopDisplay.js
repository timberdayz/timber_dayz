function normalizeText(value) {
  return String(value || '').trim()
}

function normalizePlatform(value) {
  return normalizeText(value).toLowerCase()
}

function buildLookupKey(platform, identifier) {
  const normalizedPlatform = normalizePlatform(platform)
  const normalizedIdentifier = normalizeText(identifier)
  if (!normalizedPlatform || !normalizedIdentifier) return ''
  return `${normalizedPlatform}::${normalizedIdentifier}`
}

function buildSearchText(parts) {
  return parts
    .map((part) => normalizeText(part))
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
}

function createDisplayMeta(source = {}) {
  const accountAlias = normalizeText(source.account_alias)
  const canonicalName = normalizeText(
    source.store_name || source.shop_name || source.name || source.account_store_name,
  )
  const fallbackId = normalizeText(
    source.shop_account_id || source.platform_shop_id || source.shop_id || source.account_id,
  )
  const displayName = accountAlias || canonicalName || fallbackId || '未命名店铺'
  const secondaryName =
    accountAlias && canonicalName && accountAlias !== canonicalName ? canonicalName : ''

  return {
    display_name: displayName,
    secondary_name: secondaryName,
    canonical_name: canonicalName,
    option_label: displayName,
    search_text: buildSearchText([
      accountAlias,
      canonicalName,
      fallbackId,
      source.main_account_name,
      source.platform,
      source.platform_code,
    ]),
  }
}

export function buildShopAccountLookup(accounts = []) {
  const lookup = new Map()

  accounts.forEach((account) => {
    const displayMeta = createDisplayMeta(account)
    const entry = {
      ...account,
      ...displayMeta,
    }
    const platform = account.platform || account.platform_code
    const keys = [
      buildLookupKey(platform, account.platform_shop_id),
      buildLookupKey(platform, account.shop_account_id),
      buildLookupKey(platform, account.shop_id),
      normalizeText(account.shop_account_id),
      normalizeText(account.platform_shop_id),
    ].filter(Boolean)

    keys.forEach((key) => {
      if (!lookup.has(key)) {
        lookup.set(key, entry)
      }
    })
  })

  return lookup
}

export function resolveShopDisplay(entity = {}, lookup = new Map()) {
  const platform = entity.platform || entity.platform_code
  const candidates = [
    buildLookupKey(platform, entity.shop_account_id),
    buildLookupKey(platform, entity.platform_shop_id),
    buildLookupKey(platform, entity.shop_id),
    normalizeText(entity.shop_account_id),
    normalizeText(entity.platform_shop_id),
    normalizeText(entity.shop_id),
  ].filter(Boolean)

  const matchedAccount = candidates
    .map((key) => lookup.get(key))
    .find(Boolean)

  if (matchedAccount) {
    const fallbackCanonical = normalizeText(
      entity.shop_name || entity.store_name || entity.name || matchedAccount.canonical_name,
    )
    return {
      display_name: matchedAccount.display_name,
      secondary_name:
        matchedAccount.secondary_name ||
        (fallbackCanonical && fallbackCanonical !== matchedAccount.display_name ? fallbackCanonical : ''),
      canonical_name: matchedAccount.canonical_name || fallbackCanonical,
      option_label: matchedAccount.option_label,
      search_text: buildSearchText([matchedAccount.search_text, fallbackCanonical]),
    }
  }

  return createDisplayMeta(entity)
}

export function decorateShopEntity(entity = {}, lookup = new Map()) {
  const displayMeta = resolveShopDisplay(entity, lookup)
  return {
    ...entity,
    display_name: displayMeta.display_name,
    secondary_name: displayMeta.secondary_name,
    canonical_name: displayMeta.canonical_name,
    option_label: displayMeta.option_label,
    search_text: displayMeta.search_text,
    shop_name: displayMeta.display_name,
    canonical_shop_name: displayMeta.canonical_name,
  }
}
