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
  listProfitEstimates(params = {}) { return api._get('/product-profit-estimates', { params }) },
  listSpuOperating(params = {}) { return api._get('/spu-operating', { params }) }
}
