import api from "./index.js";

export default {
  listCategories(params = {}) {
    return api._get("/product-categories", { params });
  },
  createCategory(payload) {
    return api._post("/product-categories", payload);
  },
  updateCategory(id, payload) {
    return api._patch(`/product-categories/${id}`, payload);
  },
  listSpus(params = {}) {
    return api._get("/spus", { params });
  },
  bulkSaveSpus(payload) {
    return api._post("/spus/bulk", payload);
  },
  createSpu(payload) {
    return api._post("/spus", payload);
  },
  updateSpu(spu, payload) {
    return api._patch(`/spus/${encodeURIComponent(spu)}`, payload);
  },
  listSkus(params = {}) {
    return api._get("/skus", { params });
  },
  bulkSaveSkus(payload) {
    return api._post("/skus/bulk", payload);
  },
  createSku(payload) {
    return api._post("/skus", payload);
  },
  updateSku(skuId, payload) {
    return api._patch(`/skus/${skuId}`, payload);
  },
  listSpuSkus(spu) {
    return api._get(`/spus/${encodeURIComponent(spu)}/skus`);
  },
  bindSku(spu, payload) {
    return api._post(`/spus/${encodeURIComponent(spu)}/skus`, payload);
  },
  listPurchaseOrders(params = {}) {
    return api._get("/purchase-orders", { params });
  },
  getPurchaseOrder(id) {
    return api._get(`/purchase-orders/${id}`);
  },
  listPurchaseOrderLines(id) {
    return api._get(`/purchase-orders/${id}/lines`);
  },
  listProviderRules(params = {}) {
    return api._get("/logistics-provider-rules", { params });
  },
  createProviderRule(payload) {
    return api._post("/logistics-provider-rules", payload);
  },
  updateProviderRule(id, payload) {
    return api._patch(`/logistics-provider-rules/${id}`, payload);
  },
  listCostAssumptions() {
    return api._get("/cost-assumption-profiles");
  },
  createCostAssumption(payload) {
    return api._post("/cost-assumption-profiles", payload);
  },
  updateCostAssumption(profileId, payload) {
    return api._patch(`/cost-assumption-profiles/${profileId}`, payload);
  },
  listProfitEstimates(params = {}) {
    return api._get("/product-profit-estimates", { params });
  },
  previewProfit(payload) {
    return api._post("/product-profit-estimates/preview", payload);
  },
  saveBaselineProfit(payload) {
    return api._post("/product-profit-estimates/baseline", payload);
  },
  listLogisticsBills(params = {}) {
    return api._get("/logistics-bills", { params });
  },
  listLogisticsBatches(params = {}) {
    return api._get("/logistics-batches", { params });
  },
  getLogisticsBatch(id) {
    return api._get(`/logistics-batches/${id}`);
  },
  createLogisticsBatch(payload) {
    return api._post("/logistics-batches", payload);
  },
  updateLogisticsBatch(id, payload) {
    return api._patch(`/logistics-batches/${id}`, payload);
  },
  saveLogisticsBatchPurchaseOrders(id, payload) {
    return api._put(`/logistics-batches/${id}/purchase-orders`, payload);
  },
  async saveLogisticsBatchLines(id, payload) {
    const poIds = payload.purchase_order_ids || [];
    if (poIds.length)
      await this.saveLogisticsBatchPurchaseOrders(id, { po_ids: poIds });
    return api._put(`/logistics-batches/${id}/lines`, {
      lines: payload.lines || [],
    });
  },
  confirmLogisticsBatch(id) {
    return api._post(`/logistics-batches/${id}/confirm`, {});
  },
  voidLogisticsBatch(id, payload) {
    return api._post(`/logistics-batches/${id}/void`, payload);
  },
  getLogisticsBill(billId) {
    return api._get(`/logistics-bills/${billId}`);
  },
  createLogisticsBill(payload) {
    return api._post("/logistics-bills", payload);
  },
  updateLogisticsBill(billId, payload) {
    return api._patch(`/logistics-bills/${billId}`, payload);
  },
  saveLogisticsBillLines(billId, payload) {
    return api._put(`/logistics-bills/${billId}/lines`, payload);
  },
  confirmLogisticsBill(billId) {
    return api._post(`/logistics-bills/${billId}/confirm`, {});
  },
  voidLogisticsBill(billId, payload) {
    return api._post(`/logistics-bills/${billId}/void`, payload);
  },
  initializeFeishuProjection(payload) {
    return api._post("/feishu-projection/initialize", payload);
  },
  getFeishuProjectionStatus() {
    return api._get("/feishu-projection/status");
  },
  retryFeishuProjection() {
    return api._post("/feishu-projection/retry-failed", {});
  },
  listSpuOperating(params = {}) {
    return api._get("/spu-operating", { params });
  },
  listSkuOperatingDimensions() {
    return api._get("/sku-operating-dimensions");
  },
  listProductWarehouses(params = {}) {
    return api._get("/product-warehouses", { params });
  },
  listWarehouseStorageRules(params = {}) {
    return api._get("/warehouse-storage-rules", { params });
  },
  createWarehouseStorageRule(payload) {
    return api._post("/warehouse-storage-rules", payload);
  },
  updateWarehouseStorageRule(ruleId, payload) {
    return api._patch(`/warehouse-storage-rules/${ruleId}`, payload);
  },
  deleteWarehouseStorageRule(ruleId) {
    return api._delete(`/warehouse-storage-rules/${ruleId}`);
  },
  updatePlatformFeeRate(platformCode, payload) {
    return api._patch(`/platforms/${encodeURIComponent(platformCode)}/fee-rate`, payload);
  },
  listSkuOperatingProfiles(params = {}) {
    return api._get("/sku-operating-profiles", { params });
  },
  createSkuOperatingProfile(payload) {
    return api._post("/sku-operating-profiles", payload);
  },
  updateSkuOperatingProfile(id, payload) {
    return api._patch(`/sku-operating-profiles/${id}`, payload);
  },
  bulkSaveSkuOperatingProfiles(payload) {
    return api._post("/sku-operating-profiles/bulk", payload);
  },
  previewSkuOperatingProfit(id, payload) {
    return api._post(`/sku-operating-profiles/${id}/profit-preview`, payload);
  },
  saveSkuOperatingProfit(id, payload) {
    return api._post(`/sku-operating-profiles/${id}/profit-estimates`, payload);
  },
  listSkuOperatingProfitHistory(id, params = {}) {
    return api._get(`/sku-operating-profiles/${id}/profit-estimates`, {
      params,
    });
  },
  listPlatformSkuProfitCandidates(params = {}) {
    return api._get("/platform-sku-profit/candidates", { params });
  },
  previewPlatformSkuProfit(payload) {
    return api._post("/platform-sku-profit/preview", payload);
  },
  savePlatformSkuProfitDraft(payload) {
    return api._post("/platform-sku-profit/drafts", payload);
  },
  savePlatformSkuProfitEstimates(payload) {
    return api._post("/platform-sku-profit/estimates", payload);
  },
  listPlatformSkuProfitEstimates(params = {}) {
    return api._get("/platform-sku-profit/estimates", { params });
  },
};
