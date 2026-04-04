import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const dashboardApiPath = path.resolve(__dirname, '../src/api/dashboard.js')
const routerPath = path.resolve(__dirname, '../src/router/index.js')
const viewPath = path.resolve(__dirname, '../src/views/finance/BCostAnalysis.vue')

const dashboardSource = fs.readFileSync(dashboardApiPath, 'utf8')
const routerSource = fs.readFileSync(routerPath, 'utf8')
const viewSource = fs.readFileSync(viewPath, 'utf8')

test('dashboard API exposes B cost analysis query methods', () => {
  assert.equal(
    dashboardSource.includes('async queryBCostAnalysisOverview(params = {})'),
    true,
    'dashboard API should expose queryBCostAnalysisOverview'
  )
  assert.equal(
    dashboardSource.includes('async queryBCostAnalysisShopMonth(params = {})'),
    true,
    'dashboard API should expose queryBCostAnalysisShopMonth'
  )
  assert.equal(
    dashboardSource.includes('async queryBCostAnalysisOrderDetail(params = {})'),
    true,
    'dashboard API should expose queryBCostAnalysisOrderDetail'
  )
})

test('router registers /b-cost-analysis route with required auth metadata', () => {
  assert.equal(
    routerSource.includes("path: '/b-cost-analysis'"),
    true,
    'router should register /b-cost-analysis path'
  )
  assert.equal(
    routerSource.includes("name: 'BCostAnalysis'"),
    true,
    'router should register BCostAnalysis route name'
  )
  assert.equal(
    routerSource.includes("permission: 'b-cost-analysis'"),
    true,
    'router should protect page with b-cost-analysis permission'
  )
  assert.equal(
    routerSource.includes("roles: ['admin', 'manager', 'finance']"),
    true,
    'router should restrict page roles to admin/manager/finance'
  )
})

test('B cost page defaults to shop-month summary and requests overview + shop-month on first load', () => {
  assert.equal(
    viewSource.includes("const periodMonth = ref(getCurrentMonth())"),
    true,
    'page should default period_month to current month'
  )
  assert.equal(
    viewSource.includes("const activeView = ref('shop-month')"),
    true,
    'page should default to shop-month summary view'
  )
  assert.equal(
    viewSource.includes('await Promise.all([loadOverview(), loadShopMonth()])'),
    true,
    'first load should request overview and shop-month together'
  )
})

test('clicking view order detail opens drawer and requests order detail', () => {
  assert.equal(
    viewSource.includes('查看订单明细'),
    true,
    'page should provide a view-order-detail action in the table'
  )
  assert.equal(
    viewSource.includes('orderDetailDrawerVisible.value = true'),
    true,
    'view-order-detail action should open drawer'
  )
  assert.equal(
    viewSource.includes('await loadOrderDetail(row)'),
    true,
    'view-order-detail action should trigger order-detail request'
  )
})

test('empty states are explicit for shop-month and order-detail areas', () => {
  assert.equal(
    viewSource.includes('暂无店铺月汇总数据'),
    true,
    'shop-month empty state text should be explicit'
  )
  assert.equal(
    viewSource.includes('暂无订单明细数据'),
    true,
    'order-detail empty state text should be explicit'
  )
})
