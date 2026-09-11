import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const source = readFileSync(
  resolve(root, "src/domains/business/views/ProductCenter.vue"),
  "utf8",
);
const api = readFileSync(resolve(root, "src/api/productCenter.js"), "utf8");

test("商品中心使用公司中文品类级联并移除成本假设入口", () => {
  assert.match(source, /一级品类/);
  assert.match(source, /二级品类/);
  assert.match(source, /categoryOptions|categories/);
  assert.doesNotMatch(source, /新增成本假设/);
  assert.doesNotMatch(source, /costAssumption|assumptionDialog/);
});

test("商品中心以表格行内新增和批量保存 SPU/SKU", () => {
  assert.match(source, /新增行/);
  assert.match(source, /保存变更/);
  assert.match(source, /bulk|saveSpuRows|saveSkuRows/);
  assert.match(api, /bulk/);
  assert.match(source, /bulkSaveSkus/);
  assert.match(source, /bulkSaveSpus/);
});

test("物流批次支持多采购单、规则自动带值和账单确认", () => {
  assert.match(source, /选择采购单/);
  assert.match(source, /计费方式/);
  assert.match(source, /敏感货/);
  assert.match(source, /账单总额/);
  assert.match(source, /confirmLogisticsBatch|confirmLogisticsBill/);
  assert.match(api, /logistics-provider-rules/);
  assert.match(api, /purchase-orders/);
  assert.match(api, /logistics-batches/);
});

test("物流批次先关联采购单再保存账单行，并使用账单费率字段", () => {
  assert.match(api, /saveLogisticsBatchPurchaseOrders/);
  assert.match(api, /purchase_order_ids/);
  assert.match(source, /敏感货 M/);
});

test("物流批次按服务商规则带出费率，并提示未映射的采购 SKU", () => {
  assert.match(source, /matchProviderRule/);
  assert.match(source, /applyRuleToBatchLines/);
  assert.match(source, /billing_unit_rate/);
  assert.match(source, /unmappedPurchaseSkus/);
  assert.match(source, /待映射/);
  assert.match(source, /sku_ids: \[sku.sku_id\]/);
});

test("编辑已有物流批次时保留 API 返回的采购单号关联", () => {
  assert.match(source, /typeof item === "string" \? item : item.po_id/);
  assert.doesNotMatch(source, /status: "completed"/);
});
