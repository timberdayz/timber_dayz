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
  // 「重估利润」→「混合成本利润」：物流是真实账单、仓储是规则预估，不是全实际
  assert.match(source, /混合成本利润/);
  assert.match(source, /混合成本完整度/);
  assert.doesNotMatch(source, /重估利润/);
  assert.doesNotMatch(source, /重估完整度/);
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
  // 「实际仓储」列已删除：它恒为 null（系统里没有仓储费账单，只有规则预估），
  // 展示一个恒空列只会误导。回退信息折进「混合成本利润」的 tooltip。
  assert.doesNotMatch(source, /label="实际仓储"/);
  assert.match(source, /规则预估/);
  assert.doesNotMatch(source, /v-model="row\.expected_logistics_cost"/);
  assert.doesNotMatch(source, /v-model="row\.expected_storage_cost"/);
  assert.match(source, /transport_type: operatingQuery\.transport_type/);
  assert.doesNotMatch(source, /transport_type: row\.transport_type \|\| "sea"/);
});

test("平台 SKU 利润测算按 SPU 级联 SKU，并提供定价设置与仓储规则入口", () => {
  assert.match(source, /filteredOperatingSkus/);
  assert.match(source, /clearOperatingSkuOutsideSpu/);
  // 抽屉从「平台费率管理」升级为「定价设置」
  assert.match(source, /定价设置/);
  assert.match(source, /仓储规则/);
  assert.match(api, /listWarehouseStorageRules/);
  assert.match(api, /createWarehouseStorageRule/);
  assert.match(api, /updateWarehouseStorageRule/);
});

test("商品中心提供定价纪律规则表 API", () => {
  assert.match(api, /sku-pricing-policies/);
  assert.match(api, /listSkuPricingPolicies/);
  assert.match(api, /updateSkuPricingPolicy/);
});

test("商品中心把平台费率抽屉升级为定价设置", () => {
  assert.match(source, /定价设置/);
  assert.match(source, /库龄档位规则/);
  assert.match(source, /平台成本率/);
});

test("抽屉保存失败时读结构化错误原因而不是带错误码前缀的 message", () => {
  assert.match(source, /readApiErrorDetail/);
  assert.match(source, /detail\?\.reason/);
});

test("定价设置抽屉区分「成本率合计」与「底线基数」", () => {
  // 成本率合计（40.70%）只是成本结构展示，底线基数是 33.33%（默认达人佣金 + 平台其他成本）
  assert.match(source, /成本率合计/);
  assert.match(source, /底线基数/);
  // 必须带上「SKU 未单独设置达人佣金率时」这个限定语
  assert.match(source, /未单独设置/);
});

test("SKU 资料页展示定价底线四列", () => {
  assert.match(source, /当前可优惠/);
  assert.match(source, /滞销可优惠/);
  assert.match(source, /最低售价/);
  assert.match(source, /达人佣金率/);
  assert.match(source, /row\.current_discount_rate/);
  assert.match(source, /row\.clearance_max_discount_rate/);
  assert.match(source, /row\.min_selling_price_override/);
  assert.match(source, /row\.creator_commission_rate/);
});

test("SKU 保存剔除只读计算字段但保留可写字段", () => {  const section = source.slice(
    source.indexOf("const payloadSku"),
    source.indexOf("const validateSpu"),
  );
  assert.match(section, /delete payload\.current_discount_rate/);
  assert.match(section, /delete payload\.min_selling_price/);
  // 平台兜底值只是展示，不能回提交成「SKU 单独设置过」
  assert.match(section, /delete payload\.creator_commission_rate_fallback/);
  assert.doesNotMatch(section, /delete payload\.min_selling_price_override/);
  assert.doesNotMatch(section, /delete payload\.creator_commission_rate;/);
});

test("最低售价在覆盖值未保存时提示「保存后生效」", () => {
  // 只读值显示的是服务端已保存的生效值；运营改了输入框还没保存时，
  // 必须明确提示「保存后生效」，否则会被误读成「改了没生效」
  assert.match(source, /pendingOverride/);
  assert.match(source, /保存后生效/);
  assert.match(source, /pending-override/);
});

test("达人佣金率带 % 后缀且说明只放在表头", () => {
  // 输入框填的是百分数，界面必须有 % 才看得出「11 = 11%」
  const commission = source.slice(
    source.indexOf('label="达人佣金率"'),
    source.indexOf('label="售价来源"'),
  );
  assert.match(commission, /rate-suffix/);
  // 「留空表示不单独设置」不该每行重复一遍
  assert.doesNotMatch(commission, /pricing-tier-hint/);
  // 改成表头问号提示
  assert.match(source, /pricing-header/);
  assert.match(source, /留空表示不单独设置，按平台默认计算/);
});

test("利润测算页展示最低售价并拦截低于底线的预计售价", () => {
  assert.match(source, /row\.min_selling_price/);
  assert.match(source, /row\.current_discount_rate/);
  assert.match(source, /row\.clearance_max_discount_rate/);
  assert.match(source, /低于最低售价/);
  assert.match(source, /below_min_selling_price/);
  // 错误信封读取：结构化业务码在 error.detail（axios 拦截器挂载点），
  // 不是顶层 data.detail —— 断言这一点，防止有人改回读不到值的写法
  assert.match(source, /readApiErrorDetail/);
  assert.match(source, /detail\?\.code === "below_min_selling_price"/);
});

test("平台 SKU 利润测算保留候选接口预览并支持分页", () => {
  // ⚠️ 断言必须**限定在利润测算区域**：
  // 全文件的 /preview:\s*null/ 还会命中 SPU 删除预检的错误分支
  // （ProductCenter.vue 的 `preview: null, error: e.message`），
  // 那是有意义的错误语义，不能删。
  const operatingSection = source.slice(
    source.indexOf('label="平台 SKU 利润测算"'),
    source.indexOf('label="物流仓储管理"'),
  );
  assert.doesNotMatch(operatingSection, /preview:\s*null/);
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

// ---------------------------------------------------------------------------
// 阶段 0 · 稳定性修复（2026-11-06）
// 上游设计稿：docs/superpowers/specs/2026-11-06-product-center-caliber-naming-and-roi-design.md §5.4
// ---------------------------------------------------------------------------

test("9 个可编辑字段都会标脏，改动不会在保存时丢失", () => {
  // saveSpuRows / saveSkuRows 只提交 dirtyRows 里的行；没标脏的行根本不在 payload 里。
  // 用「字段 → 后面 260 字符」的切片来断言，失败时只报切片内容，不会把整个源码打出来。
  const cases = [
    ["spu_name", "spu"],
    ["category_l2_code", "spu"],
    ["biz_status", "spu"],
    ["owner_user_id", "spu"],
    ["sku_name", "sku"],
    ["specification", "sku"],
    ["weight_kg", "sku"],
    ["units_per_carton", "sku"],
  ];
  for (const [field, kind] of cases) {
    const at = source.indexOf(`v-model="row.${field}"`);
    assert.notEqual(at, -1, `找不到字段 ${field}`);
    const slice = source.slice(at, at + 260);
    assert.match(
      slice,
      new RegExp(`markDirty\\('${kind}', row\\)`),
      `${field} 应当触发 markDirty('${kind}', row)`,
    );
  }
  // 一级品类：清空二级 + 标脏必须合并成一个 handler（一个 el-select 只能挂一个 @change）
  assert.match(source, /onSpuL1CategoryChange/);
  assert.match(
    source,
    /onSpuL1CategoryChange = \(row\) => \{[\s\S]{0,200}category_l2_code = "";[\s\S]{0,200}markDirty\("spu", row\)/,
  );
  assert.doesNotMatch(source, /@change="row\.category_l2_code = ''"/);
});

test("物流批次体积换算有实现，且体积缺失会被显式提示而不是静默算 0", () => {
  assert.match(source, /const formatVolume = \(sku\) =>/);
  assert.match(source, /unit_volume_cbm/);
  assert.match(source, /hasVolume/);
  assert.match(source, /missingVolumeSkus/);
  assert.match(source, /单件体积未填/);
});

test("SPU 列表带出已软删的行，软删可恢复", () => {
  assert.match(source, /include_inactive: true/);
  assert.match(source, /spuRowClass/);
  assert.match(source, /spu-inactive-row/);
  // 「恢复」按钮 / 「删除」禁用 / 选中过滤 / 整行灰显 **全部**依赖 row.active。
  // 后端响应必须真的下发 active，否则这些判断恒为 false ⇒ 恢复按钮永远不出现。
  assert.match(source, /v-if="row\.active === false"[\s\S]{0,200}handleRestoreSpu/);
  assert.match(source, /row\.active === false \? "spu-inactive-row" : ""/);
  assert.match(api, /listSpus\(params = \{\}\)/);
  assert.match(api, /listSkus\(params = \{\}\)/);
});

test("仓储规则写入口按权限隐藏，operator 不会点了报 403", () => {
  assert.match(source, /canManagePlatformFee/);
  // 新增按钮
  const addAt = source.indexOf("addStorageRuleRow");
  assert.notEqual(addAt, -1);
  assert.match(source.slice(Math.max(0, addAt - 120), addAt), /v-if="canManagePlatformFee"/);
  // 操作列：整列 v-if（4 个按钮全都要 admin/manager/finance）
  const opAt = source.indexOf('label="操作" width="240"');
  assert.notEqual(opAt, -1);
  assert.match(
    source.slice(Math.max(0, opAt - 80), opAt),
    /<el-table-column v-if="canManagePlatformFee"/,
  );
  assert.match(source.slice(opAt, opAt + 400), /saveStorageRule/);
});

test("SKU 列表提供状态筛选，停用与在售不再混排", () => {
  assert.match(source, /v-model="skuQuery\.status"/);
  assert.match(source, /全部状态/);
  assert.match(source, /value="active"/);
  assert.match(source, /value="inactive"/);
});

test("利润测算页不再展示恒为空的实际仓储列", () => {
  assert.doesNotMatch(source, /label="实际仓储"/);
  // 实际物流折进混合成本利润的 tooltip
  assert.match(source, /实际物流|actual_logistics_cost/);
});

test("完整度列不再拿 configuration_status 兜底", () => {
  assert.doesNotMatch(source, /configuration_status/);
});

// ---------------------------------------------------------------------------
// 阶段 1 · ROI 只读层（2026-11-07）
// 上游设计稿：docs/superpowers/specs/2026-11-06-product-center-caliber-naming-and-roi-design.md §2.5
// ---------------------------------------------------------------------------

// 断言必须限定在「平台 SKU 利润测算」区域 —— SKU 资料页也有「最低售价」列
const operatingSection = source.slice(
  source.indexOf('label="平台 SKU 利润测算"'),
  source.indexOf('label="物流仓储管理"'),
);

test("利润测算页给出广告前贡献毛利率 / 保本ROI / 建议ROI 三个只读列", () => {
  assert.match(operatingSection, /label="广告前贡献毛利率"/);
  assert.match(operatingSection, /label="保本ROI"/);
  assert.match(operatingSection, /label="建议ROI"/);
  // 数据源在 preview 段（自由 dict，不改 Pydantic 契约）
  assert.match(
    operatingSection,
    /row\.preview\?\.expected\?\.advertising_contribution_margin_rate/,
  );
  assert.match(operatingSection, /row\.preview\?\.expected\?\.break_even_roi/);
  assert.match(operatingSection, /row\.preview\?\.expected\?\.suggested_roi_clamped/);
});

test("三个 ROI 列排在最低售价右侧、预计售价之前", () => {
  const floor = operatingSection.indexOf('label="最低售价"');
  const margin = operatingSection.indexOf('label="广告前贡献毛利率"');
  const breakEven = operatingSection.indexOf('label="保本ROI"');
  const suggested = operatingSection.indexOf('label="建议ROI"');
  const price = operatingSection.indexOf('label="预计售价"');
  assert.ok(floor >= 0 && margin > floor, "广告前贡献毛利率必须紧跟最低售价");
  assert.ok(breakEven > margin, "保本ROI 必须在广告前贡献毛利率之后");
  assert.ok(suggested > breakEven, "建议ROI 必须在保本ROI 之后");
  assert.ok(price > suggested, "三个 ROI 列必须在预计售价之前");
});

test("成本不全时 ROI 一律置灰并提示保本ROI 偏乐观", () => {
  // 成本不全 → pre_ad_profit 高估 → 保本ROI 偏松 → 运营真投广告就亏。
  // 这个守卫是阶段 1 的硬前提，没有它本阶段不能上线。
  assert.match(
    source,
    /const roiGuarded = \(row\) => row\.reference_cost_status !== "ready"/,
  );
  assert.match(operatingSection, /'roi-guarded': roiGuarded\(row\)/);
  assert.match(source, /成本不全，保本ROI 偏乐观/);
  // 缺失原因按三份清单分列（缺物流 / 缺仓储 / 缺体积）
  assert.match(source, /缺物流规则/);
  assert.match(source, /缺仓储规则/);
  assert.match(source, /缺 SKU 体积\/重量/);
});

test("ROI 列挂两条免责提示", () => {
  // ① 本表不预测销量（提价掉量模型看不见）
  // ② 平台报告 ROI 含自然/达人归因，达标 ≠ 赚钱
  assert.match(operatingSection, /本表不预测销量/);
  assert.match(operatingSection, /达标 ≠ 赚钱/);
});

test("建议 ROI 超过平台可填上限时提示广告空间不足并保留未封顶原值", () => {
  assert.match(operatingSection, /above_platform_ceiling/);
  assert.match(operatingSection, /广告空间不足/);
  // 未封顶原值必须能看到 —— 运营要知道自己离平台上限差多少
  assert.match(source, /未封顶原值/);
});

// ---------------------------------------------------------------------------
// 阶段 2.1 · 底线下沉到「SKU × 平台」
// ---------------------------------------------------------------------------

test("SKU 资料页提供「底线按平台」选择器", () => {
  // 底线是 SKU × 平台的量（Shopee 41.65% vs TikTok 27.27%）：
  // 不让运营选平台，界面上的底线就是"某个平台的底线"而运营不知道是谁的。
  assert.match(source, /skuPricingPlatform/);
  assert.match(source, /底线按平台/);
  // 选项来自经营维度里的销售平台，不是硬编码
  assert.match(source, /operatingDimensions\.platforms \|\| \[\]/);
});

test("SKU 列表按所选平台取底线", () => {
  const loadSkus = source.slice(
    source.indexOf("const loadSkus"),
    source.indexOf("const validateSku"),
  );
  assert.match(loadSkus, /platform_code: skuPricingPlatform\.value \|\| undefined/);
});

test("SKU 资料页说清底线口径与人工覆盖的作用域", () => {
  // ① 这条底线是按哪个平台的费率算的
  assert.match(source, /底线按 \{\{ skuPricingPlatform \|\| '默认平台' \}\} 的成本率计算/);
  // ② 人工覆盖是公司级的 —— 避免运营以为"在 TikTok 改的只影响 TikTok"
  assert.match(source, /人工覆盖是公司级的，对所有平台生效/);
});

test("利润测算页的最低售价说明按平台口径，不再说公司统一口径", () => {
  // 旧文案「公司统一口径，不随平台/仓库变化」在本阶段已经不成立 ——
  // 底线就是按平台算的，留着会直接误导运营。
  assert.doesNotMatch(source, /公司统一口径，不随平台\/仓库变化/);
  assert.match(operatingSection, /平台成本率计算，不同平台底线不同/);
});
