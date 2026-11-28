import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildExpenseRowKey,
  countSplitTargets,
  distributeEvenly,
  resolveQuickSplitTargets,
  sortExpenseRows,
  splitShopsByAvailability
} from '../src/utils/expenseViewModel.js'

const SHOPS = [
  {
    platform_code: 'shopee',
    shop_id: '1391124228',
    internal_code: 'HX_HOME_SG',
    enabled: true,
    main_account_id: 'shopee KR'
  },
  {
    platform_code: 'shopee',
    shop_id: '1292370001',
    internal_code: 'ETERNALBLOOM_SG',
    enabled: false,
    main_account_id: 'hongxikeji:main'
  },
  {
    platform_code: 'tiktok',
    shop_id: 'tiktok_sg_daone_mall_local',
    internal_code: 'FIORO SG',
    enabled: true,
    main_account_id: 'Tiktok 1店'
  }
]

test('店铺集合按启用状态拆成全部与在营两组', () => {
  const { all, operating } = splitShopsByAvailability(SHOPS)
  assert.equal(all.length, 3)
  assert.equal(operating.length, 2)
  assert.equal(operating.some((s) => s.shop_id === '1292370001'), false)
})

test('行键用 (platform_code, shop_account_id)，跨平台语义一致', () => {
  // 店铺目录行：Shopee 用平台店铺 ID 作 shop_id，但键取账号 ID
  assert.equal(
    buildExpenseRowKey({
      platform_code: 'shopee',
      shop_account_id: 'shopee_sg_a_local',
      shop_id: '1292370001'
    }),
    'shopee|shopee_sg_a_local'
  )
  // 店铺目录行：TikTok
  assert.equal(
    buildExpenseRowKey({
      platform_code: 'tiktok',
      shop_account_id: 'tiktok_sg_b_local',
      shop_id: 'tiktok_sg_b_local'
    }),
    'tiktok|tiktok_sg_b_local'
  )
  // 费用行：后端回传的 shop_shop_account_id
  assert.equal(
    buildExpenseRowKey({
      platform_code: 'shopee',
      shop_shop_account_id: 'shopee_sg_a_local',
      shop_id: '1292370001'
    }),
    'shopee|shopee_sg_a_local'
  )
  // 孤儿行回退到 shop_id，天然不与任何店铺冲突
  assert.equal(buildExpenseRowKey({ platform_code: 'shopee', shop_id: '999' }), 'shopee|999')
})

test('行按平台、租户、店铺排序', () => {
  const rows = [
    { platform_code: 'tiktok', shop_id: 'b', main_account_id: 'm1' },
    { platform_code: 'shopee', shop_id: 'z', main_account_id: 'm2' },
    { platform_code: 'shopee', shop_id: 'a', main_account_id: 'm1' }
  ]
  const sorted = sortExpenseRows(rows)
  assert.deepEqual(
    sorted.map((row) => row.shop_id),
    ['a', 'z', 'b']
  )
})

test('分摊目标只包含在营店铺', () => {
  const rows = [
    { platform_code: 'shopee', shop_id: 'a', enabled: true },
    { platform_code: 'shopee', shop_id: 'b', enabled: false }
  ]
  const targets = resolveQuickSplitTargets(rows, { platform_code: 'shopee' })
  assert.equal(targets.length, 1)
  assert.equal(targets[0].shop_id, 'a')
})

test('分摊范围可按平台或租户收窄', () => {
  const rows = SHOPS.map((shop) => ({ ...shop }))
  const byPlatform = resolveQuickSplitTargets(rows, { platform_code: 'tiktok' })
  assert.equal(byPlatform.length, 1)
  const byTenant = resolveQuickSplitTargets(rows, { main_account_id: 'Tiktok 1店' })
  assert.equal(byTenant.length, 1)
  const all = resolveQuickSplitTargets(rows, {})
  assert.equal(all.length, 2)
})

test('拆分店铺数与目标集合一致', () => {
  const rows = SHOPS.map((shop) => ({ ...shop }))
  assert.equal(countSplitTargets(rows, {}), 2)
  assert.equal(countSplitTargets(rows, { platform_code: 'tiktok' }), 1)
})

test('均摊保留分到分的尾差', () => {
  const parts = distributeEvenly(100, 3)
  assert.equal(parts.length, 3)
  assert.equal(
    parts.reduce((sum, value) => sum + value, 0),
    100
  )
})
