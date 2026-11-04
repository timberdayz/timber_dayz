/**
 * 店铺显示名统一口径（全站唯一）。
 *
 * 主名（display_name）
 *   internal_code（内部编号，如 `XHKJ11_SG`）
 *     → account_alias（人工别名）
 *     → store_name（平台原始店名，如 `xhkj11.sg`）
 *     → 键值（shop_account_id / platform_shop_id / shop_id）
 *     → '未命名店铺'
 *
 * 副显（secondary_name）
 *   主名之外的另一个可读名字：店名 / 别名。
 *
 * 为什么主名用 internal_code
 * -------------------------
 * 平台上能看到的是店名（"xhkj11.sg"），但**店名会改、别名也会改**；
 * internal_code 是内部编号，唯一且稳定 —— 报表、截图、对账都以它为准。
 *
 * ⚠️ 显示名**只能用于展示**。
 * 任何 key / join / group-by 都必须用 shop_id 这类**稳定键值**，
 * 因为显示名是可变的 —— 改了店名，历史分组就对不上了。
 */

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

export function createDisplayMeta(source = {}) {
  const internalCode = normalizeText(source.internal_code)
  const accountAlias = normalizeText(source.account_alias)
  // raw_shop_name 是「装饰前的原始店名」。
  // decorateShopEntity 会把 shop_name 覆写成显示名，所以**再解析一次**时
  // 必须优先用 raw_shop_name / canonical_name，否则原始店名会被显示名顶替，
  // canonical_name 失真（再装饰一次就变成「显示名 = 店名 = 显示名」）。
  const canonicalName = normalizeText(
    source.raw_shop_name ||
      source.store_name ||
      source.canonical_name ||
      source.shop_name ||
      source.name ||
      source.account_store_name
  )
  const fallbackId = normalizeText(
    source.shop_account_id || source.platform_shop_id || source.shop_id || source.account_id
  )
  const displayName = internalCode || accountAlias || canonicalName || fallbackId || '未命名店铺'
  const secondaryName =
    [canonicalName, accountAlias].find((name) => name && name !== displayName) || ''

  return {
    display_name: displayName,
    secondary_name: secondaryName,
    canonical_name: canonicalName,
    option_label: displayName,
    // 搜索文本要**同时包含所有可能的键值** ——
    // 用户可能是拿内部编号搜，也可能是拿平台店铺ID搜，
    // 只放第一个非空 ID 的话另一种就搜不到了（「看得见、搜不到」）。
    search_text: buildSearchText([
      internalCode,
      accountAlias,
      canonicalName,
      source.shop_account_id,
      source.platform_shop_id,
      source.shop_id,
      source.account_id,
      source.main_account_name,
      source.platform,
      source.platform_code
    ])
  }
}

export function buildShopAccountLookup(accounts = []) {
  const lookup = new Map()

  accounts.forEach((account) => {
    const displayMeta = createDisplayMeta(account)
    const entry = {
      ...account,
      ...displayMeta
    }
    const platform = account.platform || account.platform_code
    const keys = [
      buildLookupKey(platform, account.platform_shop_id),
      buildLookupKey(platform, account.shop_account_id),
      buildLookupKey(platform, account.shop_id),
      buildLookupKey(platform, account.internal_code),
      buildLookupKey(platform, account.store_name),
      normalizeText(account.shop_account_id),
      normalizeText(account.platform_shop_id),
      normalizeText(account.internal_code)
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
    buildLookupKey(platform, entity.internal_code),
    buildLookupKey(platform, entity.store_name),
    normalizeText(entity.shop_account_id),
    normalizeText(entity.platform_shop_id),
    normalizeText(entity.internal_code)
  ].filter(Boolean)

  const matchedAccount = candidates.map((key) => lookup.get(key)).find(Boolean)

  if (matchedAccount) {
    const fallbackCanonical = normalizeText(
      entity.raw_shop_name ||
        entity.store_name ||
        entity.shop_name ||
        entity.name ||
        matchedAccount.canonical_name
    )
    return {
      display_name: matchedAccount.display_name,
      secondary_name:
        matchedAccount.secondary_name ||
        (fallbackCanonical && fallbackCanonical !== matchedAccount.display_name
          ? fallbackCanonical
          : ''),
      canonical_name: matchedAccount.canonical_name || fallbackCanonical,
      option_label: matchedAccount.option_label,
      search_text: buildSearchText([matchedAccount.search_text, fallbackCanonical])
    }
  }

  return createDisplayMeta(entity)
}

export function decorateShopEntity(entity = {}, lookup = new Map()) {
  const displayMeta = resolveShopDisplay(entity, lookup)
  const rawShopName = normalizeText(entity.raw_shop_name || entity.store_name || entity.shop_name)
  return {
    ...entity,
    display_name: displayMeta.display_name,
    secondary_name: displayMeta.secondary_name,
    canonical_name: displayMeta.canonical_name,
    option_label: displayMeta.option_label,
    search_text: displayMeta.search_text,
    // 装饰前的原始店名 —— shop_name 会被覆写成显示名，这个字段把原件留下来，
    // 避免「原始店名」被永久替换掉之后再也找不回来。
    raw_shop_name: rawShopName,
    shop_name: displayMeta.display_name,
    canonical_shop_name: displayMeta.canonical_name
  }
}
