import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildAccountManagementGroups,
  resolveSelectedMainAccountKey,
} from '../src/utils/accountManagementView.js'

test('buildAccountManagementGroups groups shops by platform then main account', () => {
  const groups = buildAccountManagementGroups({
    accounts: [
      {
        platform: 'shopee',
        account_id: 'shop-1',
        parent_account: 'main-a',
        store_name: 'Shop A-1',
        enabled: true,
        shop_id: 'p-1',
      },
      {
        platform: 'shopee',
        account_id: 'shop-2',
        parent_account: 'main-a',
        store_name: 'Shop A-2',
        enabled: false,
        shop_id: '',
      },
      {
        platform: 'tiktok',
        account_id: 'shop-3',
        parent_account: 'main-b',
        store_name: 'Shop B-1',
        enabled: true,
        shop_id: 'p-3',
      },
    ],
    mainAccounts: [
      {
        platform: 'shopee',
        main_account_id: 'main-a',
        main_account_name: 'Main A',
        username: 'owner-a',
      },
      {
        platform: 'tiktok',
        main_account_id: 'main-b',
        main_account_name: 'Main B',
        username: 'owner-b',
      },
    ],
  })

  assert.equal(groups.length, 2)
  assert.equal(groups[0].platform, 'shopee')
  assert.equal(groups[0].mainAccounts.length, 1)
  assert.equal(groups[0].mainAccounts[0].mainAccountId, 'main-a')
  assert.equal(groups[0].mainAccounts[0].shopCount, 2)
  assert.equal(groups[0].mainAccounts[0].activeShopCount, 1)
  assert.equal(groups[0].mainAccounts[0].inactiveShopCount, 1)
  assert.equal(groups[0].mainAccounts[0].missingShopIdCount, 1)
  assert.equal(groups[1].platform, 'tiktok')
  assert.equal(groups[1].mainAccounts[0].mainAccountName, 'Main B')
})

test('resolveSelectedMainAccountKey keeps current selection when still visible', () => {
  const groups = [
    {
      platform: 'shopee',
      mainAccounts: [{ key: 'shopee::main-a' }],
    },
    {
      platform: 'tiktok',
      mainAccounts: [{ key: 'tiktok::main-b' }],
    },
  ]

  assert.equal(resolveSelectedMainAccountKey(groups, 'tiktok::main-b'), 'tiktok::main-b')
})

test('resolveSelectedMainAccountKey falls back to first visible main account', () => {
  const groups = [
    {
      platform: 'shopee',
      mainAccounts: [{ key: 'shopee::main-a' }],
    },
    {
      platform: 'tiktok',
      mainAccounts: [{ key: 'tiktok::main-b' }],
    },
  ]

  assert.equal(resolveSelectedMainAccountKey(groups, 'unknown'), 'shopee::main-a')
  assert.equal(resolveSelectedMainAccountKey([], 'unknown'), '')
})
