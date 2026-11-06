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
  // 阶段 3：旧名「当前可优惠 / 滞销可优惠」已改成「当前让利上限 / 清货让利上限」
  assert.match(source, /当前让利上限/);
  assert.match(source, /清货让利上限/);
  assert.doesNotMatch(source, /当前可优惠/);
  assert.doesNotMatch(source, /滞销可优惠/);
  assert.match(source, /最低售价/);
  assert.match(source, /达人佣金率/);
  assert.match(source, /row\.current_discount_rate/);
  assert.match(source, /row\.clearance_max_discount_rate/);
  // 阶段 2.1b：人工覆盖不再是 SKU 级的 row.min_selling_price_override，
  // 而是按平台分行的 item.min_selling_price_override。
  assert.match(source, /item\.min_selling_price_override/);
  assert.match(source, /row\.creator_commission_rate/);
});

test("SKU 保存剔除只读计算字段与已拆出的平台级覆盖值", () => {  const section = source.slice(
    source.indexOf("const payloadSku"),
    source.indexOf("const validateSpu"),
  );
  assert.match(section, /delete payload\.current_discount_rate/);
  assert.match(section, /delete payload\.min_selling_price/);
  // 平台兜底值只是展示，不能回提交成「SKU 单独设置过」
  assert.match(section, /delete payload\.creator_commission_rate_fallback/);
  // 阶段 2.1b：人工覆盖已从 SKU 主数据里拆出去（走平台级独立接口），
  // 留在保存载荷里会被判 422 或被静默丢弃 ⇒ 必须剔除。
  assert.match(section, /delete payload\.min_selling_price_override/);
  // 分平台底线数据是后端下发的只读结果，也不能回提交
  assert.match(section, /delete payload\.min_selling_price_by_platform/);
  assert.doesNotMatch(section, /delete payload\.creator_commission_rate;/);
});

test("最低售价在覆盖值未保存时提示「保存后生效」", () => {
  // 只读值显示的是服务端已保存的生效值；运营改了输入框还没保存时，
  // 必须明确提示「保存后生效」，否则会被误读成「改了没生效」
  assert.match(source, /pendingPlatformOverride/);
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
  // 阶段 3：「广告费率」改名「广告分成率」
  assert.match(source, /广告分成率/);
  assert.doesNotMatch(source, /广告费率/);
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

test("三个 ROI 列排在最低售价右侧、测算售价之前", () => {
  const floor = operatingSection.indexOf('label="最低售价"');
  const margin = operatingSection.indexOf('label="广告前贡献毛利率"');
  const breakEven = operatingSection.indexOf('label="保本ROI"');
  const suggested = operatingSection.indexOf('label="建议ROI"');
  // 阶段 3：「预计售价」改名「测算售价」
  const price = operatingSection.indexOf('label="测算售价"');
  assert.ok(floor >= 0 && margin > floor, "广告前贡献毛利率必须紧跟最低售价");
  assert.ok(breakEven > margin, "保本ROI 必须在广告前贡献毛利率之后");
  assert.ok(suggested > breakEven, "建议ROI 必须在保本ROI 之后");
  assert.ok(price > suggested, "三个 ROI 列必须在测算售价之前");
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
  // ② 人工覆盖是 SKU × 平台的量 —— 阶段 2.1b 之后不再说「公司级、对所有平台生效」
  assert.match(source, /人工覆盖按平台生效/);
  assert.doesNotMatch(source, /人工覆盖是公司级的/);
});

test("利润测算页的最低售价说明按平台口径，不再说公司统一口径", () => {
  // 旧文案「公司统一口径，不随平台/仓库变化」在本阶段已经不成立 ——
  // 底线就是按平台算的，留着会直接误导运营。
  assert.doesNotMatch(source, /公司统一口径，不随平台\/仓库变化/);
  assert.match(operatingSection, /平台成本率计算，不同平台底线不同/);
});

// ---------------------------------------------------------------------------
// 阶段 2.1b · 人工覆盖下沉到「SKU × 平台」
// ---------------------------------------------------------------------------

// SKU 资料页的「最低售价」列（第一个 label="最低售价" 就是它，
// 利润测算页那个在 operatingSection 之后）。
const skuPricingColumn = source.slice(
  source.indexOf('label="最低售价"'),
  source.indexOf('label="达人佣金率"'),
);

test("SKU 资料页的最低售价按平台分行", () => {
  // 底线是 SKU × 平台的量：TikTok 与 Shopee 的平台其他成本率差一截
  // （27.27% vs 41.65%）⇒ 同一件商品在两个平台有两条不同的底线，
  // 一行一个平台才看得出「我看到的这条底线是谁的」。
  assert.match(source, /skuPricingPlatformRows/);
  // 数据源是列表接口下发的分平台底线
  assert.match(source, /row\.min_selling_price_by_platform/);
  // 每个可定价平台渲染一行
  assert.match(skuPricingColumn, /v-for="item in skuPricingPlatformRows\(row\)"/);
  // 一行里有：平台名 + 该平台底线 + 该平台来源 + 该平台覆盖输入框
  assert.match(skuPricingColumn, /pricing-platform-name/);
  assert.match(skuPricingColumn, /item\.min_selling_price\b/);
  assert.match(skuPricingColumn, /item\.min_selling_price_source/);
  assert.match(skuPricingColumn, /item\.min_selling_price_is_override/);
  // 平台名取自经营维度；找不到就退回平台代码本身
  assert.match(source, /platformDisplayName/);
  assert.match(source, /hit\?\.name \|\| platformCode/);
  // 「重置为自动值」只在**该平台**有覆盖值时出现
  assert.match(
    skuPricingColumn,
    /v-if="item\.min_selling_price_is_override \|\| item\.min_selling_price_override != null"/,
  );
});

test("人工覆盖的保存走平台级独立接口", () => {
  // 接口：PATCH /api/skus/{sku_id}/pricing-override
  assert.match(api, /setSkuPricingOverride/);
  assert.match(api, /\/skus\/\$\{skuId\}\/pricing-override/);
  // 保存：载荷必须带 platform_code（人工覆盖是 SKU × 平台的量）
  assert.match(
    source,
    /setSkuPricingOverride\(row\.sku_id, \{\s*platform_code: item\.platform_code,\s*min_selling_price_override: Number\(value\)/,
  );
  // 「重置为自动值」= 同一个接口，min_selling_price_override 传 null
  assert.match(
    source,
    /setSkuPricingOverride\(row\.sku_id, \{\s*platform_code: item\.platform_code,\s*min_selling_price_override: null/,
  );
  // 覆盖值不再随 SKU 主数据一起标脏保存
  assert.doesNotMatch(skuPricingColumn, /markDirty\('sku', row\)/);
  assert.doesNotMatch(source, /v-model="row\.min_selling_price_override"/);
});

test("SKU 主数据保存载荷不再包含人工覆盖字段", () => {
  const section = source.slice(
    source.indexOf("const payloadSku"),
    source.indexOf("const validateSpu"),
  );
  // 后端已从 SkuCreateRequest / SkuUpdateRequest / SkuBulkItem 移除该字段，
  // 留在载荷里会被判 422 或被静默丢弃 ⇒ 必须剔除。
  assert.match(section, /delete payload\.min_selling_price_override/);
  assert.match(section, /delete payload\.min_selling_price_by_platform/);
  // 新增行也不再预置这个字段
  const blankSkuSection = source.slice(
    source.indexOf("const blankSku"),
    source.indexOf("const PRICING_SOURCE_LABELS"),
  );
  assert.doesNotMatch(blankSkuSection, /min_selling_price_override/);
});

test("文案不再声称人工覆盖是公司级的", () => {
  assert.doesNotMatch(source, /人工覆盖是公司级的/);
  assert.doesNotMatch(source, /对所有平台生效/);
  assert.match(source, /人工覆盖按平台生效/);
});

test("覆盖值保存失败给出可见报错，成功后刷新该行底线", () => {
  // 失败必须有可见提示（不能静默失败）
  assert.match(source, /pricingOverrideErrorText/);
  assert.match(source, /ElMessage\.error\(pricingOverrideErrorText\(error\)\)/);
  // 统一错误信封里的结构化业务码要能被读出来并翻译
  assert.match(source, /pricing_override_unknown_platform/);
  assert.match(source, /pricing_override_platform_not_sales/);
  // 成功后刷新**这一行**（整表重载会冲掉运营还没保存的其它字段编辑）
  assert.match(source, /const refreshSkuPricingRow = async \(row\) =>/);
  assert.match(source, /await refreshSkuPricingRow\(row\)/);
});

test("「底线按平台」选择器保留且仍参与列表取数", () => {
  assert.match(source, /v-model="skuPricingPlatform"/);
  assert.match(source, /placeholder="底线按平台"/);
  assert.match(source, /@change="loadSkus"/);
  const loadSkus = source.slice(
    source.indexOf("const loadSkus"),
    source.indexOf("const validateSku"),
  );
  assert.match(loadSkus, /platform_code: skuPricingPlatform\.value \|\| undefined/);
});

test("测算页提供目标ROI与平台报告ROI两个手填列", () => {
  assert.match(source, /label="目标ROI"/);
  assert.match(source, /label="平台报告ROI"/);
  assert.match(source, /v-model="row\.target_roi"/);
  assert.match(source, /v-model="row\.actual_roi"/);
});

test("ROI 投放输入进草稿与利润版本的载荷", () => {
  const payload = source.slice(
    source.indexOf("const operatingPayload"),
    source.indexOf("const clearOperatingSkuOutsideSpu"),
  );
  assert.match(payload, /target_roi: row\.target_roi \?\? null/);
  assert.match(payload, /actual_roi: row\.actual_roi \?\? null/);
});

test("平台报告ROI不预填，避免把上一轮投放事实悄悄带进新一版", () => {
  const load = source.slice(
    source.indexOf("const loadOperatingProfiles"),
    source.indexOf("const resetOperatingPage"),
  );
  // 目标ROI 是当前意图，存在经营档案里 ⇒ 预填
  assert.match(load, /target_roi: row\.target_roi \?\? null/);
  // 平台报告ROI 是某一次投放的历史事实 ⇒ 每轮重新填
  assert.match(load, /actual_roi: null/);
});

test("ROI 三色判定按保本线与建议ROI分档", () => {
  const verdict = source.slice(
    source.indexOf("const roiVerdict ="),
    source.indexOf("const targetRoiBelowBreakEven"),
  );
  assert.match(verdict, /亏损投放/);
  assert.match(verdict, /有利润但未达财务目标/);
  assert.match(verdict, /达标/);
  // 保本线算不出来 ⇒ 不判定（缺输入宁可不算）
  assert.match(verdict, /if \(breakEven == null\) return null/);
  // 目标 ROI 低于保本线单独标红
  assert.match(source, /const targetRoiBelowBreakEven =/);
  assert.match(source, /低于保本线/);
});

test("「达标」带归因警示且不给归因放大系数", () => {
  const tooltip = source.slice(
    source.indexOf("const roiVerdictTooltip ="),
    source.indexOf("const referenceLabelFee ="),
  );
  assert.match(tooltip, /归因可能虚高/);
  assert.match(tooltip, /自然流量和达人带货/);
  // 给不出数字时宁可不给，不能编
  assert.doesNotMatch(tooltip, /归因系数|放大系数\s*[:：=]/);
  assert.match(tooltip, /只提示、不给数字/);
});

test("保存利润版本时 ROI 护栏错误给出可执行提示", () => {
  assert.match(source, /below_break_even_roi/);
  assert.match(source, /roi_cost_incomplete/);
  // 护栏错误要排在「资料未完整」之前处理
  const save = source.slice(
    source.indexOf("const saveOperatingEstimate"),
    source.indexOf("const payloadSpu"),
  );
  const roiAt = save.indexOf("below_break_even_roi");
  const missingAt = save.indexOf("detail?.missing_fields");
  assert.ok(roiAt > 0, "必须处理 ROI 护栏错误码");
  assert.ok(missingAt > roiAt, "ROI 护栏错误必须排在资料未完整之前");
});

// ---------------------------------------------------------------------------
// 阶段 3 · 广告分成率降级 + 列改名（2026-11-07）
// ---------------------------------------------------------------------------

test("阶段 3 的列改名全部落地，旧名一个都不剩", () => {
  // 旧名以**列标签**的形态核对：像「参考物流规则」这种**规则名**不在改名范围内
  //（§8 改的是列名，不是 LogisticsProviderRule 这个业务对象的叫法）。
  const renames = [
    ["label=\"基准售价\"", "label=\"参考售价\""],
    ["label=\"测算售价\"", "label=\"预计售价\""],
    ["label=\"参考成本利润\"", "label=\"预计利润\""],
    ["label=\"广告分成率\"", "label=\"广告费率\""],
    ["label=\"平台佣金率\"", "label=\"平台费率\""],
    ["label=\"平台佣金\"", "label=\"平台费用\""],
    ["label=\"预估物流成本\"", "label=\"参考物流\""],
    ["label=\"预估仓储成本\"", "label=\"参考仓储\""],
    ["label=\"贴单费\"", "label=\"参考贴单费\""],
    ["label=\"物流货损率（SPU）\"", "label=\"继承货损率\""],
    ["label=\"退货损失率（SPU）\"", "label=\"继承退货损失率\""],
    ["label=\"当前让利上限\"", "label=\"当前可优惠\""],
    ["label=\"清货让利上限\"", "label=\"清货极限\""],
    ["label=\"清货让利上限\"", "label=\"滞销可优惠\""],
  ];
  for (const [label, old] of renames) {
    assert.match(source, new RegExp(label.replace(/"/g, '\\"')), `新名必须出现：${label}`);
    assert.doesNotMatch(
      source,
      new RegExp(old.replace(/"/g, '\\"')),
      `旧名必须消失：${old}`,
    );
  }
  // 「优惠券」补上限定语：是谁承担的
  assert.match(source, /优惠券（商家承担）/);
});

test("利润测算页不再有重复的「物流方式」列", () => {
  // 物流方式已经在顶部筛选器里选过了，表里再放一列是重复
  assert.doesNotMatch(operatingSection, /label="物流方式"/);
  // 顶部筛选器仍然保留（它是唯一的入口）
  assert.match(source, /operatingQuery\.transport_type/);
});

test("广告分成率降级为高级逃生口，默认折叠", () => {
  // 默认折叠：要显式展开才改得了
  assert.match(source, /const showAdRateEscape = ref\(false\)/);
  assert.match(source, /v-model="showAdRateEscape"/);
  assert.match(source, /v-if="showAdRateEscape"/);
  // 折叠态显示当前生效口径，不给输入框
  assert.match(source, /按目标ROI口径/);
});

test("广告分成率旁边永远并排显示等效目标 ROI", () => {
  assert.match(operatingSection, /等效目标ROI/);
  assert.match(
    operatingSection,
    /row\.preview\?\.expected\?\.equivalent_target_roi/,
  );
});

test("两个口径互斥：改广告分成率清掉目标 ROI，改目标 ROI 取消分成率口径", () => {
  // 两个输入填着就打架（后端只能取一个）⇒ 动了哪一个就以那个为准
  assert.match(source, /const onAdRateEscapeInput = \(row\) => \{/);
  assert.match(source, /row\.target_roi = null/);
  assert.match(source, /row\.adRateEscapeUsed = true/);
  assert.match(source, /const onTargetRoiInput = \(row\) => \{/);
  assert.match(source, /row\.adRateEscapeUsed = false/);
  // 提示语要说明发生了什么
  assert.match(source, /已改用广告分成率口径/);
});
