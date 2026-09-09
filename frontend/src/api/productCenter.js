import api from './index.js'

export default {
  listSpus(params = {}) { return api._get('/spus', { params }) },
  createSpu(payload) { return api._post('/spus', payload) },
  updateSpu(spu, payload) { return api._patch(`/spus/${encodeURIComponent(spu)}`, payload) },
  listSkus(params = {}) { return api._get('/skus', { params }) },
  createSku(payload) { return api._post('/skus', payload) },
  updateSku(skuId, payload) { return api._patch(`/skus/${skuId}`, payload) },
  listSpuSkus(spu) { return api._get(`/spus/${encodeURIComponent(spu)}/skus`) },
  bindSku(spu, payload) { return api._post(`/spus/${encodeURIComponent(spu)}/skus`, payload) },
  listCostAssumptions() { return api._get('/cost-assumption-profiles') },
  createCostAssumption(payload) { return api._post('/cost-assumption-profiles', payload) },
  updateCostAssumption(profileId, payload) { return api._patch(`/cost-assumption-profiles/${profileId}`, payload) },
  listProfitEstimates(params = {}) { return api._get('/product-profit-estimates', { params }) },
  previewProfit(payload) { return api._post('/product-profit-estimates/preview', payload) },
  saveBaselineProfit(payload) { return api._post('/product-profit-estimates/baseline', payload) },
  listLogisticsBills(params = {}) { return api._get('/logistics-bills', { params }) },
  getLogisticsBill(billId) { return api._get(`/logistics-bills/${billId}`) },
  createLogisticsBill(payload) { return api._post('/logistics-bills', payload) },
  updateLogisticsBill(billId, payload) { return api._patch(`/logistics-bills/${billId}`, payload) },
  saveLogisticsBillLines(billId, payload) { return api._put(`/logistics-bills/${billId}/lines`, payload) },
  confirmLogisticsBill(billId) { return api._post(`/logistics-bills/${billId}/confirm`, {}) },
  voidLogisticsBill(billId, payload) { return api._post(`/logistics-bills/${billId}/void`, payload) },
  initializeFeishuProjection(payload) { return api._post('/feishu-projection/initialize', payload) },
  getFeishuProjectionStatus() { return api._get('/feishu-projection/status') },
  retryFeishuProjection() { return api._post('/feishu-projection/retry-failed', {}) },
  listSpuOperating(params = {}) { return api._get('/spu-operating', { params }) }
}
