import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildShopAccountLookup,
  resolveShopDisplay,
} from '../src/utils/shopDisplay.js'

test('resolveShopDisplay prefers account alias and keeps canonical name as secondary text', () => {
  const lookup = buildShopAccountLookup([
    {
      platform: 'shopee',
      account_alias: '西航新加坡1店',
      store_name: 'HongXi Singapore Local',
      platform_shop_id: 'shop-001',
      shop_account_id: 'shopee_sg_hongxi_local',
    },
  ])

  const result = resolveShopDisplay(
    {
      platform_code: 'shopee',
      shop_id: 'shop-001',
      shop_name: 'HongXi Singapore Local',
    },
    lookup,
  )

  assert.equal(result.display_name, '西航新加坡1店')
  assert.equal(result.secondary_name, 'HongXi Singapore Local')
  assert.equal(result.option_label, '西航新加坡1店')
  assert.match(result.search_text, /西航新加坡1店/i)
  assert.match(result.search_text, /HongXi Singapore Local/i)
})

test('resolveShopDisplay falls back to canonical name when no alias is configured', () => {
  const lookup = buildShopAccountLookup([])
  const result = resolveShopDisplay(
    {
      platform_code: 'tiktok',
      shop_id: 'acc-ph',
      shop_name: 'Tiktok PH Store',
    },
    lookup,
  )

  assert.equal(result.display_name, 'Tiktok PH Store')
  assert.equal(result.secondary_name, '')
})
