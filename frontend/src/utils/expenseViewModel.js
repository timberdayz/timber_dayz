/**
 * 费用管理页的纯逻辑层（可单测）。
 *
 * 为什么单独抽出来
 * ----------------
 * 费用页里最容易出错的三件事——「谁该出现在表里」「钱摊给谁」「怎么排序」——
 * 都不该埋在 .vue 模板里。这里把它们做成纯函数，由
 * `frontend/scripts/expenseViewModel.test.mjs` 直接断言。
 *
 * 口径（全站唯一）
 * ----------------
 * * 权威店铺状态：`core.shop_accounts.enabled`（`enabled === true` 才算在营）；
 * * 空白行只给在营店；已停用店若当月有费用记录则照常显示并标注，但**不参与分摊**；
 * * 分摊范围可按平台或租户收窄。
 */

/**
 * 行键：平台 + **店铺账号 ID**。
 *
 * 为什么不用 shop_id
 * -----------------
 * Shopee 的 `shop_id` 是平台店铺 ID（`1292370001`），TikTok 的是本地账号 ID
 * （`tiktok_sg_daone_mall_local`）—— **两者语义不同**。店铺账号 ID 在两个平台下
 * 语义一致且稳定，所以匹配键统一取 `(platform_code, shop_account_id)`：
 *
 * * 店铺目录行：`row.shop_account_id`（D2 新增字段）
 * * 费用行：`row.shop_shop_account_id`（D3 从连接中回传）
 * * 孤儿行（店铺账号已不存在）：回退到 `shop_id`，天然不与任何店铺冲突
 */
export function buildExpenseRowKey(row = {}) {
  const platform = row.platform_code || ''
  const account =
    row.shop_account_id || row.shop_shop_account_id || row.shop_id || ''
  return `${platform}|${account}`
}

/**
 * 店铺集合按启用状态拆分。
 * @returns {{ all: object[], operating: object[] }}
 */
export function splitShopsByAvailability(shops = []) {
  const all = []
  const operating = []
  ;(Array.isArray(shops) ? shops : []).forEach((shop) => {
    const item = { ...shop, is_operating: shop.enabled === true }
    all.push(item)
    if (item.is_operating) operating.push(item)
  })
  return { all, operating }
}

/** 行排序：平台 → 租户 → 店铺。 */
export function sortExpenseRows(rows = []) {
  return [...(Array.isArray(rows) ? rows : [])].sort((a, b) => {
    const platform = String(a.platform_code || '').localeCompare(
      String(b.platform_code || '')
    )
    if (platform !== 0) return platform
    const tenant = String(a.main_account_id || '').localeCompare(
      String(b.main_account_id || '')
    )
    if (tenant !== 0) return tenant
    return String(a.shop_id || '').localeCompare(String(b.shop_id || ''))
  })
}

/**
 * 解析快速拆分的分摊目标集合。
 * @param {object[]} rows 当前表格行
 * @param {{platform_code?: string, main_account_id?: string}} scope 范围；空对象 = 全部在营店
 */
export function resolveQuickSplitTargets(rows = [], scope = {}) {
  const platform = scope.platform_code || ''
  const tenant = scope.main_account_id || ''
  return (Array.isArray(rows) ? rows : []).filter((row) => {
    if (row.enabled !== true && row.is_operating !== true) return false
    if (platform && String(row.platform_code || '') !== platform) return false
    if (tenant && String(row.main_account_id || '') !== tenant) return false
    return true
  })
}

/** 拆分店铺数（与分摊目标集合口径一致）。 */
export function countSplitTargets(rows = [], scope = {}) {
  return resolveQuickSplitTargets(rows, scope).length
}

/**
 * 金额均摊：按分计算并把余数分给前面的行，保证总额分毫不差。
 */
export function distributeEvenly(totalAmount, count) {
  const totalCents = Math.round((Number(totalAmount) || 0) * 100)
  if (!count || count <= 0) return []
  const base = Math.floor(totalCents / count)
  let remainder = totalCents - base * count
  return Array.from({ length: count }, () => {
    const extra = remainder > 0 ? 1 : 0
    remainder -= extra
    return (base + extra) / 100
  })
}
