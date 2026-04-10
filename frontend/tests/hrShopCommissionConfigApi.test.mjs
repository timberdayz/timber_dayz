import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const repoRoot = resolve(import.meta.dirname, '..')
const apiSource = readFileSync(resolve(repoRoot, 'src/api/index.js'), 'utf8')
const viewSource = readFileSync(resolve(repoRoot, 'src/views/hr/ShopAssignment.vue'), 'utf8')

test('HR shop commission config API forwards year_month as query params', () => {
  assert.match(
    apiSource,
    /async getHrShopCommissionConfig\s*\(\s*params\s*=\s*\{\s*\}\s*\)\s*\{[\s\S]*?_get\('\s*\/hr\/shop-commission-config'\s*,\s*\{\s*params\s*\}\)/,
  )
})

test('ShopAssignment passes configMonth as year_month when loading commission config', () => {
  assert.match(
    viewSource,
    /api\.getHrShopCommissionConfig\(\s*\{\s*year_month:\s*configMonth\.value\s*\}\s*\)/,
  )
})

test('ShopAssignment passes configMonth when saving shop commission config', () => {
  assert.match(
    apiSource,
    /async putHrShopCommissionConfig\s*\(\s*platformCode\s*,\s*shopId\s*,\s*data\s*\)\s*\{[\s\S]*?_put\(\s*`\/hr\/shop-commission-config\/\$\{platformCode\}\/\$\{shopId\}`\s*,\s*data\s*\)/,
  )
  assert.match(
    viewSource,
    /api\.putHrShopCommissionConfig\(\s*shop\.platform_code\s*,\s*shop\.shop_id\s*,\s*\{\s*year_month:\s*configMonth\.value\s*,\s*allocatable_profit_rate:\s*rate\s*\}\s*\)/,
  )
})
