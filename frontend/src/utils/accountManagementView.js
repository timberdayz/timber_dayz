function normalizeText(value) {
  return String(value || '').trim()
}

function buildMainAccountKey(platform, mainAccountId) {
  return `${normalizeText(platform)}::${normalizeText(mainAccountId)}`
}

function buildMainAccountLookup(mainAccounts = []) {
  const lookup = new Map()

  for (const item of mainAccounts) {
    const key = buildMainAccountKey(item.platform, item.main_account_id)
    lookup.set(key, item)
  }

  return lookup
}

function sortByLabel(items, getLabel) {
  return [...items].sort((left, right) => {
    return getLabel(left).localeCompare(getLabel(right), 'zh-Hans-CN', { sensitivity: 'base' })
  })
}

export function buildAccountManagementGroups({ accounts = [], mainAccounts = [] }) {
  const mainAccountLookup = buildMainAccountLookup(mainAccounts)
  const platformMap = new Map()

  for (const account of accounts) {
    const platform = normalizeText(account.platform) || 'unknown'
    const mainAccountId = normalizeText(account.parent_account || account.main_account_id || account.account_id)
    const mainAccountKey = buildMainAccountKey(platform, mainAccountId)
    const mainAccountMeta = mainAccountLookup.get(mainAccountKey)

    if (!platformMap.has(platform)) {
      platformMap.set(platform, new Map())
    }

    const mainAccountMap = platformMap.get(platform)

    if (!mainAccountMap.has(mainAccountKey)) {
      mainAccountMap.set(mainAccountKey, {
        key: mainAccountKey,
        platform,
        mainAccountId,
        mainAccountName: normalizeText(mainAccountMeta?.main_account_name) || mainAccountId,
        loginUsername: normalizeText(mainAccountMeta?.username),
        shops: [],
        shopCount: 0,
        activeShopCount: 0,
        inactiveShopCount: 0,
        missingShopIdCount: 0,
      })
    }

    const group = mainAccountMap.get(mainAccountKey)
    group.shops.push(account)
    group.shopCount += 1
    group.activeShopCount += account.enabled ? 1 : 0
    group.inactiveShopCount += account.enabled ? 0 : 1
    group.missingShopIdCount += normalizeText(account.shop_id || account.platform_shop_id) ? 0 : 1
  }

  return sortByLabel(Array.from(platformMap.entries()), ([platform]) => platform).map(([platform, mainAccountMap]) => {
    return {
      platform,
      mainAccounts: sortByLabel(Array.from(mainAccountMap.values()), (item) => {
        return `${normalizeText(item.mainAccountName)} ${item.mainAccountId}`
      }),
    }
  })
}

export function resolveSelectedMainAccountKey(groups = [], currentKey = '') {
  const visibleKeys = groups.flatMap((group) => group.mainAccounts.map((item) => item.key))
  if (visibleKeys.includes(currentKey)) {
    return currentKey
  }
  return visibleKeys[0] || ''
}

export function findMainAccountGroup(groups = [], selectedKey = '') {
  for (const platformGroup of groups) {
    const found = platformGroup.mainAccounts.find((item) => item.key === selectedKey)
    if (found) {
      return found
    }
  }
  return null
}

export function buildMainAccountSnapshot(group) {
  if (!group) {
    return null
  }

  return {
    key: group.key,
    platform: group.platform,
    mainAccountId: group.mainAccountId,
    mainAccountName: group.mainAccountName,
    loginUsername: group.loginUsername,
    shopCount: group.shopCount,
    activeShopCount: group.activeShopCount,
    inactiveShopCount: group.inactiveShopCount,
    missingShopIdCount: group.missingShopIdCount,
    shops: group.shops,
  }
}
