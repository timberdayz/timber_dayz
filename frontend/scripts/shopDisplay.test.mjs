import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildShopAccountLookup,
  createDisplayMeta,
  decorateShopEntity,
  resolveShopDisplay
} from '../src/utils/shopDisplay.js'

const ACCOUNTS = [
  {
    platform_code: 'shopee',
    shop_account_id: 'shopee_sg_xhkj11_local',
    platform_shop_id: '123456',
    store_name: 'xhkj11.sg',
    internal_code: 'XHKJ11_SG',
    account_alias: '新加坡西虹11',
    enabled: true
  },
  {
    platform_code: 'tiktok',
    shop_account_id: 'tiktok_sg_hx_home_local',
    platform_shop_id: '',
    store_name: 'Singapore(HX Home)',
    internal_code: 'SINGAPORE_HX_HOME_SG',
    account_alias: '',
    enabled: true
  }
]

test('主名优先用 internal_code，店名作为副显', () => {
  const meta = createDisplayMeta(ACCOUNTS[0])
  assert.equal(meta.display_name, 'XHKJ11_SG')
  assert.equal(meta.secondary_name, 'xhkj11.sg')
  assert.equal(meta.canonical_name, 'xhkj11.sg')
})

test('没有 internal_code 时退回别名，再退回店名', () => {
  assert.equal(createDisplayMeta({ account_alias: '别名', store_name: '店名' }).display_name, '别名')
  assert.equal(createDisplayMeta({ store_name: '店名' }).display_name, '店名')
  assert.equal(createDisplayMeta({ shop_id: 'k' }).display_name, 'k')
  assert.equal(createDisplayMeta({}).display_name, '未命名店铺')
})

test('搜索文本同时包含内部编号、别名、店名与键值', () => {
  const meta = createDisplayMeta(ACCOUNTS[0])
  assert.ok(meta.search_text.includes('xhkj11_sg'))
  assert.ok(meta.search_text.includes('新加坡西虹11'))
  assert.ok(meta.search_text.includes('xhkj11.sg'))
  assert.ok(meta.search_text.includes('123456'))
})

test('lookup 能用平台店铺ID / 店铺账号ID / 内部编号命中', () => {
  const lookup = buildShopAccountLookup(ACCOUNTS)
  assert.equal(
    resolveShopDisplay({ platform_code: 'shopee', shop_id: '123456' }, lookup).display_name,
    'XHKJ11_SG'
  )
  assert.equal(
    resolveShopDisplay(
      { platform_code: 'shopee', shop_id: 'shopee_sg_xhkj11_local' },
      lookup
    ).display_name,
    'XHKJ11_SG'
  )
  assert.equal(
    resolveShopDisplay({ platform_code: 'shopee', internal_code: 'XHKJ11_SG' }, lookup).display_name,
    'XHKJ11_SG'
  )
})

test('平台前缀键优先：跨平台同名不会被串到别的店', () => {
  const lookup = buildShopAccountLookup([
    { platform_code: 'shopee', shop_account_id: 'a', store_name: '同名店', internal_code: 'A_SG' },
    { platform_code: 'tiktok', shop_account_id: 'b', store_name: '同名店', internal_code: 'B_SG' }
  ])
  assert.equal(
    resolveShopDisplay({ platform_code: 'tiktok', store_name: '同名店' }, lookup).display_name,
    'B_SG'
  )
  assert.equal(
    resolveShopDisplay({ platform_code: 'shopee', store_name: '同名店' }, lookup).display_name,
    'A_SG'
  )
})

test('匹配不上时退回实体自身字段', () => {
  const meta = resolveShopDisplay(
    { platform_code: 'shopee', shop_id: 'unknown' },
    buildShopAccountLookup([])
  )
  assert.equal(meta.display_name, 'unknown')
})

test('decorateShopEntity 保留装饰前的原始店名', () => {
  const lookup = buildShopAccountLookup(ACCOUNTS)
  const decorated = decorateShopEntity(
    { platform_code: 'shopee', shop_id: '123456', store_name: 'xhkj11.sg' },
    lookup
  )
  assert.equal(decorated.display_name, 'XHKJ11_SG')
  assert.equal(decorated.raw_shop_name, 'xhkj11.sg')
  assert.equal(decorated.shop_name, 'XHKJ11_SG')
})

test('重复装饰不会让原始店名被显示名顶替', () => {
  const lookup = buildShopAccountLookup(ACCOUNTS)
  const once = decorateShopEntity(
    { platform_code: 'shopee', shop_id: '123456', store_name: 'xhkj11.sg' },
    lookup
  )
  const twice = decorateShopEntity(once, lookup)
  assert.equal(twice.canonical_name, 'xhkj11.sg')
  assert.equal(twice.raw_shop_name, 'xhkj11.sg')
  assert.equal(twice.display_name, 'XHKJ11_SG')
})
