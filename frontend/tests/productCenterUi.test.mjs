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
  // ⚠️ 「不许有币种入口」针对**全站**：采购成本一律按 CNY 维护；
  //    尾程费率（口径 2026-11-17 归一）也**只填人民币等值** ——
  //    照抄新币数字会被当成人民币 ⇒ 尾程少算好几倍 ⇒ 成本底线偏低 ⇒ 漏钱。
  const skuSection = source.slice(
    source.indexOf('label="SKU 资料"'),
    source.indexOf('label="平台 SKU 利润测算"'),
  );
  assert.ok(skuSection.length > 0, "没定位到 SKU 资料 tab");
  assert.doesNotMatch(skuSection, /label="币种"/);
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
    source.indexOf('label="基准售价来源"'),
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
    ["weight_tier_code", "sku"],
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
  // ⚠️ 参数名必须是 include_soft_deleted（不是 include_inactive）——
  //    「已删除」与「停用」在这个域里是两件事，同名会让人以为口径一致。
  assert.match(source, /include_soft_deleted: true/);
  assert.match(source, /spuRowClass/);
  assert.match(source, /spu-inactive-row/);
  // 「恢复」按钮 / 「删除」禁用 / 选中过滤 / 整行灰显 **全部**依赖 row.active。
  // 后端响应必须真的下发 active，否则这些判断恒为 false ⇒ 恢复按钮永远不出现。
  assert.match(source, /v-if="row\.active === false"[\s\S]{0,200}handleRestoreSpu/);
  assert.match(source, /row\.active === false \? "spu-inactive-row" : ""/);
  assert.match(api, /listSpus\(params = \{\}\)/);
  assert.match(api, /listSkus\(params = \{\}\)/);
});

test("SKU 行展示归属生效日 —— 归属是一段有时效的关联，不是一个字段", () => {
  // 「SKU 属于哪个 SPU」不是 SKU 身上的一个字段，而是**一段归属关系在今天的落点**。
  // 只显示编码 ⇒ 运营看不到「这个货是什么时候挂到这个款上的」「换过几次款」。
  assert.match(source, /spu_effective_from/);
  assert.match(source, /spu-binding-since/);
  // 生效日必须挂在 **SKU 表**的 SPU 单元格里（跟着编码走，不是散落在别处）
  const skuTableAt = source.indexOf('class="flat-table sku-table"');
  assert.notEqual(skuTableAt, -1);
  assert.match(
    source.slice(skuTableAt, skuTableAt + 4000),
    /spu_effective_from/,
  );
});

test("SKU 存量行的 SPU 单元格可编辑 —— 归属关系双向可达", () => {
  const skuTableAt = source.indexOf('class="flat-table sku-table"');
  assert.notEqual(skuTableAt, -1);
  const seg = source.slice(skuTableAt, skuTableAt + 6000);

  // ⚠️ 以前存量行的 SPU 单元格是**只读**的（v-else readonly-cell），
  //    改归属只能从「SPU 管理」tab 的抽屉单向进入 ⇒ 归属关系单向可达。
  assert.doesNotMatch(
    seg,
    /v-else class="readonly-cell"[^>]*>\s*\{\{ row\.spu/,
    "存量行的 SPU 单元格仍是只读 —— 归属关系还是单向可达",
  );

  // 换款必须走已有的批量保存通道（bulk_save_skus），不许另开一条写入路径。
  assert.match(source, /const onSkuSpuChange = \(row\) =>/);
  assert.match(source, /@change="onSkuSpuChange\(row\)"/);
  assert.match(source, /markDirty\("sku", row\)/);

  // 候选集必须用**可绑定口径**（assignable）—— 赋值是外键，不能造出挂不上的款。
  assert.match(seg, /spuAssignable/);
  // 存量行当前挂着的款要补进候选里，否则运营打开下拉看不到自己那一行的值。
  assert.match(source, /spuAssignableOptions/);
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

test("ROI 四列拆开：目标/平台报告属决策输入，保本/建议属定价结果", () => {
  // 阶段 6 之前：三列结果（毛利率/保本/建议）必须排在「测算售价」之前。
  // 阶段 6 起列重排，四段式把 ROI 拆成两段：
  //   决策输入段 = 测算售价 → 目标ROI → 平台报告ROI（运营要填的）
  //   定价结果段 = 当前让利上限 → 清货让利上限 → 最低售价 → 广告前贡献毛利率
  //                 → 保本ROI → 建议ROI（系统算出来的）
  // ⚠️ 两段之间的相对序是业务约束，不能因为重排弄丢：
  //   运营先填输入、再读结果；结果段内部的 ROI 相对序也不变。
  const price = operatingSection.indexOf('label="测算售价"');
  const target = operatingSection.indexOf('label="目标ROI"');
  const reported = operatingSection.indexOf('label="平台报告ROI"');
  const discount = operatingSection.indexOf('label="当前让利上限"');
  const floor = operatingSection.indexOf('label="最低售价"');
  const margin = operatingSection.indexOf('label="广告前贡献毛利率"');
  const breakEven = operatingSection.indexOf('label="保本ROI"');
  const suggested = operatingSection.indexOf('label="建议ROI"');
  // 决策输入段
  assert.ok(price >= 0 && target > price, "目标ROI 必须紧跟测算售价");
  assert.ok(reported > target, "平台报告ROI 必须在目标ROI 之后");
  // 优惠券列已移除（2026-11-16 口径归一：商家实收 = 测算售价，不再二次扣券）
  assert.doesNotMatch(operatingSection, /优惠券/);
  // 输入段整体在结果段之前
  assert.ok(discount > reported, "决策输入段必须排在定价结果段之前");
  assert.ok(floor > discount, "最低售价必须在当前让利上限之后");
  // 结果段内部的 ROI 相对序（阶段 1 起就有，不能丢）
  assert.ok(margin > floor, "广告前贡献毛利率必须紧跟最低售价");
  assert.ok(breakEven > margin, "保本ROI 必须在广告前贡献毛利率之后");
  assert.ok(suggested > breakEven, "建议ROI 必须在保本ROI 之后");
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
  // 优惠券列整体移除（2026-11-16 口径归一：商家实收 = 测算售价）
  assert.doesNotMatch(source, /优惠券（商家承担）/);
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

// ---------------------------------------------------------------------------
// 阶段 4 · 基准售价治理（前端部分，2026-11-07）
// ---------------------------------------------------------------------------

test("基准售价来源改成枚举下拉，只留三档", () => {
  // 自由文本来源会被后端的枚举校验直接 422，历史脏值也没法归一化
  assert.match(source, /const SELLING_PRICE_SOURCE_OPTIONS = \[/);
  assert.match(source, /value: "platform_listing", label: "平台挂牌价"/);
  assert.match(source, /value: "erp", label: "ERP 价"/);
  assert.match(source, /value: "manual", label: "人工填写"/);
  const sourceColumn = source.slice(
    source.indexOf('label="基准售价来源"'),
    source.indexOf('label="周转类型"'),
  );
  assert.match(sourceColumn, /<el-select v-model="row\.selling_price_source"/);
  assert.match(sourceColumn, /v-for="option in SELLING_PRICE_SOURCE_OPTIONS"/);
  // 不能再是自由文本输入框
  assert.doesNotMatch(sourceColumn, /<el-input v-model="row\.selling_price_source"/);
});

test("列表补齐确认日期、售价账龄与是否过期三列", () => {
  assert.match(source, /label="确认日期"/);
  assert.match(source, /label="售价账龄\(天\)"/);
  assert.match(source, /label="是否过期"/);
  assert.match(source, /formatConfirmedAt\(row\.selling_price_confirmed_at\)/);
  assert.match(source, /row\.selling_price_age_days/);
  assert.match(source, /row\.selling_price_stale/);
  // 过期要标红
  assert.match(source, /row\.selling_price_stale \? "已过期" : "正常"/);
  assert.match(source, /:type="row\.selling_price_stale \? 'danger' : 'success'"/);
  // 确认日期超过 90 天要标黄（与「是否过期」列的标红是两件事）
  assert.match(source, /'stale-date': row\.selling_price_stale/);
  assert.match(source, /\.stale-date \{/);
  assert.match(source, /\.stale-hint \{/);
});

test("基准售价改动即时调预览接口，且只对已保存的 SKU 调", () => {
  assert.match(api, /previewSkuSellingPrice/);
  assert.match(api, /selling-price-preview/);
  assert.match(source, /@input="scheduleSellingPricePreview\(row\)"/);
  assert.match(
    source,
    /@change="markDirty\('sku', row\); scheduleSellingPricePreview\(row\)"/,
  );
  const schedule = source.slice(
    source.indexOf("const scheduleSellingPricePreview"),
    source.indexOf("const runSellingPricePreview"),
  );
  // 新增行还没落库 ⇒ 不调（后端没有这条 SKU，也没有「当前值」可比）
  assert.match(schedule, /if \(!key\) return;/);
  // 输入防抖：别每敲一下就请求一次后端
  assert.match(source, /const SELLING_PRICE_PREVIEW_DEBOUNCE_MS = 300/);
});

test("预览展示各平台最低售价的当前→预览变化并标明原因", () => {
  assert.match(source, /最低售价将从 /);
  assert.match(source, /const sellingPriceChangeText = /);
  // 原因复用同一份来源标签字典，不另造一份
  assert.match(
    source,
    /sourceLabel: item\.source_preview \? pricingSourceLabel\(item\.source_preview\) : ""/,
  );
  // 抬价超过 20% 才提示（阈值与后端一致，不在前端另立口径）
  assert.match(source, /const SELLING_PRICE_PREVIEW_WARN_PCT = 20/);
  // 预览只是假设，必须说清「保存后才会生效」
  assert.match(source, /保存后生效/);
});

test("有人工覆盖的平台不能说成「涨到 63」", () => {
  assert.match(
    source,
    /const SELLING_PRICE_OVERRIDE_LOCKED_TEXT = "该平台已有人工覆盖，改基准售价不生效"/,
  );
  const preview = source.slice(
    source.indexOf("const applySellingPricePreview"),
    source.indexOf("const scheduleSellingPricePreview"),
  );
  assert.match(preview, /const locked = !!item\.override_locked/);
  assert.match(preview, /lockedText: SELLING_PRICE_OVERRIDE_LOCKED_TEXT/);
});

test("预览失败静默降级：清掉旧结果，不弹错误框也不打断输入", () => {
  const runner = source.slice(
    source.indexOf("const runSellingPricePreview"),
    source.indexOf("const formatConfirmedAt"),
  );
  assert.match(runner, /state\.platforms = \[\];/);
  assert.match(runner, /state\.warnings = \[\];/);
  assert.doesNotMatch(runner, /ElMessage/);
  assert.doesNotMatch(runner, /ElMessageBox/);
});

test("连续改价时旧预览结果不能盖掉新的", () => {
  const runner = source.slice(
    source.indexOf("const runSellingPricePreview"),
    source.indexOf("const formatConfirmedAt"),
  );
  assert.match(runner, /const seq = state\.seq \+ 1;/);
  assert.match(runner, /if \(state\.seq !== seq\) return;/);
});

test("基准售价巡检是显式按钮触发，且带 loading 态", () => {
  assert.match(api, /checkSkuSellingPrice/);
  assert.match(api, /selling-price-check/);
  // 接口很慢，超时必须放宽，否则正常计算会被判成失败
  assert.match(api, /timeout: 180000/);
  assert.match(source, /@click="runSellingPriceCheck"/);
  assert.match(source, /:loading="sellingPriceCheck\.loading"/);
  // 绝不能挂在列表加载路径上：那会把每次刷新都变成一次全表扫描
  const load = source.slice(
    source.indexOf("const loadSkus"),
    source.indexOf("const refreshSkuPricingRow"),
  );
  assert.doesNotMatch(load, /runSellingPriceCheck|checkSkuSellingPrice/);
});

test("巡检结果分三类，「算不出偏差」不等于没问题", () => {
  assert.match(source, /title="算不出偏差 ≠ 没问题"/);
  assert.match(source, /sellingPriceCheckGroups/);
  const groups = source.slice(
    source.indexOf("const sellingPriceCheckGroups"),
    source.indexOf("const SELLING_PRICE_UNVERIFIED_REASONS"),
  );
  assert.match(groups, /exceeds_threshold/);
  assert.match(groups, /item\.stale/);
  assert.match(groups, /available === false/);
  // 三个计数都要露出来
  assert.match(source, /deviation_count/);
  assert.match(source, /stale_count/);
  assert.match(source, /unverified_count/);
});

test("服务端算出来的基准售价字段不回提交", () => {
  const section = source.slice(
    source.indexOf("const payloadSku"),
    source.indexOf("const validateSpu"),
  );
  assert.match(section, /delete payload\.selling_price_age_days/);
  assert.match(section, /delete payload\.selling_price_stale/);
  assert.match(section, /delete payload\.selling_price_source_cleaned_at/);
  assert.match(section, /delete payload\.selling_price_confirmed_at/);
});

// ---------------------------------------------------------------------------
// 阶段 6 · 仓维度落地与前端列重排（2026-11-22）
// 方案：docs/superpowers/plans/2026-11-22-product-center-warehouse-dimension-implementation-plan.md
// ---------------------------------------------------------------------------

test("测算表左侧固定三列：SPU / ERP SKU / 商品名称", () => {
  const fixedLeft = [...operatingSection.matchAll(/<el-table-column[^>]*fixed="left"[^>]*>/g)].map(
    (m) => m[0],
  );
  assert.equal(fixedLeft.length, 3, "左侧固定列必须正好三列");
  assert.match(fixedLeft[0], /label="SPU"/);
  assert.match(fixedLeft[1], /label="ERP SKU"/);
  assert.match(fixedLeft[2], /label="商品名称"/);
  // 固定列必须真的在最左边：第一段（非固定的采购成本）排在它们之后
  const lastFixed = operatingSection.lastIndexOf('fixed="left"');
  const firstFact = operatingSection.indexOf('class-name="seg-fact"');
  assert.ok(lastFixed < firstFact, "固定三列必须排在所有非固定列之前");
});

test("测算表按「事实 → 输入 → 结果 → 成本」四段分区", () => {
  const segAt = (cls) => operatingSection.indexOf(`class-name="${cls}"`);
  const fact = segAt("seg-fact");
  const input = segAt("seg-input");
  const result = segAt("seg-result");
  const cost = segAt("seg-cost");
  assert.ok(fact >= 0, "必须有事实段");
  assert.ok(input > fact, "决策输入段必须在事实段之后");
  assert.ok(result > input, "定价结果段必须在决策输入段之后");
  assert.ok(cost > result, "成本明细段必须在定价结果段之后");
  // 表头也要上色 —— 只在数据行着色，运营扫一眼表头认不出分段
  assert.match(operatingSection, /label-class-name="seg-fact"/);
  assert.match(operatingSection, /label-class-name="seg-input"/);
  assert.match(operatingSection, /label-class-name="seg-result"/);
  assert.match(operatingSection, /label-class-name="seg-cost"/);
  // 图例：告诉运营这四段分别是什么
  assert.match(source, /segment-legend/);
  assert.match(source, /标识与事实/);
  assert.match(source, /决策输入/);
  assert.match(source, /定价结果/);
  assert.match(source, /成本明细与利润/);
});

test("事实段的顺序是采购成本 → 基准售价 → 竞品价格（用户从左到右的工作顺序）", () => {
  const cost = operatingSection.indexOf('label="采购成本"');
  const base = operatingSection.indexOf('label="基准售价"');
  const competitor = operatingSection.indexOf('label="竞品价格"');
  assert.ok(cost >= 0 && base > cost, "采购成本必须在基准售价之前");
  assert.ok(competitor > base, "竞品价格必须在基准售价之后");
});

test("测算表给出仓级库龄列：当前所选仓的库龄 + 其它仓的库龄", () => {
  assert.match(operatingSection, /label="库龄（仓）"/);
  assert.match(source, /const currentWarehouseRestockDays = \(row\)/);
  assert.match(source, /const currentWarehouseLabel = \(row\)/);
  assert.match(source, /const otherWarehouseRestocks = \(row\)/);
  // 页面显示的库龄必须与底线依据的库龄同源 —— 数字对不上运营会以为系统坏了
  assert.match(source, /pricing_days_since_restock/);
  // 其它仓按库龄倒序：老的排前面，先看到最该处理的
  assert.match(source, /\(b\.days_since_restock \?\? -1\) - \(a\.days_since_restock \?\? -1\)/);
});

test("测算表给出跨仓提示，且只提示不改价", () => {
  assert.match(operatingSection, /label="跨仓提示"/);
  assert.match(operatingSection, /row\.warehouse_divergence/);
  assert.match(source, /warehouse_divergence\.suggestion/);
  // 提示的方向是「调拨」，不是「降价」—— 系统不越权替运营做调拨决策
  assert.match(source, /调拨/);
});

// ---------------------------------------------------------------------------
// 阶段 7 · 当前仓库存（2026-11-08）
//
// 「这个仓还剩多少货」和「这批货压了多久」是两件事：
// 零库存 = 已清仓，是**事实**，必须显式标出来，不能让运营误读成缺数据。
// ---------------------------------------------------------------------------

test("测算表给出「当前仓库存」列，与「库龄（仓）」并列放在事实段", () => {
  assert.match(operatingSection, /label="当前仓库存"/);
  // 库存是事实段的一列，和库龄放在一起读
  assert.match(
    operatingSection,
    /label="当前仓库存"[^>]*class-name="seg-fact"/,
  );
  const stockAt = operatingSection.indexOf('label="当前仓库存"');
  const ageAt = operatingSection.indexOf('label="库龄（仓）"');
  assert.ok(stockAt >= 0 && ageAt > stockAt, "当前仓库存必须在库龄列之前或紧邻其后");
});

test("当前仓库存把「已清仓」显式标出来，而不是当成缺数据", () => {
  assert.match(source, /const currentWarehouseStockLabel = \(row\)/);
  assert.match(source, /已清仓/);
  // 四种状态分得开：在卖 / 已清仓 / 这个仓没这货 / 取不到
  assert.match(source, /"in_stock"/);
  assert.match(source, /"cleared"/);
  assert.match(source, /"no_record"/);
  assert.match(source, /"unavailable"/);
});

test("「仅有库存」筛选默认打开，且在后端做", () => {
  // 默认打开：测算表是"给还在卖的货定价"的表
  assert.match(source, /only_in_stock: true/);
  assert.match(operatingSection, /v-model="operatingQuery\.only_in_stock"/);
  // 筛选必须走后端 —— 前端筛只筛当前页，总数对不上、翻页会漏行
  assert.match(
    source,
    /only_in_stock: operatingQuery\.only_in_stock/,
  );
});
// ---------------------------------------------------------------------------
// 批次 4 · 尾程配送费（2026-11-16）
// ---------------------------------------------------------------------------

test("尾程费率可维护：平台 × 仓 × 重量段 → 单件尾程费", () => {
  // 尾程是必付成本：没有可维护的入口，业务就没法把费率录进来
  // ⇒ 尾程算不出来 ⇒ 利润链整条算不出来（不是按 0 计）。
  assert.match(api, /listDeliveryRateRules/);
  assert.match(api, /createDeliveryRateRule/);
  assert.match(api, /updateDeliveryRateRule/);
  assert.match(api, /deleteDeliveryRateRule/);
  assert.match(source, /新增尾程费率/);
  assert.match(source, /尾程配送费/);
});

test("定价设置里能维护尾程占收入比（尾程进底线的拆分基准）", () => {
  assert.match(source, /delivery_cost_rate_pct/);
  assert.match(source, /delivery_cost_rate: fromPercent/);
  // 口径说明必须写在界面上：为什么留空就不进底线
  assert.match(source, /尾程占收入比/);
});

test("测算页说清尾程有没有进成本底线", () => {
  // 尾程进底线必须成对（分子加尾程 ⇔ 分母剔残差里那份），
  // 只进一边就是重复扣 —— 界面必须让运营看得见当前是哪种状态。
  assert.match(source, /已计入底线/);
  assert.match(source, /未计入底线/);
  assert.match(source, /delivery_cost_in_cost_floor/);
});

test("SKU 资料页的底线与测算页同口径：按当前仓算尾程", () => {
  assert.match(source, /warehouse_code: operatingQuery\.warehouse_code \|\| undefined/);
});

// ---------------------------------------------------------------------------
// 尾程费率的录入体验 + 币种护栏（2026-11-17）
// ---------------------------------------------------------------------------

test("尾程费率按人民币等值入账（口径 2026-11-17 归一：人工填的就是人民币）", () => {
  // 平台价目表常是外币（Shopee SG = SGD），而尾程计算链**不读汇率** ——
  // 照抄新币数字当人民币 = 尾程少算 5 倍 ⇒ 成本底线偏低 ⇒ 直接漏钱。
  // ⇒ 录入界面**只让人填人民币等值**（外币自行折算，原币写备注留档）；
  //    界面不再有汇率层 —— 那层壳反而制造「照抄外币」的机会。
  assert.match(source, /label="单件尾程费（元）"/);
  assert.doesNotMatch(source, /label="原币单价"/);
  assert.doesNotMatch(source, /label="汇率→人民币"/);
  // 入库一律人民币等值
  assert.match(source, /currency: "CNY"/);
  assert.match(source, /unit_price: row\.unit_price/);
});

test("尾程费率支持批量新增：照一张价目表一次录完", () => {
  assert.match(source, /批量新增尾程费率/);
  assert.match(source, /deliveryBatchRows/);
  assert.match(source, /submitDeliveryBatch/);
});

test("尾程费率按重量段录：同一「平台 × 仓 × 段」不许填两行", () => {
  // 批次 6：重量段是**全局一套**的，段与段之间不会重叠 ⇒ 不再有「区间重叠」问题；
  // 真正要拦的是「同一个平台 × 仓 × 段填了两行当期」⇒ 选档歧义 ⇒ 系统算不出来。
  assert.match(source, /deliveryTierDuplicateHint/);
  assert.doesNotMatch(source, /deliveryIntervalsOverlap/);
  // 重量段从全局段表里选，不手工填上下限。
  assert.match(source, /listWeightTiers/);
  assert.doesNotMatch(source, /label="重量下限 kg"/);
  assert.doesNotMatch(source, /label="重量上限 kg"/);
});

test("尾程费率可停用/启用：停用比删除安全（历史留痕）", () => {
  assert.match(source, /toggleDeliveryRuleStatus/);
  assert.match(source, /停用/);
  assert.match(source, /启用/);
});

test("尾程费率改价走新版本（POST），不覆盖历史行", () => {
  // 费率版本化只进不退：改价 = 旧行闭区间 + 新行今天起生效。
  // 若走 PATCH 直接改单价 ⇒ 历史行被覆盖 ⇒ 事后对不上「当时按多少钱算的」。
  assert.match(source, /deliveryRuleCreatePayload/);
  assert.match(source, /deliveryRuleUpdatePayload/);
  assert.match(source, /已按新价开新版本/);
});

test("平台没配尾程占收入比时，费率页要提醒尾程不进底线", () => {
  assert.match(source, /deliveryPlatformSplitHint/);
  assert.match(source, /尾程占收入比/);
});

// ---------------------------------------------------------------------------
// 批次 5 遗留收口：头程账单内的分段改名（2026-11-16）
// ---------------------------------------------------------------------------

test("头程账单里的 last_mile_cost 改名成「头程末端派送」，不再叫「尾程」", () => {
  // ⚠️ 它是**头程账单内**的分段（港 → 仓），**不是买家快递**。
  //    商品中心的新概念「尾程配送费」= 仓 → 买家那段快递费。
  //    同一个界面里两个都叫「尾程」⇒ 运营会把两笔不同的钱当成同一笔。
  assert.match(source, /label="头程末端派送"/);
  assert.match(source, /v-model="row\.last_mile_cost"/);
  // 旧的「尾程」列名必须已经消失（注意：不能误伤「尾程配送费」）
  assert.doesNotMatch(source, /label="尾程"/);
});

test("改名后仍能看出头程账单三段与尾程配送费的区别", () => {
  // 界面上必须写清区别，否则改名等于没改
  assert.match(source, /头程末端派送/);
  assert.match(source, /尾程配送费/);
});

// ---------------------------------------------------------------------------
// 批次 6：重量段化 + 包邮开关（2026-11-17）
// ---------------------------------------------------------------------------

test("SKU 资料页按重量段选，不填精确重量", () => {
  // 承运商按重量段定价 ⇒ SKU 不称重、只报「落在哪一段」。
  const skuSection = source.slice(
    source.indexOf('label="SKU 资料"'),
    source.indexOf('label="平台 SKU 利润测算"'),
  );
  assert.match(skuSection, /label="重量段"/);
  assert.match(skuSection, /v-model="row.weight_tier_code"/);
  assert.doesNotMatch(skuSection, /label="重量 kg"/);
  assert.doesNotMatch(skuSection, /row.weight_kg/);
});

test("重量段定义全局一套：SKU 页与费率页读同一份段表", () => {
  assert.match(source, /listWeightTiers/);
  assert.match(source, /weightTiers/);
  // 段表是唯一真源 ⇒ 页面上不许手工填重量上下限。
  assert.doesNotMatch(source, /label="重量下限 kg"/);
  assert.doesNotMatch(source, /label="重量上限 kg"/);
});

test("测算页逐个 SKU 切换包邮（跨境电商不是默认包邮）", () => {
  // ⚠️ 这是**经营选择**：同一平台上有的 listing 包邮、有的不包邮。
  assert.match(source, /onFreeShippingChange/);
  assert.match(source, /setSkuFreeShipping/);
  assert.match(source, /label="包邮"/);
  assert.match(source, /v-model="row.free_shipping"/);
});

test("不包邮时界面要说清尾程不计入成本底线", () => {
  assert.match(source, /买家付运费/);
  assert.match(source, /不包邮/);
});

test("缺失原因换成重量段口径", () => {
  assert.match(source, /missing_weight_tier/);
  assert.match(source, /missing_delivery_rate_for_tier/);
});

test("定价设置抽屉自带平台选择器，平台身份不再靠外部筛选条件", () => {
  // ⚠️ 这是「定价设置是空的」的根因：平台成本率 tab 的「平台」原来是只读文本，
  // 平台身份靠测算页的 operatingQuery.platform_code 隐式传递 ⇒
  // 从 SKU 资料页进抽屉时永远是一个空壳（费率全空、来源全空），
  // 而保存又会把值写到**别的**平台行上（静默写错平台）。
  assert.match(source, /v-model="pricingDrawer\.form\.platform_code"/);
  assert.match(source, /pricingDrawer\.form\.platform_code/);
  assert.doesNotMatch(source, /label="平台"><span>/);
});

test("保存平台成本率只写抽屉里选中的平台，没选平台就提示", () => {
  // 写入目标必须来自**抽屉表单**，不是页面上任何一个筛选条件。
  assert.match(source, /const platformCode = pricingDrawer\.form\.platform_code/);
  assert.match(source, /updatePlatformFeeRate\(platformCode/);
  assert.doesNotMatch(source, /updatePlatformFeeRate\(operatingQuery\.platform_code/);
  // 没有平台必须提示，不许静默 return（静默 = 运营以为存上了，其实没存）。
  assert.match(source, /请先选择平台/);
});

test("两个入口各叫各的：库龄档位规则 / 平台成本率", () => {
  assert.match(source, />库龄档位规则</);
  assert.match(source, />平台成本率</);
  // 抽屉标题保留「定价设置」（它是两个子页的容器），但按钮不再都叫它。
  assert.doesNotMatch(source, />定价设置</);
});

test("尾程费率录入只填人民币，不再让运营填原币与汇率", () => {
  // 库里存的是人民币等值，界面也只让人填人民币 ——
  // 照抄外币价目表（SGD 2.87）会被当成 2.87 元人民币 ⇒ 尾程少算 5 倍 ⇒ 漏钱。
  assert.match(source, /label="单件尾程费（元）"/);
  assert.doesNotMatch(source, /label="原币单价"/);
  assert.doesNotMatch(source, /label="币种"/);
  assert.doesNotMatch(source, /label="汇率→人民币"/);
  // 前端不再做任何折算（后端契约本来就只收 CNY）。
  assert.doesNotMatch(source, /exchange_rate/);
  assert.doesNotMatch(source, /deliveryRuleConvertedCny/);
});

test("尾程费率按「平台 × 仓」卡片式维护，卡内列出全局段表的全部段", () => {
  // 业务理由：一行一条的表格里改一档价要先用眼睛找那一行（平台/仓/段三列并排），
  // 且平台与仓在存量行上是禁用的 ⇒ 找错行、改错行风险高。
  assert.match(source, /deliveryCardForm/);
  assert.match(source, /deliveryCardRows/);
  assert.match(source, /deliveryCardTiers/);
  // 卡片定位：平台 + 仓两个选择器，切换即换整卡。
  assert.match(source, /deliveryCardForm\.platform_code/);
  assert.match(source, /deliveryCardForm\.warehouse_code/);
  // 缺价的段在卡上看得见（不必等系统报错才知道缺料）。
  assert.match(source, /deliveryCardTierMissing/);
  // 一次保存整张卡。
  assert.match(source, /saveDeliveryCard/);
});

test("批量铺完尾程费率后回到卡片视图，方便核对与微调", () => {
  // 批量只是铺价的手段，不是终点 —— 铺完不回卡片，后续修改仍然困难。
  assert.match(source, /批量新增尾程费率/);
  assert.match(source, /deliveryCardForm\.platform_code = /);
  assert.match(source, /deliveryCardForm\.warehouse_code = /);
  assert.match(source, /refreshDeliveryCards/);
});

test("尾程改价发的是「今天」而不是原行的生效日（否则旧价区间倒挂 ⇒ 409）", () => {
  // 2026-11-17 实测：卡片改价对**已存在**的档位直接 409「already exists」。
  // 根因：改价时把原行生效日（2026-01-01）一起发出去 ⇒ 旧行被闭区间到
  // 2025-12-31 ⇒ effective_to < effective_from ⇒ 撞检查约束 ⇒ 409；
  // 就算没撞，历史也被抹掉（2026-01-01 起就算新价）。
  // ⇒ 口径：**改价 ⇒ 新价今天起生效，旧价闭区间到昨天**。
  assert.match(source, /const deliveryToday = \(\) => new Date\(\)\.toISOString\(\)\.slice\(0, 10\)/);
  // 卡片改价
  assert.match(source, /effective_from: deliveryToday\(\)/);
  // 明细表改价
  assert.match(source, /deliveryRuleCreatePayload\(row, deliveryToday\(\)\)/);
});

test("卡片只显示今天真正生效的那一档（未来才生效的价不冒充当前价）", () => {
  // 官方价目表说明年生效时，同一段会同时存在「旧价（还在当期）+ 新价（还没生效）」。
  // 取错行 ⇒ 卡片显示一个还没生效的价 ⇒ 运营照着改 ⇒ 改错。
  assert.match(source, /const inEffect = candidates\.find\(/);
  assert.match(source, /row\.effective_to >= today/);
});
