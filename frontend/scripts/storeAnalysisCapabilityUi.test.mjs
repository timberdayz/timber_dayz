import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'

const dashboardApiPath = path.resolve('frontend/src/api/dashboard.js')
const storeAnalyticsPath = path.resolve('frontend/src/views/store/StoreAnalytics.vue')

test('dashboard api exposes store analysis endpoints', () => {
  const text = fs.readFileSync(dashboardApiPath, 'utf8')
  assert.match(text, /queryStoreAnalysisCapabilities/)
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
  assert.match(text, /queryStoreAnalysisCapabilities/)
  assert.match(text, /supports_hourly_daily/)
  assert.match(text, /effective_granularity/)
  assert.match(text, /hourly/)
})
