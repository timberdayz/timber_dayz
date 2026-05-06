import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'

const dashboardApiPath = path.resolve('src/api/dashboard.js')
const storeAnalyticsPath = path.resolve('src/domains/business/views/store/StoreAnalytics.vue')

test('dashboard api exposes store analysis endpoints', () => {
  const text = fs.readFileSync(dashboardApiPath, 'utf8')
  assert.match(text, /queryStoreAnalysisShops/)
  assert.match(text, /queryStoreAnalysisCapabilities/)
  assert.match(text, /queryStoreAnalysisOverview/)
  assert.match(text, /queryStoreAnalysisComparison/)
  assert.match(text, /queryStoreAnalysisTopProducts/)
  assert.match(text, /queryStoreAnalysisTrafficSummary/)
  assert.match(text, /queryStoreAnalysisTrafficTrend/)
})

test('store analytics view no longer calls legacy store-analytics endpoints', () => {
  const text = fs.readFileSync(storeAnalyticsPath, 'utf8')
  assert.equal(text.includes('getStoreHealthScores'), false)
  assert.equal(text.includes('getStoreGMVTrend'), false)
  assert.equal(text.includes('getStoreTrafficAnalysis'), false)
  assert.equal(text.includes('/store-analytics/'), false)
})

test('store analytics view is capability-driven for hourly support', () => {
  const text = fs.readFileSync(storeAnalyticsPath, 'utf8')
  assert.match(text, /queryStoreAnalysisShops/)
  assert.match(text, /queryStoreAnalysisCapabilities/)
  assert.match(text, /queryStoreAnalysisOverview/)
  assert.match(text, /queryStoreAnalysisComparison/)
  assert.match(text, /queryStoreAnalysisTopProducts/)
  assert.match(text, /supports_hourly_daily/)
  assert.match(text, /effective_granularity/)
  assert.match(text, /hourly/)
})

test('store analytics view uses real shop options instead of manual shop id input', () => {
  const text = fs.readFileSync(storeAnalyticsPath, 'utf8')
  assert.equal(text.includes('placeholder="杈撳叆搴楅摵ID"'), false)
  assert.match(text, /availableShops/)
  assert.match(text, /v-for="shop in availableShops"/)
})

test('store analytics view renders richer overview content', () => {
  const text = fs.readFileSync(storeAnalyticsPath, 'utf8')
  assert.match(text, /queryStoreAnalysisOverview/)
  assert.match(text, /GMV/)
  assert.match(text, /achievement_rate/)
  assert.match(text, /operating_result_text/)
  assert.match(text, /分析摘要/)
})

test('store analytics view includes comparison analysis block', () => {
  const text = fs.readFileSync(storeAnalyticsPath, 'utf8')
  assert.match(text, /queryStoreAnalysisComparison/)
  assert.match(text, /comparisonMetrics/)
  assert.match(text, /对比分析/)
})

test('store analytics view includes top products contribution block', () => {
  const text = fs.readFileSync(storeAnalyticsPath, 'utf8')
  assert.match(text, /queryStoreAnalysisTopProducts/)
  assert.match(text, /topProducts/)
  assert.match(text, /商品贡献/)
})

test('store analytics view uses page_views_per_visitor for traffic depth display', () => {
  const text = fs.readFileSync(storeAnalyticsPath, 'utf8')
  assert.match(text, /page_views_per_visitor/)
  assert.match(text, /浏览进店比/)
})
