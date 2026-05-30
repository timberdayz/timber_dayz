import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const routerSource = readFileSync(new URL('../src/router/index.js', import.meta.url), 'utf8')
const managementSource = readFileSync(new URL('../src/domains/business/views/hr/PerformanceManagement.vue', import.meta.url), 'utf8')
const displaySource = readFileSync(new URL('../src/domains/business/views/hr/PerformanceDisplay.vue', import.meta.url), 'utf8')
const managementShopSource = readFileSync(new URL('../src/domains/business/views/hr/PerformanceManagementShop.vue', import.meta.url), 'utf8')
const managementPersonSource = readFileSync(new URL('../src/domains/business/views/hr/PerformanceManagementPerson.vue', import.meta.url), 'utf8')
const displayShopSource = readFileSync(new URL('../src/domains/business/views/hr/PerformanceDisplayShop.vue', import.meta.url), 'utf8')
const displayPersonSource = readFileSync(new URL('../src/domains/business/views/hr/PerformanceDisplayPerson.vue', import.meta.url), 'utf8')
const menuSource = readFileSync(new URL('../src/config/menuGroups.js', import.meta.url), 'utf8')

test('router exposes split performance routes', () => {
  assert.equal(routerSource.includes("path: '/hr-performance-management/shop'"), true)
  assert.equal(routerSource.includes("path: '/hr-performance-management/person'"), true)
  assert.equal(routerSource.includes("path: '/hr-performance-display/shop'"), true)
  assert.equal(routerSource.includes("path: '/hr-performance-display/person'"), true)
})

test('performance pages are route-aware for shop/person views', () => {
  assert.equal(managementSource.includes("useRoute"), true)
  assert.equal(managementSource.includes("/hr-performance-management/person"), true)
  assert.equal(managementSource.includes("showGroupToggle"), true)
  assert.equal(displaySource.includes("useRoute"), true)
  assert.equal(displaySource.includes("/hr-performance-display/person"), true)
  assert.equal(displaySource.includes("showGroupToggle"), true)
})

test('performance split route wrapper pages exist', () => {
  assert.equal(managementShopSource.includes('forced-group-by="shop"'), true)
  assert.equal(managementPersonSource.includes('forced-group-by="person"'), true)
  assert.equal(displayShopSource.includes('forced-group-by="shop"'), true)
  assert.equal(displayPersonSource.includes('forced-group-by="person"'), true)
})

test('menu points to split performance routes', () => {
  assert.equal(menuSource.includes("'/hr-performance-management/shop'"), true)
  assert.equal(menuSource.includes("'/hr-performance-display/shop'"), true)
})
