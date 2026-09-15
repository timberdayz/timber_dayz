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

test("历史不可选品类在商品中心可读但不能用于新的 SPU 分配", () => {
  assert.match(source, /is_selectable/);
  assert.match(source, /PET_DAILY/);
  assert.match(source, /disabled.*!cat\.is_selectable|:disabled="!cat\.is_selectable"/);
  assert.match(source, /cat\.status !== 'active'/);
  assert.match(source, /include_inactive/);
});

test("商品中心将平台 SKU 利润作为利润唯一工作入口", () => {
  assert.match(source, /平台 SKU 利润/);
  assert.match(source, /物流仓储管理/);
  assert.doesNotMatch(source, /SKU 成本资料/);
  assert.doesNotMatch(source, /基准预计利润/);
  assert.match(source, /operatingProfiles/);
  assert.match(api, /profit-preview/);
});

test("平台 SKU 利润使用平台仓库 SKU 粒度", () => {
  assert.match(source, /platform_code/);
  assert.match(source, /warehouse_code/);
  assert.doesNotMatch(source, /operatingQuery\.shop_id/);
  assert.doesNotMatch(source, /operatingQuery\.site_code/);
  assert.match(api, /sku-operating-profiles/);
  assert.match(api, /sku-operating-dimensions/);
});

test("平台 SKU 利润测算通过候选 SKU 自动加载而不是新增经营行", () => {
  assert.match(source, /平台 SKU 利润测算/);
  assert.match(source, /listPlatformSkuProfitCandidates/);
  assert.match(source, /previewOperatingRow/);
  assert.match(source, /预计广告费用/);
  assert.match(source, /重估利润/);
  assert.match(api, /platform-sku-profit\/candidates/);
  assert.match(api, /platform-sku-profit\/preview/);
});

test("物流规则和批次使用收货仓库及固定运输方式", () => {
  assert.match(source, /收货仓库/);
  assert.match(source, /海运/);
  assert.match(source, /空运/);
  assert.match(source, /铁路运输/);
  assert.doesNotMatch(source, /目的地.*el-input/);
});

test("SKU 资料按 CNY 维护采购成本、周转类型和参考仓储天数", () => {
  assert.match(source, /采购成本来源/);
  assert.match(source, /采购成本确认时间/);
  assert.match(source, /周转类型/);
  assert.match(source, /参考仓储天数/);
  assert.match(source, /fast.*30|30.*fast/);
  assert.match(source, /normal.*60|60.*normal/);
  assert.match(source, /slow.*90|90.*slow/);
  assert.doesNotMatch(source, /label="币种"/);
});

test("平台 SKU 利润测算按平台、仓库和运输方式自动计算参考成本", () => {
  assert.match(source, /v-model="operatingQuery\.transport_type"/);
  assert.match(source, /参考物流/);
  assert.match(source, /参考仓储/);
  assert.match(source, /未录入\/参考回退/);
  assert.doesNotMatch(source, /v-model="row\.expected_logistics_cost"/);
  assert.doesNotMatch(source, /v-model="row\.expected_storage_cost"/);
  assert.match(source, /transport_type: operatingQuery\.transport_type/);
  assert.doesNotMatch(source, /transport_type: row\.transport_type \|\| "sea"/);
});

test("平台 SKU 利润测算按 SPU 级联 SKU，并提供平台费率与仓储规则入口", () => {
  assert.match(source, /filteredOperatingSkus/);
  assert.match(source, /clearOperatingSkuOutsideSpu/);
  assert.match(source, /平台费率管理/);
  assert.match(source, /仓储规则/);
  assert.match(api, /listWarehouseStorageRules/);
  assert.match(api, /createWarehouseStorageRule/);
  assert.match(api, /updateWarehouseStorageRule/);
});

test("平台 SKU 利润测算保留候选接口预览并支持分页", () => {
  assert.doesNotMatch(source, /preview:\s*null/);
  assert.match(source, /page:\s*1/);
  assert.match(source, /page_size:\s*20/);
  assert.match(source, /const operatingTotal = ref\(0\)/);
  assert.match(source, /page:\s*operatingQuery\.page/);
  assert.match(source, /page_size:\s*operatingQuery\.page_size/);
  assert.match(source, /:total="operatingTotal"/);
  assert.match(source, /v-model:current-page="operatingQuery\.page"/);
  assert.match(source, /v-model:page-size="operatingQuery\.page_size"/);
});

test("仓储规则当前行保存后由服务端自动生成新版本", () => {
  assert.match(source, /保存（自动新版本）/);
  assert.doesNotMatch(source, /v-model="row\.unit_rate_cny"[^>]*:disabled="!row\.__new"/);
  assert.doesNotMatch(source, /v-model="row\.effective_from"[^>]*:disabled="!row\.__new"/);
});

test("物流服务商规则允许维护默认规则且前端不会任意选择同优先级费率", () => {
  assert.match(source, /v-model="row\.is_default"/);
  assert.match(source, /默认规则/);
  const matcher = source.slice(
    source.indexOf("const matchProviderRule"),
    source.indexOf("const applyRuleToLine"),
  );
  assert.match(matcher, /is_default/);
  assert.doesNotMatch(matcher, /\}\)\[0\] \|\| null/);
});

test("SKU 资料直接维护单件体积，箱规明确为件每箱", () => {
  assert.match(source, /单件体积 m³/);
  assert.match(source, /箱规（件\/箱）/);
  assert.doesNotMatch(source, /label="包装 cm"/);
  assert.doesNotMatch(source, /v-model="row\.package_length_cm"/);
});

test("测算页使用百分比输入并支持草稿与不完整提示", () => {
  assert.match(source, /广告费率/);
  assert.match(source, /%/);
  assert.match(source, /toPercent|fromPercent/);
  assert.match(source, /保存测算草稿/);
  assert.match(source, /savePlatformSkuProfitDraft/);
  assert.match(source, /missing_fields/);
});

test("仓储规则允许当前行保存为自动版本", () => {
  assert.match(source, /storage_rule_versioned|新版本/);
  assert.match(source, /__original/);
  assert.doesNotMatch(source, /v-model="row\.unit_rate_cny"[^\n]*:disabled="!row\.__new"/);
});
