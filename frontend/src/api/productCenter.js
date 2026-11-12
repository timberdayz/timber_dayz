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
  // SPU 值域 —— 「可选的款有哪些」是**独立的业务口径**，不是 /spus 的分页切片。
  // browse：在售（可被筛选）；assignable：还能挂新 SKU（可被赋值）。
  listSpuOptions(params = {}) {
    return api._get("/spus/options", { params });
  },
  listSpuAssignableOptions(params = {}) {
    return api._get("/spus/assignable-options", { params });
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
  previewSpuDeletion(spu) {
    return api._post(`/spus/${encodeURIComponent(spu)}/deletion-preview`, {});
  },
  softDeleteSpu(spu, payload) {
    return api._post(`/spus/${encodeURIComponent(spu)}/soft-delete`, payload);
  },
  restoreSpu(spu, payload) {
    return api._post(`/spus/${encodeURIComponent(spu)}/restore`, payload);
  },
  batchSoftDeleteSpus(payload) {
    return api._post(`/spus/batch-soft-delete`, payload);
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
  // 平台级最低售价人工覆盖（阶段 2.1b）。
  // ⚠️ 为什么是独立接口，而不是 SKU 主数据的保存字段：
  // ① 人工覆盖是 **SKU × 平台** 的量（TikTok 与 Shopee 的平台成本率不同，底线也不同），
  //    挂在 SKU 主数据上等于一个数套所有平台；
  // ② `core.dim_erp_sku` 参与「采集机 → 云端」同步，同步脚本对它做
  //    `TRUNCATE ... RESTART IDENTITY CASCADE` ⇒ 挂在 SKU 上的覆盖值每次同步都被抹掉，
  //    护栏上限形同虚设。
  // 传 `min_selling_price_override: null` 表示「重置为自动值」。
  setSkuPricingOverride(skuId, payload) {
    return api._patch(`/skus/${skuId}/pricing-override`, payload);
  },
  // 基准售价即时影响预览（阶段 4 工具 3）。
  // ⚠️ 预览是**假设**：不写库、不写审计。真正生效要等运营保存 SKU 主数据。
  // ⚠️ `reference_selling_price` **必填**（可以是 null = 预览「清空基准售价」）：
  //    少传这个键后端会 422，所以这里即使值是 null 也必须出现在 body 里。
  previewSkuSellingPrice(skuId, referenceSellingPrice) {
    return api._post(`/skus/${skuId}/selling-price-preview`, {
      reference_selling_price: referenceSellingPrice,
    });
  },
  // 基准售价体检（阶段 4 工具 4）：偏差校验 + 过期巡检。
  // ⚠️ 这个接口很慢（带偏差时要扫订单事实表，单次可能几十秒），
  //    所以只允许运营**显式点击**时调用，绝不能挂在列表加载路径上。
  //    超时必须放宽：默认 30s 会把一次正常计算判成失败。
  checkSkuSellingPrice({ skuId, includeDeviation } = {}) {
    return api._get("/skus/selling-price-check", {
      params: {
        sku_id: skuId ?? undefined,
        include_deviation: includeDeviation ?? true,
      },
      timeout: 180000,
      // 关掉 axios 的自动重试：重试也是一次全量扫描，
      // 3 次重试 = 4 × 180s ≈ 12 分钟的转圈，比直接报错还糟。
      retryCount: 3,
    });
  },
  previewSkuDeletion(skuId) {
    return api._post(`/skus/${skuId}/deletion-preview`, {});
  },
  softDeleteSku(skuId, payload) {
    return api._post(`/skus/${skuId}/soft-delete`, payload);
  },
  restoreSku(skuId, payload) {
    return api._post(`/skus/${skuId}/restore`, payload);
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
  deleteProviderRule(id) {
    return api._delete(`/logistics-provider-rules/${id}`);
  },
  listLogisticsBills(params = {}) {
    return api._get("/logistics-bills", { params });
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
  // --- SKU 定价纪律规则（库龄档位） ---
  listSkuPricingPolicies(params = {}) {
    return api._get("/sku-pricing-policies", { params });
  },
  listCurrentSkuPricingPolicies() {
    return api._get("/sku-pricing-policies/current");
  },
  updateSkuPricingPolicy(minAgeDays, payload) {
    return api._put(`/sku-pricing-policies/${minAgeDays}`, payload);
  },
};
