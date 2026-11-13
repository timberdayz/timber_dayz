<template>
  <div class="product-center erp-page-container">
    <el-tabs v-model="activeTab" class="product-tabs">
      <el-tab-pane label="SPU 管理" name="spu">
        <div class="toolbar">
          <el-input
            v-model="spuQuery.keyword"
            clearable
            placeholder="搜索 SPU 或名称"
            @keyup.enter="loadSpus"
          /><el-select
            v-model="spuQuery.biz_status"
            clearable
            placeholder="经营状态"
            @change="loadSpus"
            ><el-option label="候选" value="candidate" /><el-option
              label="测试"
              value="testing" /><el-option
              label="主推"
              value="promoted" /><el-option
              label="淘汰"
              value="retired" /></el-select
          ><el-button type="primary" :icon="Plus" @click="addSpuRow"
            >新增行</el-button
          ><el-button
            :icon="Check"
            :disabled="!spuDirty.length"
            :loading="saving"
            @click="saveSpuRows"
            >保存变更</el-button
          ><el-button
            type="danger"
            :disabled="!selectedSpus.length"
            @click="handleBatchDeleteSpu"
            >批量软删({{ selectedSpus.length }})</el-button
          >
        </div>
        <el-table
          :data="spus"
          v-loading="loadingSpus"
          stripe
          border
          class="flat-table"
          :row-class-name="spuRowClass"
          @selection-change="onSpuSelectionChange"
          ><el-table-column type="selection" width="48" :selectable="(row) => !row.__new && row.active !== false"
          /><el-table-column label="SPU" min-width="150"
            ><template #default="{ row }"
              ><el-input
                v-if="row.__new"
                v-model="row.spu"
                size="small"
                placeholder="HOME-0001" /><span v-else class="readonly-cell">{{ row.spu || "-" }}</span></template></el-table-column
          ><el-table-column label="商品名称" min-width="190"
            ><template #default="{ row }"
              ><el-input
                v-model="row.spu_name"
                size="small"
                @change="markDirty('spu', row)" /></template></el-table-column
          ><el-table-column label="一级品类" width="150"
            ><template #default="{ row }"
              ><el-select
                v-model="row.category_l1_code"
                size="small"
                placeholder="选择"
                @change="onSpuL1CategoryChange(row)"
                ><el-option
                  v-for="cat in l1Categories"
                  :key="categoryCode(cat)"
                  :label="cat.name_zh"
                  :disabled="cat.status !== 'active' || !cat.is_selectable"
                  :value="
                    categoryCode(cat)
                  " /></el-select></template></el-table-column
          ><el-table-column label="二级品类" width="170"
            ><template #default="{ row }"
              ><el-select
                v-model="row.category_l2_code"
                size="small"
                placeholder="选择"
                @change="markDirty('spu', row)"
                ><el-option
                  v-for="cat in childCategories(row.category_l1_code)"
                  :key="categoryCode(cat)"
                  :label="cat.name_zh"
                  :disabled="cat.status !== 'active' || !cat.is_selectable"
                  :value="
                    categoryCode(cat)
                  " /></el-select></template></el-table-column
          ><el-table-column label="物流货损率" width="120"
            ><template #default="{ row }"
              ><div class="rate-cell"
                ><el-input-number
                  :model-value="toPercent(row.logistics_damage_rate)"
                  :min="0"
                  :max="100"
                  :step="0.1"
                  @update:model-value="row.logistics_damage_rate = fromPercent($event); markDirty('spu', row)"
                  :controls="false"
                  size="small" /><span class="rate-suffix">%</span></div></template></el-table-column
          ><el-table-column label="退货损失率" width="120"
            ><template #default="{ row }"
              ><div class="rate-cell"
                ><el-input-number
                  :model-value="toPercent(row.return_loss_rate)"
                  :min="0"
                  :max="100"
                  :step="0.1"
                  @update:model-value="row.return_loss_rate = fromPercent($event); markDirty('spu', row)"
                  :controls="false"
                  size="small" /><span class="rate-suffix">%</span></div></template></el-table-column
          ><el-table-column label="状态" width="110"
            ><template #default="{ row }"
              ><el-select v-model="row.biz_status" size="small" @change="markDirty('spu', row)"
                ><el-option label="候选" value="candidate" /><el-option
                  label="测试"
                  value="testing" /><el-option
                  label="主推"
                  value="promoted" /><el-option
                  label="淘汰"
                  value="retired" /></el-select></template></el-table-column
          ><el-table-column label="负责人" width="110"
            ><template #default="{ row }"
              ><el-input-number
                v-model="row.owner_user_id"
                :min="1"
                :controls="false"
                size="small"
                @change="markDirty('spu', row)" /></template></el-table-column
          ><el-table-column label="操作" width="220" fixed="right"
            ><template #default="{ row }"
              ><el-button link type="primary" @click="showBindings(row)"
                >SKU 归属</el-button
              ><el-button
                v-if="row.active === false"
                link
                type="success"
                @click="handleRestoreSpu(row)"
                >恢复</el-button
              ><el-button
                link
                type="danger"
                :disabled="row.__new || row.active === false"
                @click="handleDeleteSpu(row)"
                >删除</el-button
              ></template
            ></el-table-column
          ></el-table
        >
        <el-pagination
          v-model:current-page="spuQuery.page"
          v-model:page-size="spuQuery.page_size"
          :total="spuTotal"
          layout="total, sizes, prev, pager, next"
          @current-change="loadSpus"
          @size-change="loadSpus"
        />
      </el-tab-pane>
      <el-tab-pane label="SKU 资料" name="sku">
        <div class="toolbar">
          <el-input
            v-model="skuQuery.keyword"
            clearable
            placeholder="搜索 SKU 或名称"
            @keyup.enter="loadSkus"
          /><el-select
            v-model="skuSpuFilter"
            clearable
            filterable
            remote
            allow-create
            remote-show-suffix
            :remote-method="spuBrowse.remoteMethod"
            :loading="spuBrowse.loading"
            placeholder="所属 SPU（可直接输入编码）"
            @change="loadSkus"
            ><el-option
              v-for="item in spuBrowse.options"
              :key="item.value"
              :label="item.label"
              :value="item.value"
              ><span class="spu-option-code">{{ item.value }}</span
              ><span class="spu-option-name">{{ item.name }}</span></el-option
            ></el-select
          ><el-select
            v-model="skuQuery.status"
            clearable
            placeholder="全部状态"
            @change="loadSkus"
            ><el-option label="在售" value="active" /><el-option
              label="停用"
              value="inactive" /></el-select
          ><el-select
            v-model="skuPricingPlatform"
            clearable
            placeholder="底线按平台"
            @change="loadSkus"
            ><el-option
              v-for="item in operatingDimensions.platforms || []"
              :key="item.platform_code"
              :label="`${item.name || item.platform_code} 底线`"
              :value="item.platform_code"
          /></el-select
          ><el-button type="primary" :icon="Plus" @click="addSkuRow"
            >新增行</el-button
          ><el-button
            :icon="Check"
            :disabled="!skuDirty.length"
            :loading="saving"
            @click="saveSkuRows"
            >保存变更</el-button
          ><el-button
            v-if="canManagePlatformFee"
            plain
            @click="openPlatformFeeDrawer('tiers')"
            >定价设置</el-button
          ><el-button
            plain
            :loading="sellingPriceCheck.loading"
            @click="runSellingPriceCheck"
            >基准售价巡检</el-button
          >
        </div>
        <el-table
          :data="skus"
          v-loading="loadingSkus"
          stripe
          border
          class="flat-table sku-table"
          :header-cell-style="skuHeaderCellStyle"
          ><el-table-column label="SPU" width="190"
            ><template #default="{ row }"
              ><!--
                存量行的 SPU 单元格**可编辑** —— 归属关系必须双向可达：
                以前只能从「SPU 管理」tab 的「SKU 归属」抽屉单向改，
                运营要改一个货的归属，得先知道它挂在哪个款下、再跨 tab 找过去。
                ⚠️ 候选集用**可绑定口径**（assignable）：赋值是外键，不能造出挂不上的款；
                ⚠️ 存量行**不给 clearable**：后端不支持解绑（清空只会静默无效）。
              -->
              <div class="spu-cell">
                <el-select
                  v-model="row.spu"
                  filterable
                  :clearable="row.__new"
                  remote
                  remote-show-suffix
                  :remote-method="spuAssignable.remoteMethod"
                  :loading="spuAssignable.loading"
                  size="small"
                  :placeholder="row.__new ? '选择 SPU' : '换款'"
                  @change="onSkuSpuChange(row)"
                  ><el-option
                    v-for="item in spuAssignableOptions"
                    :key="item.value"
                    :label="item.label"
                    :value="item.value"
                    ><span class="spu-option-code">{{ item.value }}</span
                    ><span class="spu-option-name">{{ item.name }}</span></el-option
                  ></el-select
                >
                <!--
                  归属生效日：这个货是**从哪天起**挂到这个款上的。
                  SPU 归属是一段有时效的关联，不是一个字段 ——
                  只显示编码，运营就看不到「什么时候挂上来的」「换过几次款」。
                -->
                <small v-if="!row.__new && row.spu_effective_from" class="spu-binding-since"
                  >自 {{ row.spu_effective_from }}</small
                >
              </div></template></el-table-column
          ><el-table-column label="SKU" width="160"
            ><template #default="{ row }"
              ><el-input
                v-if="row.__new"
                v-model="row.sku_key"
                size="small"
                placeholder="SKU-0001" /><span v-else class="readonly-cell">{{ row.sku_key || "-" }}</span></template></el-table-column
          ><el-table-column label="名称" min-width="180"
            ><template #default="{ row }"
              ><el-input
                v-model="row.sku_name"
                size="small"
                @change="markDirty('sku', row)" /></template></el-table-column
          ><el-table-column label="规格" width="140"
            ><template #default="{ row }"
              ><el-input
                v-model="row.specification"
                size="small"
                @change="markDirty('sku', row)" /></template></el-table-column
          ><el-table-column label="重量 kg" width="105"
            ><template #default="{ row }"
              ><el-input-number
                v-model="row.weight_kg"
                :min="0"
                :precision="3"
                :controls="false"
                size="small"
                @change="markDirty('sku', row)" /></template></el-table-column
          ><el-table-column label="单件体积 m³" width="125"
            ><template #default="{ row }"
              ><el-input-number
                v-model="row.unit_volume_cbm"
                :min="0"
                :precision="6"
                :step="0.0001"
                :controls="false"
                size="small"
                @change="markDirty('sku', row)" /></template></el-table-column
          ><el-table-column label="箱规（件/箱）" width="110"
            ><template #default="{ row }"
              ><el-input-number
                v-model="row.units_per_carton"
                :min="1"
                :controls="false"
                size="small"
                @change="markDirty('sku', row)" /></template></el-table-column
          ><el-table-column label="采购成本" width="115"><template #default="{ row }"><el-input-number v-model="row.default_purchase_cost" :min="0" :precision="2" :controls="false" size="small" @change="markDirty('sku', row)" /></template></el-table-column
          ><el-table-column label="采购成本来源" width="120"><template #default="{ row }">{{ row.purchase_cost_source || "待补充" }}</template></el-table-column
          ><el-table-column label="采购成本确认时间" width="145"><template #default="{ row }">{{ row.purchase_cost_confirmed_at || "-" }}</template></el-table-column
          ><el-table-column label="基准售价" width="260"><template #default="{ row }"><el-input-number v-model="row.reference_selling_price" :min="0" :precision="2" :controls="false" size="small" @input="scheduleSellingPricePreview(row)" @change="markDirty('sku', row); scheduleSellingPricePreview(row)" /><div v-if="sellingPricePreviewState(row)" class="selling-price-preview"><div class="selling-price-preview-title">最低售价会怎么变（保存后生效）</div><div v-for="item in sellingPricePreviewState(row).platforms" :key="item.platform_code" class="selling-price-preview-line"><template v-if="item.locked"><el-tag size="small" type="warning">{{ item.lockedText }}</el-tag></template><template v-else><span class="selling-price-preview-platform">{{ item.platformName }}</span><span class="selling-price-preview-change">{{ item.changeText }}<template v-if="item.pctText">（{{ item.pctText }}）</template></span><el-tag v-if="item.sourceLabel" size="small" :type="item.sourceTagType">{{ item.sourceLabel }}</el-tag><el-tag v-if="item.warn" size="small" type="danger">抬价超 20%</el-tag></template></div><div v-for="warning in sellingPricePreviewState(row).warnings" :key="warning" class="selling-price-preview-warning">{{ warning }}</div><div v-if="sellingPricePreviewState(row).loading" class="selling-price-preview-hint">正在计算…</div><div v-if="sellingPricePreviewState(row).error" class="selling-price-preview-hint">{{ sellingPricePreviewState(row).error }}</div></div></template></el-table-column
          ><el-table-column label="确认日期" width="130"><template #default="{ row }"><span class="readonly-cell" :class="{ 'stale-date': row.selling_price_stale }">{{ formatConfirmedAt(row.selling_price_confirmed_at) }}</span></template></el-table-column
          ><el-table-column label="售价账龄(天)" width="115"><template #default="{ row }"><span>{{ row.selling_price_age_days ?? "-" }}</span><div v-if="row.selling_price_stale" class="pricing-tier-hint stale-hint">基准售价已 {{ row.selling_price_age_days }} 天未确认，纪律线可能失真</div><div v-else-if="row.reference_selling_price != null && row.selling_price_age_days == null" class="pricing-tier-hint">基准售价从未确认</div></template></el-table-column
          ><el-table-column label="是否过期" width="100"><template #default="{ row }"><el-tag size="small" :type="row.selling_price_stale ? 'danger' : 'success'">{{ row.selling_price_stale ? "已过期" : "正常" }}</el-tag></template></el-table-column
          ><el-table-column label="当前让利上限" width="110"><template #default="{ row }"><el-tag size="small" type="info">{{ percent(row.current_discount_rate) }}</el-tag></template></el-table-column
          ><el-table-column label="清货让利上限" width="110"><template #default="{ row }"><el-tag size="small" type="warning">{{ percent(row.clearance_max_discount_rate) }}</el-tag></template></el-table-column
          ><el-table-column label="最低售价" width="340"
            ><template #default="{ row }"
              ><div class="pricing-cell">
                <!-- 每个可定价平台一行：底线是 SKU × 平台的量，TikTok 与 Shopee 的平台成本率不同
                     （27.27% vs 41.65%），同一件商品在两个平台有两条不同的底线。 -->
                <div
                  v-for="item in skuPricingPlatformRows(row)"
                  :key="item.platform_code"
                  class="pricing-platform-row"
                >
                  <div class="pricing-cell-head">
                    <span class="pricing-platform-name">{{ item.name }}</span>
                    <span
                      class="readonly-cell"
                      :class="{ 'pending-override': pendingPlatformOverride(row, item) != null }"
                      >{{ pendingPlatformOverride(row, item) != null ? `保存后生效：${money(pendingPlatformOverride(row, item))}` : money(item.min_selling_price) }}</span
                    ><el-tag
                      size="small"
                      :type="pricingSourceTagType(item.min_selling_price_source)"
                      :title="PRICING_SOURCE_TOOLTIPS[item.min_selling_price_source]"
                      >{{ pricingSourceLabel(item.min_selling_price_source) }}</el-tag
                    >
                  </div>
                  <div class="pricing-override-row">
                    <el-input-number
                      :model-value="platformOverrideDraft(row, item)"
                      :min="0.01"
                      :precision="2"
                      :controls="false"
                      size="small"
                      :disabled="!row.sku_id"
                      :placeholder="item.min_selling_price != null ? money(item.min_selling_price) : '自动'"
                      @update:model-value="setPlatformOverrideDraft(row, item, $event)"
                    />
                    <el-button
                      size="small"
                      plain
                      :disabled="!row.sku_id || platformOverrideDraft(row, item) == null"
                      :loading="savingOverrideKey === overrideSavingKey(row, item)"
                      @click="savePlatformOverride(row, item)"
                      >保存覆盖</el-button
                    ><el-button
                      v-if="item.min_selling_price_is_override || item.min_selling_price_override != null"
                      size="small"
                      link
                      type="warning"
                      :disabled="!row.sku_id"
                      @click="resetPlatformOverride(row, item)"
                      >重置为自动值</el-button
                    >
                  </div>
                </div>
                <div
                  v-if="!skuPricingPlatformRows(row).length"
                  class="pricing-tier-hint"
                >暂无可定价平台，无法计算底线</div>
                <div class="pricing-tier-hint">{{ row.pricing_tier_label || "-" }}<template v-if="row.pricing_days_since_restock != null">（库龄 {{ row.pricing_days_since_restock }} 天）</template><el-tag v-if="row.pricing_tier_source === 'fallback_no_restock_days'" size="small" type="info">兜底</el-tag></div>
                <div class="pricing-tier-hint">底线按 {{ skuPricingPlatform || '默认平台' }} 的成本率计算</div>
                <div class="pricing-tier-hint">人工覆盖按平台生效，各平台底线互相独立</div>
              </div></template
            ></el-table-column
          ><el-table-column label="达人佣金率" width="145"><template #header><el-tooltip content="留空表示不单独设置，按平台默认计算" placement="top"><span class="pricing-header">达人佣金率<el-icon class="pricing-header-help"><QuestionFilled /></el-icon></span></el-tooltip></template><template #default="{ row }"><div class="rate-cell"><el-input-number :model-value="toPercent(row.creator_commission_rate)" :min="0" :max="100" :step="0.1" :precision="2" :controls="false" size="small" :placeholder="row.creator_commission_rate_fallback != null ? percent(row.creator_commission_rate_fallback) : '按平台默认'" @update:model-value="row.creator_commission_rate = fromPercent($event, null); markDirty('sku', row)" /><span class="rate-suffix">%</span></div></template></el-table-column
          ><el-table-column label="基准售价来源" width="140"><template #default="{ row }"><el-select v-model="row.selling_price_source" size="small" placeholder="选择来源" @change="markDirty('sku', row)"><el-option v-for="option in SELLING_PRICE_SOURCE_OPTIONS" :key="option.value" :label="option.label" :value="option.value" /></el-select></template></el-table-column
          ><el-table-column label="周转类型" width="120"><template #default="{ row }"><el-select v-model="row.turnover_class" size="small" placeholder="选择" @change="markDirty('sku', row)"><el-option label="快销商品（30天）" value="fast" /><el-option label="普通商品（60天）" value="normal" /><el-option label="慢销商品（90天）" value="slow" /></el-select></template></el-table-column
          ><el-table-column label="参考仓储天数" width="120"><template #default="{ row }">{{ referenceStorageDays(row.turnover_class) || "待设置" }}</template></el-table-column
          ><el-table-column
            label="来源文件"
            prop="source_file_id"
            width="100"
          /><el-table-column label="资料完整度" width="110"
            ><template #default="{ row }"
              ><el-tag
                :type="
                  row.data_completeness === 'complete' ? 'success' : 'warning'
                "
                size="small"
                >{{ row.data_completeness || "待补充" }}</el-tag
              ></template
            ></el-table-column
          ><el-table-column label="操作" width="160" fixed="right"
            ><template #default="{ row }"
              ><el-button
                v-if="row.status !== 'inactive' && !row.__new"
                link
                type="danger"
                @click="handleDeleteSku(row)"
                >停用</el-button
              ><el-button
                v-if="row.status === 'inactive'"
                link
                type="success"
                @click="handleRestoreSku(row)"
                >恢复</el-button
              ></template
            ></el-table-column
          ></el-table
        >
        <el-pagination
          v-model:current-page="skuQuery.page"
          v-model:page-size="skuQuery.page_size"
          :total="skuTotal"
          layout="total, sizes, prev, pager, next"
          @current-change="loadSkus"
          @size-change="loadSkus"
        />
      </el-tab-pane>
      <el-tab-pane label="平台 SKU 利润测算" name="operating">
        <div class="toolbar">
          <el-select
            v-model="operatingQuery.platform_code"
            clearable
            filterable
            placeholder="平台"
            @change="resetOperatingPage"
            ><el-option
              v-for="item in operatingDimensions.platforms"
              :key="item.platform_code"
              :label="item.name || item.platform_code"
              :value="item.platform_code"
          /></el-select>
          <el-select v-model="operatingQuery.warehouse_code" clearable filterable placeholder="收货仓库" @change="resetOperatingPage">
            <el-option v-for="item in operatingDimensions.warehouses" :key="item.warehouse_code" :label="item.warehouse_name || item.warehouse_code" :value="item.warehouse_code" />
          </el-select>
          <el-select v-model="operatingQuery.transport_type" clearable placeholder="物流方式" @change="resetOperatingPage">
            <el-option label="海运" value="sea" />
            <el-option label="空运" value="air" />
            <el-option label="铁路运输" value="rail" />
          </el-select>
          <el-select v-model="operatingQuery.spu" clearable filterable placeholder="SPU" @change="handleOperatingSpuChange">
            <el-option v-for="item in operatingDimensions.spus || []" :key="item" :label="item" :value="item" />
          </el-select>
          <el-select v-model="operatingQuery.sku_id" clearable filterable placeholder="ERP SKU" @change="resetOperatingPage">
            <el-option v-for="item in filteredOperatingSkus" :key="item.sku_id" :label="item.sku_key" :value="item.sku_id" />
          </el-select>
          <el-button v-if="canManagePlatformFee" plain @click="openPlatformFeeDrawer('platform')">定价设置</el-button>
          <!--
            阶段 7：「仅有库存」默认打开 —— 测算表是"给还在卖的货定价"的表，
            先把**这个仓已经清空的货**藏起来，运营不用在一屏"已清仓"里找活干。
            筛选在后端做（前端筛只筛当前页，总数对不上、翻页会漏行）。
          -->
          <el-checkbox v-model="operatingQuery.only_in_stock" @change="resetOperatingPage">仅有库存</el-checkbox>
          <span class="pricing-tier-hint">只看当前仓还有可用库存的 SKU</span>
          <el-checkbox v-model="showAdRateEscape" class="ad-rate-escape-toggle">
            高级：按广告分成率口径（默认用目标ROI）
          </el-checkbox>
        </div>
        <el-alert v-if="!operatingQuery.platform_code || !operatingQuery.warehouse_code || !operatingQuery.transport_type" type="info" :closable="false" title="请选择平台、收货仓库和物流方式后加载 SKU 测算数据" />
        <div class="roi-disclaimer">
          <div>① 本表不预测销量：提价会不会掉量看不到（缺历史投放数据，做不了销量预测）。</div>
          <div>② 平台报告 ROI 含自然流量/达人归因，达标 ≠ 赚钱；投多少不亏以本表「保本ROI」为准。</div>
        </div>
        <!--
          四段分区说明（阶段 6）：表头按段着色，运营从左到右按「看事实 → 填输入 →
          看结果 → 查成本」的工作顺序读表，不用在一堆列里找下一步该动哪个。
        -->
        <div class="segment-legend">
          <span class="segment-legend-item"><i class="seg-fact"></i>标识与事实：是什么、成本多少</span>
          <span class="segment-legend-item"><i class="seg-input"></i>决策输入：要卖多少、要投多少</span>
          <span class="segment-legend-item"><i class="seg-result"></i>定价结果：底线多少、能不能投</span>
          <span class="segment-legend-item"><i class="seg-cost"></i>成本明细与利润：钱花在哪</span>
        </div>
        <el-table
          :data="operatingProfiles"
          v-loading="loadingOperating"
          stripe
          border
          class="flat-table operating-table"
        >
          <!--
            左侧固定三列（阶段 6）：标识与事实。
            运营横向滚动看后面的成本与利润时，「这是哪个 SKU」必须一直在眼前。
          -->
          <el-table-column prop="spu" label="SPU" width="160" fixed="left" />
          <el-table-column prop="sku_key" label="ERP SKU" width="155" fixed="left" />
          <el-table-column prop="sku_name" label="商品名称" min-width="200" show-overflow-tooltip fixed="left" />
          <!-- 段一 · 标识与事实 -->
          <el-table-column label="采购成本" width="110" class-name="seg-fact" label-class-name="seg-fact"><template #default="{ row }">{{
            money(row.purchase_cost)
          }}</template></el-table-column
          >
          <el-table-column label="基准售价" width="105" class-name="seg-fact" label-class-name="seg-fact"><template #default="{ row }">{{ money(row.reference_selling_price) }}</template></el-table-column>
          <el-table-column label="竞品价格" width="110" class-name="seg-fact" label-class-name="seg-fact"><template #default="{ row }"><el-input-number v-model="row.competitor_price" :min="0" :controls="false" size="small" /></template></el-table-column>
          <!--
            当前仓库存（阶段 7）：**这个仓现在还剩多少货**。
            ⚠️ 与「库龄（仓）」是两件事：库龄是"压了多久"（只算还有货的仓），
            这里是"还有多少货"（**零也要列出来**）—— 零 = 这个仓清过这货，
            是一条事实。所以显式标「已清仓」，不让运营把它误读成缺数据。
          -->
          <el-table-column label="当前仓库存" width="120" class-name="seg-fact" label-class-name="seg-fact"><template #default="{ row }"><el-tag v-if="row.current_warehouse_stock_status === 'cleared'" size="small" type="info">已清仓</el-tag><span v-else :class="{ muted: row.current_warehouse_stock_status !== 'in_stock' }">{{ currentWarehouseStockLabel(row) }}</span></template></el-table-column>
          <!--
            库龄（仓）：阶段 6 —— 库龄不再是「这个 SKU 最老的那一仓」，
            而是**当前选中的这个仓自己**的库龄；下面再列其它仓的库龄，
            运营一眼能看出「我这仓新鲜、别的仓压着」。
          -->
          <el-table-column label="库龄（仓）" width="230" class-name="seg-fact" label-class-name="seg-fact"><template #default="{ row }"><div><span class="readonly-cell">{{ currentWarehouseRestockDays(row) ?? "-" }}</span> 天<span class="pricing-tier-hint">（{{ currentWarehouseLabel(row) }}）</span></div><div v-for="item in otherWarehouseRestocks(row)" :key="item.warehouse_code" class="pricing-tier-hint">{{ item.warehouse_name }}：{{ item.days_since_restock ?? "-" }} 天</div></template></el-table-column>
          <!-- 段二 · 决策输入 -->
          <el-table-column label="测算售价" width="110" class-name="seg-input" label-class-name="seg-input"
            ><template #default="{ row }"
              ><el-input-number
                v-model="row.expected_selling_price"
                :class="{ 'price-below-floor': isBelowFloor(row) }"
                :min="0"
                :controls="false"
                size="small"
                @input="scheduleOperatingPreview(row)" />
              <div v-if="isBelowFloor(row)" class="price-floor-hint">
                低于最低售价 {{ money(row.min_selling_price) }}
              </div></template
          ></el-table-column
          >
          <el-table-column label="优惠券（商家承担）" width="110" class-name="seg-input" label-class-name="seg-input"
            ><template #default="{ row }"
              ><el-input-number
                v-model="row.seller_coupon_amount"
                :min="0"
                :controls="false"
                size="small"
                @input="scheduleOperatingPreview(row)" /></template
          ></el-table-column
          >
          <el-table-column label="目标ROI" width="135" class-name="seg-input" label-class-name="seg-input"
            ><template #default="{ row }"
              ><div class="rate-cell"
                ><el-input-number
                  v-model="row.target_roi"
                  :min="0"
                  :step="0.1"
                  :controls="false"
                  size="small"
                  @input="onTargetRoiInput(row)" /></div
              >
              <el-tag v-if="targetRoiBelowBreakEven(row)" size="small" type="danger"
                >低于保本线</el-tag
              >
              <el-tooltip placement="top" :content="targetRoiTooltip(row)">
                <el-icon class="pricing-header-help"><QuestionFilled /></el-icon>
              </el-tooltip></template
          ></el-table-column
          >
          <el-table-column label="平台报告ROI" width="175" class-name="seg-input" label-class-name="seg-input"
            ><template #default="{ row }"
              ><div class="rate-cell"
                ><el-input-number
                  v-model="row.actual_roi"
                  :min="0"
                  :step="0.1"
                  :controls="false"
                  size="small" /></div
              >
              <el-tag v-if="roiVerdict(row)" size="small" :type="roiVerdict(row).type">{{
                roiVerdict(row).label
              }}</el-tag>
              <el-tooltip placement="top" :content="roiVerdictTooltip(row)">
                <el-icon class="pricing-header-help"><QuestionFilled /></el-icon>
              </el-tooltip></template
          ></el-table-column
          >
          <!-- 段三 · 定价结果 -->
          <el-table-column label="当前让利上限" width="100" class-name="seg-result" label-class-name="seg-result"><template #default="{ row }"><el-tag size="small" type="info">{{ percent(row.current_discount_rate) }}</el-tag></template></el-table-column>
          <el-table-column label="清货让利上限" width="100" class-name="seg-result" label-class-name="seg-result"><template #default="{ row }"><el-tag size="small" type="warning">{{ percent(row.clearance_max_discount_rate) }}</el-tag></template></el-table-column>
          <el-table-column label="最低售价" width="120" class-name="seg-result" label-class-name="seg-result"
            ><template #default="{ row }"
              ><span class="readonly-cell">{{ money(row.min_selling_price) }}</span>
              <div class="pricing-tier-hint">
                {{ row.pricing_tier_label || "-" }}
                <el-tag v-if="row.pricing_tier_source === 'fallback_no_restock_days'" size="small" type="info">兜底</el-tag>
              </div>
              <div class="pricing-tier-hint">按 {{ row.platform_code }} 平台成本率计算，不同平台底线不同</div></template
          ></el-table-column>
          <el-table-column label="广告前贡献毛利率" width="140" class-name="seg-result" label-class-name="seg-result"
            ><template #default="{ row }"
              ><span :class="{ 'roi-guarded': roiGuarded(row) }">{{
                percent(row.preview?.expected?.advertising_contribution_margin_rate)
              }}</span>
              <el-tooltip
                placement="top"
                content="扣掉采购、物流、仓储、贴单、平台佣金、达人佣金、货损、退货后的占比。分母是商家实收（售价−优惠券），与平台 GMV 同一口径"
              >
                <el-icon class="pricing-header-help"><QuestionFilled /></el-icon>
              </el-tooltip></template
          ></el-table-column>
          <el-table-column label="保本ROI" width="150" class-name="seg-result" label-class-name="seg-result"
            ><template #default="{ row }"
              ><span :class="{ 'roi-guarded': roiGuarded(row) }">{{
                roiDisplay(row.preview?.expected?.break_even_roi)
              }}</span>
              <el-tooltip placement="top" :content="roiGuardTooltip(row)">
                <el-icon class="pricing-header-help"><QuestionFilled /></el-icon>
              </el-tooltip>
              <div v-if="roiGuarded(row)" class="roi-guard-hint">
                成本不全，保本ROI 偏乐观
              </div></template
          ></el-table-column>
          <el-table-column label="建议ROI" width="150" class-name="seg-result" label-class-name="seg-result"
            ><template #default="{ row }"
              ><span :class="{ 'roi-guarded': roiGuarded(row) }">{{
                roiDisplay(row.preview?.expected?.suggested_roi_clamped)
              }}</span>
              <el-tag
                v-if="row.preview?.expected?.suggestion_note === 'above_platform_ceiling'"
                size="small"
                type="warning"
                >广告空间不足</el-tag
              >
              <el-tooltip placement="top" :content="roiSuggestionTooltip(row)">
                <el-icon class="pricing-header-help"><QuestionFilled /></el-icon>
              </el-tooltip></template
          ></el-table-column>
          <!--
            跨仓提示（阶段 6）：同一个 ERP SKU 在别的仓滞销、这个仓不滞销时，
            提示「优先调拨，而不是压低全站点底线」。
            **只提示，不改价** —— 调拨是运营决策，系统不越权。
          -->
          <el-table-column label="跨仓提示" width="280" class-name="seg-result" label-class-name="seg-result"><template #default="{ row }"><template v-if="row.warehouse_divergence"><el-tag size="small" type="warning">跨仓库龄差异</el-tag><div class="warehouse-divergence-hint">{{ row.warehouse_divergence.suggestion }}</div></template><span v-else class="muted">-</span></template></el-table-column>
          <!-- 段四 · 成本明细与利润 -->
          <el-table-column label="预估物流成本" width="150" class-name="seg-cost" label-class-name="seg-cost"><template #default="{ row }">{{ referenceCostDisplay(row, "logistics") }}</template></el-table-column>
          <el-table-column label="预估仓储成本" width="150" class-name="seg-cost" label-class-name="seg-cost"><template #default="{ row }">{{ referenceCostDisplay(row, "storage") }}</template></el-table-column>
          <el-table-column label="贴单费" width="115" class-name="seg-cost" label-class-name="seg-cost"><template #default="{ row }">{{ referenceLabelFeeDisplay(row) }}</template></el-table-column>
          <el-table-column label="广告分成率" width="225" class-name="seg-cost" label-class-name="seg-cost"
            ><template #default="{ row }"
              ><!--
                广告分成率是**高级逃生口**（阶段 3）：主输入是「目标 ROI」
                （平台语言：商家实收 ÷ 目标ROI）。手填分成率默认折叠，
                要显式展开才改得了；旁边**永远**并排显示「等效目标 ROI」，
                那是同一件事的平台语言说法（保本ROI ÷ 广告分成率）。
                两个口径在数值上等价，所以切换不改变利润。
              -->
              <div class="rate-cell">
                <el-input-number
                  v-if="showAdRateEscape"
                  v-model="row.expected_ad_rate_pct"
                  :min="0"
                  :max="100"
                  :step="0.1"
                  :controls="false"
                  size="small"
                  @input="onAdRateEscapeInput(row)" />
                <span v-else class="rate-locked">{{
                  percent(row.preview?.expected?.ad_cost_rate)
                }}（按目标ROI口径）</span>
                <span class="rate-suffix">%</span>
              </div>
              <div class="ad-rate-equivalent">
                等效目标ROI {{ roiDisplay(row.preview?.expected?.equivalent_target_roi) }}
              </div>
              <div v-if="row.adRateEscapeUsed" class="price-floor-hint">
                已改用广告分成率口径（目标ROI 已清空）
              </div></template
          ></el-table-column>
          <el-table-column label="平台佣金率" width="100" class-name="seg-cost" label-class-name="seg-cost"><template #default="{ row }">{{ percent(row.platform_fee_rate) }}</template></el-table-column>
          <el-table-column label="平台佣金" width="105" class-name="seg-cost" label-class-name="seg-cost"><template #default="{ row }">{{ money(row.preview?.expected?.platform_fee) }}</template></el-table-column>
          <el-table-column label="达人佣金" width="120" class-name="seg-cost" label-class-name="seg-cost"><template #default="{ row }"><div class="rate-cell"><span>{{ percent(row.preview?.expected?.creator_commission_rate) }}</span></div>{{ money(row.preview?.expected?.creator_commission) }}</template></el-table-column>
          <el-table-column label="预计广告费用" width="105" class-name="seg-cost" label-class-name="seg-cost"><template #default="{ row }">{{ money(row.preview?.expected?.ad_cost) }}</template></el-table-column>
          <el-table-column label="物流货损率（SPU）" width="110" class-name="seg-cost" label-class-name="seg-cost"><template #default="{ row }">{{ percent(row.logistics_damage_rate) }}</template></el-table-column>
          <el-table-column label="退货损失率（SPU）" width="130" class-name="seg-cost" label-class-name="seg-cost"><template #default="{ row }">{{ percent(row.return_loss_rate) }}</template></el-table-column>
          <el-table-column label="参考成本利润" width="120" class-name="seg-cost" label-class-name="seg-cost"
            ><template #default="{ row }">{{
              money(row.preview?.expected?.profit)
            }}</template></el-table-column
          >
          <el-table-column label="利润率" width="100" class-name="seg-cost" label-class-name="seg-cost"
            ><template #default="{ row }">{{
              percent(row.preview?.expected?.margin_rate)
            }}</template></el-table-column
          >
          <el-table-column label="混合成本利润" width="120" class-name="seg-cost" label-class-name="seg-cost"
            ><template #default="{ row }"
              >{{ money(row.preview?.actual_recost?.profit) }}
              <el-tooltip
                placement="top"
                :content="`物流 ${money(row.actual_logistics_cost)}（真实账单）｜仓储 ${money(row.preview?.actual_recost?.storage_cost)}（规则预估——系统里没有仓储费账单）`"
              >
                <el-icon class="pricing-header-help"><QuestionFilled /></el-icon>
              </el-tooltip></template
            ></el-table-column
          >
          <el-table-column label="混合成本完整度" width="120" class-name="seg-cost" label-class-name="seg-cost"
            ><template #default="{ row }"
              >{{ row.preview?.actual_recost?.completeness || "-" }}
              <el-tooltip
                placement="top"
                content="这一版用了多少真实成本：incomplete=没算出来 / estimated=全预估 / mixed=一半真实 / actual=全真实"
              >
                <el-icon class="pricing-header-help"><QuestionFilled /></el-icon>
              </el-tooltip></template
            ></el-table-column
          >
          <el-table-column label="操作" width="180" fixed="right"
            ><template #default="{ row }"
              ><el-button link type="primary" @click="previewOperatingRow(row)">试算</el-button
              ><el-button link @click="saveOperatingDraft(row)">保存测算草稿</el-button
              ><el-button link type="success" :disabled="isBelowFloor(row)" :title="isBelowFloor(row) ? `低于最低售价 ${money(row.min_selling_price)}` : ''" @click="saveOperatingEstimate(row)">保存利润版本</el-button
              ></template
            ></el-table-column
          >
        </el-table>
        <el-pagination
          v-model:current-page="operatingQuery.page"
          v-model:page-size="operatingQuery.page_size"
          :total="operatingTotal"
          layout="total, sizes, prev, pager, next"
          @current-change="loadOperatingProfiles"
          @size-change="loadOperatingProfiles"
        />
      </el-tab-pane>
      <el-tab-pane label="物流仓储管理" name="logistics"
        ><el-tabs v-model="costTab" class="cost-tabs"
          ><el-tab-pane label="物流服务商规则" name="rules"
            ><div class="toolbar">
              <el-button type="primary" :icon="Plus" @click="addRuleRow"
                >新增规则</el-button
              ><el-button
                :icon="Check"
                :disabled="!ruleDirty.length"
                @click="saveRuleRows"
                >保存规则</el-button
              >
            </div>
            <el-table :data="rules" v-loading="loadingRules" stripe border empty-text="暂无物流规则"
              ><el-table-column label="服务商"
                ><template #default="{ row }"
                  ><el-input
                    v-model="row.logistics_provider"
                    size="small"
                    @change="markRuleDirty(row)" /></template></el-table-column
              ><el-table-column label="收货仓库"
                ><template #default="{ row }"
                  ><el-select v-model="row.warehouse_code" size="small" filterable @change="markRuleDirty(row)">
                    <el-option v-for="item in operatingDimensions.warehouses" :key="item.warehouse_code" :label="`${item.warehouse_name} (${item.country_name})`" :value="item.warehouse_code" />
                  </el-select></template></el-table-column
              ><el-table-column label="运输方式"
                ><template #default="{ row }"
                  ><el-select v-model="row.transport_type" size="small" @change="markRuleDirty(row)"><el-option label="海运" value="sea" /><el-option label="空运" value="air" /><el-option label="铁路运输" value="rail" /></el-select></template></el-table-column
              ><el-table-column label="货物类型"
                ><template #default="{ row }"
                  ><el-select v-model="row.cargo_class" size="small" @change="markRuleDirty(row)"
                    ><el-option label="普通货" value="normal" /><el-option
                      label="敏感货 M"
                      value="sensitive" /></el-select></template></el-table-column
              ><el-table-column label="默认规则" width="95"
                ><template #default="{ row }"
                  ><el-switch
                    v-model="row.is_default"
                    @change="markRuleDirty(row)"
                  /></template></el-table-column
              ><el-table-column label="计费方式"
                ><template #default="{ row }"
                  ><el-select v-model="row.billing_basis" size="small" @change="markRuleDirty(row)"
                    ><el-option label="按体积" value="volume" /><el-option
                      label="按重量"
                      value="weight" /><el-option
                      label="按数量"
                      value="quantity" /><el-option
                      label="固定金额"
                      value="fixed" /></el-select></template></el-table-column
              ><el-table-column label="单位费率"
                ><template #default="{ row }"
                  ><el-input-number
                    v-model="row.freight_unit_rate"
                    :min="0"
                    :controls="false"
                    size="small"
                    @change="markRuleDirty(row)" /></template></el-table-column
              ><el-table-column label="生效日期"
                ><template #default="{ row }"
                  ><el-date-picker
                    v-model="row.effective_from"
                    type="date"
                    value-format="YYYY-MM-DD"
                    size="small"
                    @change="markRuleDirty(row)" /></template></el-table-column
              ><el-table-column label="操作" width="90" fixed="right"
                ><template #default="{ row }"
                  ><el-button
                    v-if="!row.__new"
                    link
                    type="danger"
                    size="small"
                    @click="removeProviderRule(row)"
                    >删除</el-button></template></el-table-column
              ></el-table></el-tab-pane
          ><el-tab-pane label="仓储规则" name="storage-rules"
            ><div class="toolbar">
              <el-button v-if="canManagePlatformFee" type="primary" :icon="Plus" @click="addStorageRuleRow">新增仓储规则</el-button>
              <span class="muted">固定按体积计费：CNY/CBM/月</span>
            </div>
            <el-table :data="storageRules" v-loading="loadingStorageRules" stripe border>
              <el-table-column label="收货仓库" min-width="180"><template #default="{ row }"><el-select v-model="row.warehouse_code" size="small" filterable :disabled="!row.__new"><el-option v-for="item in operatingDimensions.warehouses" :key="item.warehouse_code" :label="`${item.warehouse_name} (${item.country_name})`" :value="item.warehouse_code" /></el-select></template></el-table-column>
              <el-table-column label="计费方式" width="110"><template #default>按体积</template></el-table-column>
              <el-table-column label="计费单位" width="130"><template #default>CNY/CBM/月</template></el-table-column>
              <el-table-column label="仓储单价" width="120"><template #default="{ row }"><el-input-number v-model="row.unit_rate_cny" :min="0" :precision="4" :controls="false" size="small" /></template></el-table-column>
              <el-table-column label="贴单费" width="110"><template #default="{ row }"><el-input-number v-model="row.label_fee" :min="0" :precision="2" :controls="false" size="small" placeholder="可选" /></template></el-table-column>
              <el-table-column label="生效日期" width="145"><template #default="{ row }"><el-date-picker v-model="row.effective_from" type="date" value-format="YYYY-MM-DD" size="small" /></template></el-table-column>
              <el-table-column label="状态" width="105"><template #default="{ row }"><el-tag :type="row.status === 'active' ? 'success' : 'info'">{{ row.status === 'active' ? '启用' : '已停用' }}</el-tag></template></el-table-column>
              <el-table-column label="版本" width="120"><template #default="{ row }"><el-input v-model="row.version" size="small" /></template></el-table-column>
              <el-table-column label="来源" width="130"><template #default="{ row }"><el-input v-model="row.source" size="small" /></template></el-table-column>
              <el-table-column label="备注" min-width="150"><template #default="{ row }"><el-input v-model="row.notes" size="small" /></template></el-table-column>
              <el-table-column v-if="canManagePlatformFee" label="操作" width="240" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="saveStorageRule(row)">保存（自动新版本）</el-button><el-button v-if="!row.__new && row.status === 'active'" link type="danger" @click="disableStorageRule(row)">停用</el-button><el-button v-if="!row.__new && row.status !== 'active'" link type="success" @click="enableStorageRule(row)">启用</el-button><el-button v-if="!row.__new" link type="danger" @click="removeStorageRuleRow(row)">删除</el-button></template></el-table-column>
            </el-table></el-tab-pane
          ><el-tab-pane label="物流批次" name="batches"
            ><div class="toolbar">
              <el-select
                v-model="billStatus"
                clearable
                placeholder="状态"
                @change="loadBatches"
                ><el-option label="草稿" value="draft" /><el-option
                  label="已确认"
                  value="confirmed" /><el-option
                  label="已作废"
                  value="voided" /></el-select
              ><el-button type="primary" :icon="Plus" @click="openBatchCreate"
                >新增物流批次</el-button
              >
            </div>
            <el-table
              :data="logisticsBatches"
              v-loading="loadingBills"
              stripe
              border
              ><el-table-column prop="bill_no" label="批次号" /><el-table-column
                prop="logistics_provider"
                label="物流服务商"
              /><el-table-column
                prop="bill_date"
                label="账单日期"
              /><el-table-column
                prop="warehouse_code"
                label="收货仓库"
              /><el-table-column prop="total_amount" label="账单总额"
                ><template #default="{ row }">{{
                  money(row.total_amount)
                }}</template></el-table-column
              ><el-table-column prop="status" label="状态" /><el-table-column
                label="操作"
                width="190"
                ><template #default="{ row }"
                  ><el-button link type="primary" @click="editBatch(row)"
                    >编辑账单行</el-button
                  ><el-button
                    v-if="row.status === 'draft'"
                    link
                    type="success"
                    @click="confirmBatch(row)"
                    >确认</el-button
                  ></template
                ></el-table-column
              ></el-table
            ></el-tab-pane
          ></el-tabs
        ></el-tab-pane
      >
    </el-tabs>
    <el-drawer
      v-model="pricingDrawer.visible"
      title="定价设置"
      size="720px"
      destroy-on-close
    >
      <el-tabs v-model="pricingDrawer.tab">
        <el-tab-pane label="平台成本率" name="platform">
          <el-alert type="info" :closable="false" title="平台成本率用于最低售价底线计算，仅管理员、主管和财务可维护。" />
          <el-form :model="pricingDrawer.form" label-width="150px" class="drawer-form">
            <el-form-item label="平台"><span>{{ pricingDrawer.label }}</span></el-form-item>
            <el-form-item label="平台佣金率">
              <div class="rate-cell"><el-input-number v-model="pricingDrawer.form.default_fee_rate_pct" :min="0" :max="100" :step="0.1" :precision="2" :controls="false" /><span class="rate-suffix">%</span></div>
            </el-form-item>
            <el-form-item label="默认达人佣金率">
              <div class="rate-cell"><el-input-number v-model="pricingDrawer.form.default_creator_commission_rate_pct" :min="0" :max="100" :step="0.1" :precision="2" :controls="false" /><span class="rate-suffix">%</span></div>
              <div class="pricing-tier-hint">SKU 未单独设置时的兜底值</div>
            </el-form-item>
            <el-form-item label="平台其他成本率">
              <div class="rate-cell"><el-input-number v-model="pricingDrawer.form.other_cost_rate_pct" :min="0" :max="100" :step="0.1" :precision="2" :controls="false" /><span class="rate-suffix">%</span></div>
            </el-form-item>
            <el-form-item label="成本率合计">
              <span>{{ pricingDrawer.costRateTotalPct }}%</span>
              <div class="pricing-tier-hint">仅作成本结构展示，不是底线基数</div>
            </el-form-item>
            <el-form-item label="默认底线基数">
              <span>{{ pricingDrawer.baseRatePct }}%</span>
              <div class="pricing-tier-hint">
                默认达人佣金率 + 平台其他成本率（平台佣金率已含在「平台其他成本率」内，不重复计入）。<br />
                <strong>仅在 SKU 未单独设置达人佣金率时成立</strong>；SKU 单独设置后，底线基数 = 平台其他成本率 + 该 SKU 的达人佣金率。
              </div>
            </el-form-item>
            <el-form-item label="生效日期"><el-date-picker v-model="pricingDrawer.form.fee_rate_effective_from" type="date" value-format="YYYY-MM-DD" /></el-form-item>
            <el-form-item label="来源"><el-input v-model="pricingDrawer.form.fee_rate_source" /></el-form-item>
            <el-form-item label="版本"><el-input v-model="pricingDrawer.form.fee_rate_version" /></el-form-item>
          </el-form>
        </el-tab-pane>
        <el-tab-pane label="库龄档位规则" name="tiers">
          <el-alert type="info" :closable="false" title="库龄起点 = 从该天数起，本行规则生效。折扣力度完全由库龄档位触发，每档只有一个让利率。" />
          <el-table :data="pricingDrawer.policies" size="small" border>
            <el-table-column label="库龄起点" width="120">
              <template #default="{ row }">
                <el-input-number v-model="row.min_restock_days" :min="0" :step="1" :precision="0" :controls="false" size="small" />
              </template>
            </el-table-column>
            <el-table-column label="档位名" min-width="140">
              <template #default="{ row }">
                <el-input v-model="row.tier_label" size="small" />
              </template>
            </el-table-column>
            <el-table-column label="让利率" width="120">
              <template #default="{ row }">
                <div class="rate-cell"><el-input-number v-model="row.discount_rate_pct" :min="0" :max="100" :step="0.1" :precision="2" :controls="false" size="small" /><span class="rate-suffix">%</span></div>
              </template>
            </el-table-column>
            <el-table-column label="目标利润率" width="120">
              <template #default="{ row }">
                <div class="rate-cell"><el-input-number v-model="row.target_margin_rate_pct" :min="0" :max="100" :step="0.1" :precision="2" :controls="false" size="small" /><span class="rate-suffix">%</span></div>
              </template>
            </el-table-column>
          </el-table>
          <div class="pricing-tier-hint">
            最深档（120 天）的让利率 30% 同时就是 SKU 资料页「清货让利上限」列。
            改「库龄起点」= 改滞销阈值，保存时关旧档、开新档，历史留档。
          </div>
        </el-tab-pane>
      </el-tabs>
      <template #footer>
        <el-button @click="pricingDrawer.visible = false">取消</el-button>
        <el-button v-if="pricingDrawer.tab === 'platform'" type="primary" :loading="saving" @click="savePlatformFeeRate">保存</el-button>
        <el-button v-else type="primary" :loading="saving" @click="savePricingPolicies">保存</el-button>
      </template>
    </el-drawer>
    <el-drawer
      v-model="batchDrawer.visible"
      title="物流批次"
      size="92%"
      destroy-on-close
      ><el-form
        :model="batchDrawer.form"
        inline
        label-width="90px"
        class="batch-form"
        ><el-form-item label="批次号"
          ><el-input v-model="batchDrawer.form.bill_no" /></el-form-item
        ><el-form-item label="物流服务商"
          ><el-input
            v-model="batchDrawer.form.logistics_provider" /></el-form-item
        ><el-form-item label="账单日期"
          ><el-date-picker
            v-model="batchDrawer.form.bill_date"
            type="date"
            value-format="YYYY-MM-DD" /></el-form-item
        ><el-form-item label="收货仓库"
          ><el-select v-model="batchDrawer.form.warehouse_code" filterable clearable><el-option v-for="item in operatingDimensions.warehouses" :key="item.warehouse_code" :label="`${item.warehouse_name} (${item.country_name})`" :value="item.warehouse_code" /></el-select></el-form-item
        ><el-form-item label="运输方式"
          ><el-select v-model="batchDrawer.form.transport_type"><el-option label="海运" value="sea" /><el-option label="空运" value="air" /><el-option label="铁路运输" value="rail" /></el-select></el-form-item
        ><el-form-item label="账单总额"
          ><el-input-number
            v-model="batchDrawer.form.total_amount"
            :min="0"
            :precision="2" /></el-form-item></el-form
      ><el-divider content-position="left">选择采购单（可多选）</el-divider
      ><el-table
        :data="purchaseOrders"
        border
        stripe
        @selection-change="selectedPurchaseOrders = $event"
        ><el-table-column type="selection" width="45" /><el-table-column
          prop="po_no"
          label="采购单号" /><el-table-column
          prop="warehouse"
          label="收货仓" /><el-table-column
          prop="status"
          label="状态" /><el-table-column
          prop="sku_count"
          label="SKU 数" /><el-table-column
          prop="received_qty"
          label="到货数量" /></el-table
      ><el-divider content-position="left"
        >账单明细（默认按体积计费，M 为敏感货）</el-divider
      ><el-table :data="batchDrawer.lines" border stripe class="bill-lines"
        ><el-table-column label="收货仓库" width="150"
          ><template #default="{ row }"
            ><el-select v-model="row.warehouse_code" size="small" filterable><el-option v-for="item in operatingDimensions.warehouses" :key="item.warehouse_code" :label="item.warehouse_name" :value="item.warehouse_code" /></el-select></template></el-table-column
        ><el-table-column label="采购单" width="150"
          ><template #default="{ row }"
            ><el-select v-model="row.po_id" size="small"
              ><el-option
                v-for="po in purchaseOrders"
                :key="po.po_id"
                :label="po.po_no"
                :value="po.po_id" /></el-select></template></el-table-column
        ><el-table-column label="SKU" width="150"
          ><template #default="{ row }"
            ><el-select v-model="row.sku_id" filterable size="small"
              ><el-option
                v-for="sku in skus"
                :key="sku.sku_id"
                :label="sku.sku_key"
                :value="sku.sku_id" /></el-select></template></el-table-column
        ><el-table-column label="件数" width="90"
          ><template #default="{ row }"
            ><el-input-number
              v-model="row.shipped_qty"
              :min="0"
              :controls="false"
              size="small" /></template></el-table-column
        ><el-table-column label="体积 m³" width="105"
          ><template #default="{ row }"
            ><el-input-number
              v-model="row.actual_total_volume_cbm"
              :class="{ 'volume-missing': volumeMissing(row) }"
              :min="0"
              :precision="4"
              :controls="false"
              size="small" /></template></el-table-column
        ><el-table-column label="毛重 kg" width="105"
          ><template #default="{ row }"
            ><el-input-number
              v-model="row.actual_total_weight_kg"
              :min="0"
              :precision="3"
              :controls="false"
              size="small" /></template></el-table-column
        ><el-table-column label="敏感货 M" width="90"
          ><template #default="{ row }"
            ><el-switch
              v-model="row.is_sensitive"
              @change="applyRuleToLine(row)" /></template></el-table-column
        ><el-table-column label="计费方式" width="110"
          ><template #default="{ row }"
            ><el-select v-model="row.billing_basis" size="small"
              ><el-option label="体积" value="volume" /><el-option
                label="重量"
                value="weight" /><el-option
                label="数量"
                value="quantity" /><el-option
                label="固定"
                value="fixed" /></el-select></template></el-table-column
        ><el-table-column label="费率" width="105"
          ><template #default="{ row }"
            ><el-input-number
              v-model="row.billing_unit_rate"
              :min="0"
              :precision="2"
              :controls="false"
              size="small"
              @change="
                row.rate_source = 'manual'
              " /></template></el-table-column
        ><el-table-column label="头程" width="105"
          ><template #default="{ row }"
            ><el-input-number
              v-model="row.headhaul_cost"
              :min="0"
              :precision="2"
              :controls="false"
              size="small" /></template></el-table-column
        ><el-table-column label="操作费" width="105"
          ><template #default="{ row }"
            ><el-input-number
              v-model="row.handling_cost"
              :min="0"
              :precision="2"
              :controls="false"
              size="small" /></template></el-table-column
        ><el-table-column label="尾程" width="105"
          ><template #default="{ row }"
            ><el-input-number
              v-model="row.last_mile_cost"
              :min="0"
              :precision="2"
              :controls="false"
              size="small" /></template></el-table-column
        ><el-table-column label="敏感货费" width="105"
          ><template #default="{ row }"
            ><el-input-number
              v-model="row.sensitive_surcharge"
              :min="0"
              :precision="2"
              :controls="false"
              size="small" /></template></el-table-column
        ><el-table-column label="行合计" width="105"
          ><template #default="{ row }">{{
            money(lineTotal(row))
          }}</template></el-table-column
        ></el-table
      >
      <el-alert
        v-if="unmappedPurchaseSkus.length"
        type="warning"
        :closable="false"
        show-icon
        title="以下采购单 SKU 待映射，无法生成物流账单行"
        :description="unmappedPurchaseSkus.join('；')"
      />
      <el-alert
        v-if="missingVolumeSkus.length"
        type="warning"
        :closable="false"
        show-icon
        title="以下 SKU 未填单件体积，按体积计费的金额会偏低（可继续保存）"
        :description="missingVolumeSkus.map((x) => x.label).join('；')"
      />
      <div class="batch-summary">
        <span>账单总额：{{ money(batchDrawer.form.total_amount) }}</span
        ><span>明细合计：{{ money(lineTotalSum) }}</span
        ><el-tag :type="batchBalanced ? 'success' : 'danger'">{{
          batchBalanced
            ? "金额一致"
            : `差额 ${money(batchDrawer.form.total_amount - lineTotalSum)}`
        }}</el-tag>
      </div>
      <template #footer
        ><el-button @click="batchDrawer.visible = false">关闭</el-button
        ><el-button type="primary" :loading="saving" @click="saveBatch"
          >保存草稿</el-button
        ></template
      ></el-drawer
    >
    <el-drawer v-model="bindingDrawer.visible" title="SKU 归属历史" size="520px"
      ><el-descriptions :column="1" border
        ><el-descriptions-item label="SPU">{{
          bindingDrawer.spu
        }}</el-descriptions-item></el-descriptions
      ><el-table :data="bindingDrawer.rows" stripe
        ><el-table-column prop="sku_id" label="SKU ID" /><el-table-column
          prop="effective_from"
          label="生效日期" /><el-table-column
          prop="effective_to"
          label="失效日期" /><el-table-column
          prop="binding_status"
          label="状态" /></el-table
    ></el-drawer>
    <el-drawer v-model="sellingPriceCheck.visible" title="基准售价巡检" size="760px"
      ><el-alert
        v-if="sellingPriceCheck.loading"
        type="info"
        :closable="false"
        show-icon
        title="正在巡检"
        description="带偏差校验要扫描历史成交数据，可能需要几十秒，请耐心等待。"
      /><el-alert
        v-else-if="sellingPriceCheck.error"
        type="error"
        :closable="false"
        show-icon
        title="巡检失败"
        :description="sellingPriceCheck.error"
      /><template v-else
        ><div class="selling-price-check-summary"
          ><el-tag type="danger"
            >偏差超阈值 {{ sellingPriceCheck.result?.deviation_count ?? 0 }}</el-tag
          ><el-tag type="warning"
            >过期未确认 {{ sellingPriceCheck.result?.stale_count ?? 0 }}</el-tag
          ><el-tag type="info"
            >算不出偏差 {{ sellingPriceCheck.result?.unverified_count ?? 0 }}</el-tag
          ></div
        ><el-alert
          type="warning"
          :closable="false"
          show-icon
          title="算不出偏差 ≠ 没问题"
          description="算不出来是因为缺历史成交数据，不是检查通过。这些 SKU 需要人工看一眼。"
        /><div class="selling-price-check-block"
          ><div class="selling-price-check-title"
            >偏差超阈值（与历史成交价中位数偏离超过 30%）</div
          ><el-table :data="sellingPriceCheckGroups.deviation" stripe size="small" border
            ><el-table-column prop="sku_key" label="SKU" width="150" /><el-table-column
              label="基准售价"
              width="100"
              ><template #default="{ row }">{{ money(row.reference_selling_price) }}</template></el-table-column
            ><el-table-column label="历史成交价中位数" width="140"
              ><template #default="{ row }">{{ money(row.deviation?.median_price) }}</template></el-table-column
            ><el-table-column label="偏差" width="90"
              ><template #default="{ row }">{{ sellingPriceDeviationText(row) }}</template></el-table-column
            ><el-table-column label="样本行数" width="90"
              ><template #default="{ row }">{{ row.deviation?.sample_size ?? "-" }}</template></el-table-column
            ></el-table
          ></div
        ><div class="selling-price-check-block"
          ><div class="selling-price-check-title">过期未确认（超过 90 天没确认）</div
          ><el-table :data="sellingPriceCheckGroups.stale" stripe size="small" border
            ><el-table-column prop="sku_key" label="SKU" width="150" /><el-table-column
              label="基准售价"
              width="100"
              ><template #default="{ row }">{{ money(row.reference_selling_price) }}</template></el-table-column
            ><el-table-column label="确认日期" width="140"
              ><template #default="{ row }">{{ formatConfirmedAt(row.selling_price_confirmed_at) }}</template></el-table-column
            ><el-table-column label="账龄(天)" width="90"
              ><template #default="{ row }">{{ row.age_days ?? "-" }}</template></el-table-column
            ></el-table
          ></div
        ><div class="selling-price-check-block"
          ><div class="selling-price-check-title">算不出偏差（缺输入，不等于检查通过）</div
          ><el-table :data="sellingPriceCheckGroups.unverified" stripe size="small" border
            ><el-table-column prop="sku_key" label="SKU" width="150" /><el-table-column
              label="基准售价"
              width="100"
              ><template #default="{ row }">{{ money(row.reference_selling_price) }}</template></el-table-column
            ><el-table-column label="算不出的原因" min-width="200"
              ><template #default="{ row }">{{ sellingPriceUnverifiedReason(row.deviation?.reason) }}</template></el-table-column
            ></el-table
          ></div
        ></template
      ><template #footer
        ><el-button @click="sellingPriceCheck.visible = false">关闭</el-button
        ></template
      ></el-drawer
    >
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Check, Plus, QuestionFilled } from "@element-plus/icons-vue";
import productCenterApi from "@/api/productCenter";
import { createSpuSearch } from "./productCenterSpuOptions";
import { useUserStore } from "@/stores/user";

const userStore = useUserStore();
const activeTab = ref("spu");
const costTab = ref("rules");
const saving = ref(false);
const selectedSpus = ref([]);
const loadingSpus = ref(false);
const loadingRules = ref(false);
const loadingSkus = ref(false);
const loadingBills = ref(false);

// SKU 资料 tab 中视觉标记为可填项的列名（仅改表头颜色，不动字段必填校验）
// ⚠️ 「基准售价」2026-10-21 起移出本列表：蓝色表头在数据表里读起来像可点击链接，
// 而它其实是「这列可以不填」的标记，容易被误读。按要求改为与其他列一致的黑色。
const skuOptionalColumnLabels = ["规格", "重量 kg", "箱规（件/箱）", "基准售价来源"];
const skuHeaderCellStyle = ({ column }) => {
  if (skuOptionalColumnLabels.includes(column.label)) {
    return { color: "#79bbff", fontWeight: "normal" };
  }
  return {};
};
const spus = ref([]);
// SPU 值域 —— 两个口径的候选集都由**后端**给出，前端不再从「SPU 管理」tab
// 的分页表格数据里顺带拿（那只有当前页 20 条，第 36 个款永远选不到）。
//   * spuBrowse    —— 浏览口径：在售的款。用于工具栏「所属 SPU」**筛选**
//                     （筛选是查询条件，敲什么编码都能查）。
//   * spuAssignable —— 可绑定口径：还能挂新 SKU 的款。用于 SKU 行的**赋值 / 换款**
//                     （赋值是外键，款必须真实存在且现在还允许挂）。
const spuBrowse = createSpuSearch((params) => productCenterApi.listSpuOptions(params));
const spuAssignable = createSpuSearch((params) =>
  productCenterApi.listSpuAssignableOptions(params),
);
const skus = ref([]);
// SKU 表的候选集 = 可绑定候选 **∪** 存量行当前挂着的款。
// ⚠️ 为什么要并上后者：可绑定口径**不含**已淘汰/已删除的款，
//    而存量行当前挂着的款未必还在可绑定范围里 ——
//    不并进来的话，运营打开下拉会看不到自己那一行的当前值，
//    看起来像「这货挂错了款」。
// ⚠️ 搜索结果**仍然**只给可绑定的款（赋值是外键，不能造出挂不上的款）。
const spuAssignableOptions = computed(() => {
  const merged = new Map();
  for (const item of spuAssignable.options) merged.set(item.value, item);
  for (const row of skus.value) {
    if (row.spu && !merged.has(row.spu)) {
      merged.set(row.spu, {
        value: row.spu,
        label: row.spu,
        name: row.spu_name || "",
      });
    }
  }
  return Array.from(merged.values());
});
const categories = ref([]);
const rules = ref([]);
const storageRules = ref([]);
const purchaseOrders = ref([]);
const logisticsBatches = ref([]);
const operatingProfiles = ref([]);
const operatingDimensions = reactive({
  platforms: [],
  spus: [],
  skus: [],
  warehouses: [],
});
const loadingOperating = ref(false);
const loadingStorageRules = ref(false);
const spuTotal = ref(0);
const skuTotal = ref(0);
const operatingTotal = ref(0);
const skuSpuFilter = ref("");
const operatingQuery = reactive({
  platform_code: "",
  spu: "",
  sku_id: "",
  warehouse_code: "",
  transport_type: "",
  // 阶段 7：「仅有库存」默认打开 —— 测算表先看**这个仓还有货**的 SKU。
  // 筛选在后端做（前端筛只会筛当前页，总数对不上、翻页会漏行）。
  only_in_stock: true,
  page: 1,
  page_size: 20,
});
const pricingDrawer = reactive({
  visible: false,
  tab: "platform",
  label: "",
  form: {
    default_fee_rate_pct: null,
    default_creator_commission_rate_pct: null,
    other_cost_rate_pct: null,
    fee_rate_effective_from: "",
    fee_rate_source: "",
    fee_rate_version: "",
  },
  policies: [],
});
// 成本率合计 = 平台佣金率 + 默认达人佣金率 + 平台其他成本率（仅作成本结构展示）
const costRateTotalPct = computed(() => {
  const form = pricingDrawer.form;
  const total = [form.default_fee_rate_pct, form.default_creator_commission_rate_pct, form.other_cost_rate_pct]
    .map((value) => Number(value) || 0)
    .reduce((sum, value) => sum + value, 0);
  return total.toFixed(2);
});
// 默认底线基数 = 默认达人佣金率 + 平台其他成本率（平台佣金率已含在 other_cost_rate 内）
const baseRatePct = computed(() => {
  const form = pricingDrawer.form;
  const total = [form.default_creator_commission_rate_pct, form.other_cost_rate_pct]
    .map((value) => Number(value) || 0)
    .reduce((sum, value) => sum + value, 0);
  return total.toFixed(2);
});
const billStatus = ref("");
const selectedPurchaseOrders = ref([]);
const unmappedPurchaseSkus = ref([]);
// 单件体积未填的 SKU —— 提示但不阻断：账单金额会偏低，可由运营自行决定是否先补资料
const missingVolumeSkus = ref([]);
const dirtyRows = ref(new Set());
const dirtyRuleRows = ref(new Set());
const spuQuery = reactive({
  keyword: "",
  biz_status: "",
  page: 1,
  page_size: 20,
});
const skuQuery = reactive({ keyword: "", status: "", page: 1, page_size: 20 });
// SKU 资料页的定价底线按**平台**算（阶段 2.1）：平台成本率不同，底线就不同。
// 不选平台时后端回落到历史 basis 平台，界面要能看出来用的是哪套口径。
const skuPricingPlatform = ref("");
const batchDrawer = reactive({
  visible: false,
  editing: false,
  billId: null,
  form: {
    bill_no: "",
    logistics_provider: "",
    bill_date: "",
    warehouse_code: "",
    transport_type: "sea",
    total_amount: 0,
    currency: "CNY",
  },
  lines: [],
});
const bindingDrawer = reactive({ visible: false, spu: "", rows: [] });
const categoryCode = (item) => item.category_code || item.code;
const parentCode = (item) => item.parent_category_code || item.parent_code;
// ⚠️ 「不可选品类」只以数据库的 `is_selectable` 为准 ——
//    这里曾硬编码过一份 PET_DAILY 清单，与数据库重复定义 ⇒ 改库不会改前端。
const l1Categories = computed(() =>
  categories.value.filter((item) => item.level === 1 || !parentCode(item)),
);
const childCategories = (code) =>
  categories.value.filter(
    (item) =>
      (item.level === 2 || parentCode(item)) && parentCode(item) === code,
  );
const canManagePlatformFee = computed(() =>
  userStore.hasRole(["admin", "manager", "finance"]),
);
const filteredOperatingSkus = computed(() => {
  if (!operatingQuery.spu) return operatingDimensions.skus || [];
  return (operatingDimensions.skus || []).filter(
    (item) => item.spu === operatingQuery.spu || item.spu_code === operatingQuery.spu,
  );
});
const referenceStorageDays = (turnoverClass) =>
  ({ fast: 30, normal: 60, slow: 90 })[turnoverClass] || null;
const referenceLogisticsCost = (row) =>
  row.reference_logistics_cost ?? row.expected_logistics_cost ?? null;
const referenceStorageCost = (row) =>
  row.reference_storage_cost ?? row.expected_storage_cost ?? null;
const spuDirty = computed(() =>
  spus.value.filter(
    (row) => row.__new || dirtyRows.value.has(`spu:${row.spu}`),
  ),
);
const skuDirty = computed(() =>
  skus.value.filter(
    (row) =>
      row.__new || dirtyRows.value.has(`sku:${row.sku_id || row.sku_key}`),
  ),
);
const ruleDirty = computed(() =>
  rules.value.filter(
    (row) => row.__new || dirtyRuleRows.value.has(row.rule_id),
  ),
);
const markDirty = (kind, row) =>
  dirtyRows.value.add(
    `${kind}:${row[kind === "spu" ? "spu" : "sku_id"] || row.sku_key}`,
  );
// 一级品类变更：清空二级品类 **并且** 标脏。
// ⚠️ 这两件事必须放在同一个 handler 里 —— 一个 el-select 只能挂一个 @change，
// 分开挂会导致第二次覆盖第一次，改了品类却不标脏 → 保存时这行不在 payload 里 → 静默丢失。
const onSpuL1CategoryChange = (row) => {
  row.category_l2_code = "";
  markDirty("spu", row);
};
// 换款（SKU 行的 SPU 单元格改动）—— 走**已有的批量保存通道**（bulk_save_skus），
// 不另开一条写入路径：归属关系有生效区间、有归档、有审计，
// 另写一条必然漏掉其中一半。
// ⚠️ 换款后旧的生效日不再适用 —— 新归属从**保存那天**起算，
//    所以先把它清掉，别让运营看到「自 2026-09-14」配着一个刚换的款。
const onSkuSpuChange = (row) => {
  row.spu_effective_from = null;
  markDirty("sku", row);
};
// 已软删的 SPU 灰显 —— 让运营一眼看出这行「已删除但可恢复」，避免误当成在售品编辑
const spuRowClass = ({ row }) => (row.active === false ? "spu-inactive-row" : "");
const markRuleDirty = (row) => dirtyRuleRows.value.add(row.rule_id);
const blankSpu = () => ({
  __new: true,
  spu: "",
  spu_name: "",
  category_l1_code: "",
  category_l2_code: "",
  biz_status: "candidate",
  owner_user_id: null,
  logistics_damage_rate: null,
  return_loss_rate: null,
});
const blankSku = () => ({
  __new: true,
  sku_key: "",
  sku_name: "",
  specification: "",
  spu: "",
  weight_kg: null,
  package_length_cm: null,
  package_width_cm: null,
  package_height_cm: null,
  unit_volume_cbm: null,
  units_per_carton: null,
  default_purchase_cost: null,
  expected_logistics_cost: null,
  expected_storage_cost: null,
  reference_selling_price: null,
  selling_price_source: "manual",
  purchase_cost_source: "manual",
  purchase_cost_confidence: "low",
  creator_commission_rate: null,
});
// --- SKU 定价底线的展示辅助 ---
const PRICING_SOURCE_LABELS = {
  manual_override: "人工设定",
  // ⚠️ 必须与后端 product_selling_price_service.PRICING_SOURCE_LABELS 逐字一致。
  //    之前这里写「折扣纪律」、后端写「基准售价纪律」，同一个东西在同一个页面上
  //    出现两个名字（预览提示来自后端、来源标签来自前端），运营会以为是两回事。
  discount_guard: "基准售价纪律",
  cost_floor: "成本底线",
  unavailable: "无法计算",
};
const PRICING_SOURCE_TOOLTIPS = {
  manual_override: "有人工覆盖值，以上面填写的数字为准（变更留审计）",
  discount_guard: "基准售价 × (1 − 当前档让利率)",
  cost_floor: "采购成本与目标利润率反解出的保本价",
  unavailable: "数据不全，最低售价算不出来",
};
const pricingSourceLabel = (source) => PRICING_SOURCE_LABELS[source] || "-";
const pricingSourceTagType = (source) =>
  ({ manual_override: "danger", discount_guard: "warning", cost_floor: "success" })[source] || "info";

// ---------------------------------------------------------------------------
// 阶段 4 · 基准售价治理（前端部分）
// ---------------------------------------------------------------------------

// 基准售价来源枚举。
// ⚠️ 之前这里是自由文本，运营能随手写「客户报价」「展会价」……，
// 而后端只认这三个值 —— 填了枚举外的东西等于「没有来源」，
// 历史脏值也只能靠后端迁移归一化。所以改成下拉，让来源只能是这三档。
const SELLING_PRICE_SOURCE_OPTIONS = [
  { value: "platform_listing", label: "平台挂牌价" },
  { value: "erp", label: "ERP 价" },
  { value: "manual", label: "人工填写" },
];

// --- 基准售价即时影响预览（阶段 4 工具 3） ---
//
// 为什么必须有「预览」：基准售价填错最典型的后果是**纪律线被顶上去**，
// 货直接卖不动（护栏把品拦死）。填完要等保存、甚至等下一个巡检周期才发现，
// 代价太大。预览与保存走服务端同一套定价函数，
// 所以「预览说涨到 63」与「保存后变成 63」必然一致。
//
// ⚠️ 预览是**假设**：不写库、不写审计。界面上必须说清「保存后才会生效」。
const SELLING_PRICE_PREVIEW_DEBOUNCE_MS = 300;
// 抬价超过这个幅度才提示 —— 与后端 _preview_warnings 的阈值一致。
// 前端不要另立一套口径，否则两边提示会打架。
const SELLING_PRICE_PREVIEW_WARN_PCT = 20;
// 人工覆盖的平台：底线根本不会跟着基准售价动。
// ⚠️ 这里**不能**显示成「涨到 63」—— 那是在报一个根本没发生的变化。
const SELLING_PRICE_OVERRIDE_LOCKED_TEXT = "该平台已有人工覆盖，改基准售价不生效";

// 预览状态按 SKU 分开存。
// ⚠️ 不能挂在 row 上：row 会被 loadSkus 整表替换，预览结果会跟着一起消失，
// 运营刚打完字就看到预览没了，比不给预览更糟。
const sellingPricePreviews = reactive({});
const sellingPricePreviewTimers = reactive({});

const sellingPricePreviewKey = (row) => (row?.sku_id ? String(row.sku_id) : "");
// 只读不建：没碰过的行不该凭空多出一个空预览块。
const sellingPricePreviewState = (row) => {
  const key = sellingPricePreviewKey(row);
  return key ? sellingPricePreviews[key] || null : null;
};
const ensureSellingPricePreview = (row) => {
  const key = sellingPricePreviewKey(row);
  if (!key) return null;
  if (!sellingPricePreviews[key]) {
    sellingPricePreviews[key] = {
      sku_id: row.sku_id,
      platforms: [],
      warnings: [],
      loading: false,
      error: "",
      reference: null,
      seq: 0,
    };
  }
  return sellingPricePreviews[key];
};
// 「从 X 变为 Y」的文案。三种边界都得说清楚：
// 算不出来既不是 0 也不是「没变化」—— 直接套模板会显示成「从 - 变为 -」。
const sellingPriceChangeText = (item) => {
  const current = item.min_selling_price_current;
  const next = item.min_selling_price_preview;
  if (current == null && next == null) {
    return "资料不全，最低售价算不出来，改基准售价也不影响";
  }
  if (current == null) return `最低售价将从算不出来变为 ${money(next)}`;
  if (next == null) return `最低售价将从 ${money(current)} 变为算不出来`;
  return `最低售价将从 ${money(current)} 变为 ${money(next)}`;
};
const applySellingPricePreview = (state, res) => {
  state.platforms = (res?.platforms || []).map((item) => {
    const locked = !!item.override_locked;
    const changePct = item.change_pct == null ? null : Number(item.change_pct);
    return {
      platform_code: item.platform_code,
      platformName: platformDisplayName(item.platform_code),
      locked,
      lockedText: SELLING_PRICE_OVERRIDE_LOCKED_TEXT,
      changeText: sellingPriceChangeText(item),
      pctText:
        changePct == null ? "" : `${changePct >= 0 ? "+" : ""}${changePct.toFixed(1)}%`,
      sourceLabel: item.source_preview ? pricingSourceLabel(item.source_preview) : "",
      sourceTagType: pricingSourceTagType(item.source_preview),
      warn:
        !locked &&
        changePct != null &&
        changePct >= SELLING_PRICE_PREVIEW_WARN_PCT,
      message: item.message || "",
    };
  });
  state.warnings = res?.warnings || [];
  state.reference = res?.reference_selling_price_preview ?? null;
};
// 输入防抖：运营连续敲数字时不该每敲一下就请求一次后端。
const scheduleSellingPricePreview = (row) => {
  const key = sellingPricePreviewKey(row);
  // 新增行还没落库，后端没有这条 SKU ⇒ 算不了预览，也没有「当前值」可比。
  if (!key) return;
  if (sellingPricePreviewTimers[key]) {
    clearTimeout(sellingPricePreviewTimers[key]);
  }
  sellingPricePreviewTimers[key] = setTimeout(() => {
    sellingPricePreviewTimers[key] = null;
    runSellingPricePreview(row);
  }, SELLING_PRICE_PREVIEW_DEBOUNCE_MS);
};
const runSellingPricePreview = async (row) => {
  const key = sellingPricePreviewKey(row);
  if (!key) return;
  const state = ensureSellingPricePreview(row);
  // 请求序号：连着改价会连发多个请求，后到的**旧**响应不能盖掉新结果。
  const seq = state.seq + 1;
  state.seq = seq;
  state.loading = true;
  state.error = "";
  try {
    const res = await productCenterApi.previewSkuSellingPrice(
      row.sku_id,
      row.reference_selling_price ?? null,
    );
    if (state.seq !== seq) return;
    applySellingPricePreview(state, res);
  } catch {
    if (state.seq !== seq) return;
    // 预览失败**静默降级**：清掉上一次的结果，不弹错误框、不打断输入。
    // 理由：预览与保存走同一套定价口径，给一个来路不明的数字比不给更糟。
    state.platforms = [];
    state.warnings = [];
    state.error = "预览暂不可用，保存后以实际结果为准";
  } finally {
    if (state.seq === seq) state.loading = false;
  }
};
// 确认日期只显示到分钟：秒对运营没有意义，反而把列撑宽。
const formatConfirmedAt = (value) => {
  if (!value) return "-";
  const text = String(value).trim();
  if (!text) return "-";
  const normalized = text.replace("T", " ").replace("Z", "");
  return normalized.length > 16 ? normalized.slice(0, 16) : normalized;
};

// --- 基准售价巡检（阶段 4 工具 4） ---
//
// ⚠️ 这个接口带偏差校验要扫历史成交事实表，一次调用几十秒 ——
//    只能运营显式点击触发，绝不能挂在 loadSkus 后面自动跑
//    （那会把每次列表刷新都变成一次全表扫描）。
const sellingPriceCheck = reactive({
  visible: false,
  loading: false,
  error: "",
  result: null,
});
const runSellingPriceCheck = async () => {
  if (sellingPriceCheck.loading) return;
  sellingPriceCheck.visible = true;
  sellingPriceCheck.loading = true;
  sellingPriceCheck.error = "";
  try {
    const res = await productCenterApi.checkSkuSellingPrice({ includeDeviation: true });
    sellingPriceCheck.result = res || null;
  } catch (error) {
    sellingPriceCheck.result = null;
    sellingPriceCheck.error = error?.message || "基准售价巡检失败";
  } finally {
    sellingPriceCheck.loading = false;
  }
};
// 巡检结果分三类。三类**不能合并**：
// 「算不出偏差」不是「没问题」—— 合并就等于把没检查过的说成检查过了。
const sellingPriceCheckGroups = computed(() => {
  const items = sellingPriceCheck.result?.items || [];
  return {
    deviation: items.filter(
      (item) => item.deviation?.available && item.deviation?.exceeds_threshold,
    ),
    stale: items.filter((item) => item.stale),
    unverified: items.filter(
      (item) => item.deviation && item.deviation.available === false,
    ),
  };
});
// 「算不出偏差」的原因码 → 中文。算不出来要说清缺什么，不能报成没问题。
const SELLING_PRICE_UNVERIFIED_REASONS = {
  no_reference_price: "没有基准售价",
  no_transaction_price: "没有历史成交记录",
};
const sellingPriceUnverifiedReason = (reason) =>
  SELLING_PRICE_UNVERIFIED_REASONS[reason] || "数据不足，算不出偏差";
// 偏差百分比：后端给的是「相对历史成交价中位数」的有符号偏差。
const sellingPriceDeviationText = (item) => {
  const value = item?.deviation?.deviation_pct;
  if (value == null) return "-";
  const number = Number(value);
  return `${number >= 0 ? "+" : ""}${number.toFixed(1)}%`;
};
// --- 平台级最低售价底线（阶段 2.1b） ---
// 底线是 **SKU × 平台** 的量：TikTok 与 Shopee 的平台其他成本率差一截
// （27.27% vs 41.65%），同一件商品在两个平台有两条不同的底线。
// 所以「最低售价」列按平台分行，人工覆盖也按平台分行、各自独立。
//
// 平台名取自经营维度里的销售平台；找不到就退回平台代码本身。
const platformDisplayName = (platformCode) => {
  const hit = (operatingDimensions.platforms || []).find(
    (item) => item.platform_code === platformCode,
  );
  return hit?.name || platformCode;
};
// 把后端下发的 {平台代码: {...}} 摊平成可直接渲染的分行
const skuPricingPlatformRows = (row) =>
  Object.entries(row.min_selling_price_by_platform || {}).map(
    ([platformCode, item]) => ({
      platform_code: platformCode,
      name: platformDisplayName(platformCode),
      min_selling_price: item?.min_selling_price ?? null,
      min_selling_price_override: item?.min_selling_price_override ?? null,
      min_selling_price_source: item?.min_selling_price_source ?? null,
      min_selling_price_is_override: !!item?.min_selling_price_is_override,
    }),
  );
// 人工覆盖不再随 SKU 主数据一起保存（阶段 2.1b），而是走平台级独立接口
// （PATCH /api/skus/{sku_id}/pricing-override）。
// 所以输入框里的值必须单独存着 —— 不能挂在 row 上：row 会在重新拉取后被整体替换。
const pricingOverrideDrafts = reactive({});
const pricingOverrideKey = (row, platformCode) =>
  `${row.sku_id || row.sku_key || "new"}::${platformCode}`;
const platformOverrideDraft = (row, item) => {
  const draft = pricingOverrideDrafts[pricingOverrideKey(row, item.platform_code)];
  if (draft !== undefined) return draft;
  return item.min_selling_price_override ?? null;
};
const setPlatformOverrideDraft = (row, item, value) => {
  const num = value == null ? null : Number(value);
  // 0 不是「不设覆盖」，而是「把底线压到 0」= 把护栏关掉 ⇒ 与后端一致，当成没填。
  pricingOverrideDrafts[pricingOverrideKey(row, item.platform_code)] =
    num == null || !Number.isFinite(num) || num <= 0 ? null : num;
};
// 输入框里填了、但还没保存的覆盖值。
// 只读值显示的是**服务端已保存**的生效值，运营在输入框里改完还没点「保存覆盖」时，
// 上方那个数不会变——容易被误读成「我改了没生效」。
// 这个函数把「待生效的覆盖值」挑出来，界面据此改成显示「保存后生效：¥X」。
const pendingPlatformOverride = (row, item) => {
  const typed = platformOverrideDraft(row, item);
  if (typed == null) return null;
  // 之前没设过覆盖值 -> 现在填的是新增
  if (!item.min_selling_price_is_override) return Number(typed);
  // 之前设过覆盖值 -> 已保存的生效值就等于当时的覆盖值；与现在输入的不一致即为待生效
  if (item.min_selling_price == null) return Number(typed);
  if (Number(typed) !== Number(item.min_selling_price)) return Number(typed);
  return null;
};
const savingOverrideKey = ref("");
const overrideSavingKey = (row, item) => pricingOverrideKey(row, item.platform_code);
// 平台级覆盖值的报错文案：后端走统一错误信封，结构化业务码在 error.detail.code。
const pricingOverrideErrorText = (error) => {
  const detail = readApiErrorDetail(error);
  if (detail?.code === "pricing_override_unknown_platform") {
    return `平台 ${detail.platform_code || ""} 不存在，不能设置底线`;
  }
  if (detail?.code === "pricing_override_platform_not_sales") {
    return `平台 ${detail.platform_code || ""} 不是销售平台，不能设置底线`;
  }
  return detail?.reason || error?.message || "保存平台最低售价失败";
};
// 保存某个平台的最低售价人工覆盖（平台级独立接口，不走 SKU 主数据保存）。
// ⚠️ 为什么不能挂在 SKU 主数据上：`core.dim_erp_sku` 参与「采集机 → 云端」同步，
// 同步脚本对它做 `TRUNCATE ... RESTART IDENTITY CASCADE` ⇒ 覆盖值每次同步都被抹掉，
// 护栏上限形同虚设。
const savePlatformOverride = async (row, item) => {
  if (!row.sku_id) {
    ElMessage.warning("请先保存这个 SKU，再设置平台底线");
    return;
  }
  const value = platformOverrideDraft(row, item);
  if (value == null) {
    ElMessage.warning("请先填写人工覆盖值");
    return;
  }
  savingOverrideKey.value = overrideSavingKey(row, item);
  try {
    await productCenterApi.setSkuPricingOverride(row.sku_id, {
      platform_code: item.platform_code,
      min_selling_price_override: Number(value),
    });
    delete pricingOverrideDrafts[pricingOverrideKey(row, item.platform_code)];
    await refreshSkuPricingRow(row);
    ElMessage.success(`${item.name} 的最低售价底线已保存`);
  } catch (error) {
    ElMessage.error(pricingOverrideErrorText(error));
  } finally {
    savingOverrideKey.value = "";
  }
};
// 「重置为自动值」= 同一个接口，`min_selling_price_override` 传 null
const resetPlatformOverride = async (row, item) => {
  if (!row.sku_id) {
    ElMessage.warning("请先保存这个 SKU，再重置平台底线");
    return;
  }
  savingOverrideKey.value = overrideSavingKey(row, item);
  try {
    await productCenterApi.setSkuPricingOverride(row.sku_id, {
      platform_code: item.platform_code,
      min_selling_price_override: null,
    });
    delete pricingOverrideDrafts[pricingOverrideKey(row, item.platform_code)];
    await refreshSkuPricingRow(row);
    ElMessage.success(`${item.name} 已重置为自动值`);
  } catch (error) {
    ElMessage.error(pricingOverrideErrorText(error));
  } finally {
    savingOverrideKey.value = "";
  }
};
const addSpuRow = () => spus.value.unshift(blankSpu());
const addSkuRow = () => skus.value.unshift(blankSku());
const addRuleRow = () =>
  rules.value.unshift({
    __new: true,
    logistics_provider: "",
    warehouse_code: "",
    transport_type: "sea",
    cargo_class: "normal",
    is_default: false,
    billing_basis: "volume",
    freight_unit_rate: null,
    effective_from: "",
  });
const loadSpus = async () => {
  loadingSpus.value = true;
  try {
    const res = await productCenterApi.listSpus({
      ...spuQuery,
      // 已软删的 SPU 必须列出来，否则「恢复」按钮永远不可达（软删就变成不可逆了）。
      // ⚠️ 参数叫 include_soft_deleted（不是 include_inactive）——
      //    「已删除」与「停用」在这个域里是两件事。
      include_soft_deleted: true,
    });
    spus.value = (res.data || []).map((row) => ({
      ...row,
      category_l1_code: row.category_l1_code || row.category_l1 || "",
      category_l2_code: row.category_l2_code || row.category_l2 || "",
    }));
    spuTotal.value = res.total || 0;
  } catch (error) {
    ElMessage.error(error.message || "加载 SPU 失败");
  } finally {
    loadingSpus.value = false;
  }
};
const loadSkus = async () => {
  loadingSkus.value = true;
  try {
    const res = await productCenterApi.listSkus({
      ...skuQuery,
      spu: skuSpuFilter.value || undefined,
      status: skuQuery.status || undefined,
      // 底线按平台算：不传平台后端会回落到历史 basis 平台（TikTok），
      // 那对 Shopee 是错的（偏低三到七成）。
      platform_code: skuPricingPlatform.value || undefined,
    });
    skus.value = (res.data || []).map((row) => ({
      ...row,
      data_completeness: row.data_completeness || row.cost_completeness,
    }));
    skuTotal.value = res.total || 0;
  } catch (error) {
    ElMessage.error(error.message || "加载 SKU 失败");
  } finally {
    loadingSkus.value = false;
  }
};
// 保存平台级人工覆盖后，**只把这一行的定价数据**合并回来。
// ⚠️ 不能整表重载（loadSkus）：整表重载会把运营在同一页还没保存的其它字段编辑冲掉
// —— 覆盖值保存与 SKU 主数据保存是两条互不相干的流程，谁都不该把对方的数据擦掉。
const refreshSkuPricingRow = async (row) => {
  const res = await productCenterApi.listSkus({
    ...skuQuery,
    spu: skuSpuFilter.value || undefined,
    status: skuQuery.status || undefined,
    platform_code: skuPricingPlatform.value || undefined,
  });
  const fresh = (res.data || []).find((item) => item.sku_id === row.sku_id);
  if (!fresh) return;
  for (const field of [
    "min_selling_price",
    "min_selling_price_source",
    "min_selling_price_is_override",
    "min_selling_price_override",
    "min_selling_price_by_platform",
    "pricing_tier_label",
    "pricing_days_since_restock",
    "pricing_tier_source",
  ]) {
    row[field] = fresh[field];
  }
};
const loadCategories = async () => {
  try {
    categories.value = await productCenterApi.listCategories({
      // 停用的与不可选的都要拿到：存量 SPU 上可能还挂着它们（要能读出来），
      // 但新分配时前端会按 is_selectable 置灰。
      include_inactive: true,
      include_unselectable: true,
    });
  } catch {
    categories.value = [];
  }
};
const _PROVIDER_RULE_PATCH_FIELDS = [
  "logistics_provider",
  "warehouse_code",
  "transport_type",
  "cargo_class",
  "is_sensitive",
  "is_default",
  "billing_basis",
  "billing_unit",
  "freight_unit_rate",
  "sensitive_surcharge_mode",
  "sensitive_surcharge_rate",
  "effective_from",
  "effective_to",
  "status",
  "source",
  "version",
  "notes",
];
const _providerRuleOriginal = (row) => {
  const snapshot = {};
  for (const field of _PROVIDER_RULE_PATCH_FIELDS) snapshot[field] = row[field];
  return snapshot;
};
const _sortProviderRules = (rows) =>
  [...rows].sort((a, b) => {
    const wa = a.warehouse_code || "";
    const wb = b.warehouse_code || "";
    if (wa !== wb) return wa.localeCompare(wb);
    if (a.logistics_provider !== b.logistics_provider) {
      return (a.logistics_provider || "").localeCompare(b.logistics_provider || "");
    }
    return (a.effective_from || "").localeCompare(b.effective_from || "");
  });
const loadRules = async () => {
  loadingRules.value = true;
  try {
    const rows = await productCenterApi.listProviderRules({
      status: "active",
    });
    console.info(
      "[loadRules] OK rows=",
      rows.length,
      "cookies=",
      document.cookie || "<none>",
    );
    rules.value = _sortProviderRules(
      rows.map((row) => ({ ...row, __original: _providerRuleOriginal(row) })),
    );
  } catch (error) {
    const status = error?.response?.status;
    console.error(
      "[loadRules] FAIL status=",
      status,
      "code=",
      error?.code,
      "msg=",
      error?.message,
      "cookies=",
      document.cookie || "<none>",
    );
    rules.value = [];
    ElMessage.error(error.message || "加载物流规则失败");
  } finally {
    loadingRules.value = false;
  }
};
const loadStorageRules = async () => {
  loadingStorageRules.value = true;
  try {
    storageRules.value = (await productCenterApi.listWarehouseStorageRules({
      include_inactive: true,
    })).map((row) => ({
      ...row,
      __original: {
        unit_rate_cny: row.unit_rate_cny,
        effective_from: row.effective_from,
        effective_to: row.effective_to,
      },
    }));
  } catch (error) {
    storageRules.value = [];
    ElMessage.error(error.message || "加载仓储规则失败");
  } finally {
    loadingStorageRules.value = false;
  }
};
const addStorageRuleRow = () =>
  storageRules.value.unshift({
    __new: true,
    warehouse_code: "",
    unit_rate_cny: null,
    label_fee: null,
    effective_from: new Date().toISOString().slice(0, 10),
    status: "active",
    source: "manual",
    version: "v1",
    notes: "",
  });
const storageRulePayload = (row) => {
  const { __new, __original, rule_id, billing_basis, billing_unit, ...payload } = row;
  if (!__new) {
    for (const field of ["unit_rate_cny", "label_fee", "effective_from", "effective_to"]) {
      if (payload[field] === __original?.[field]) delete payload[field];
    }
  }
  return payload;
};
const saveStorageRule = async (row) => {
  try {
    if (!row.warehouse_code || row.unit_rate_cny == null || !row.effective_from) {
      throw new Error("请填写收货仓库、仓储单价和生效日期");
    }
    if (row.__new) await productCenterApi.createWarehouseStorageRule(storageRulePayload(row));
    else await productCenterApi.updateWarehouseStorageRule(row.rule_id, storageRulePayload(row));
    await loadStorageRules();
    ElMessage.success("仓储规则已保存");
  } catch (error) {
    ElMessage.error(error.message || "保存仓储规则失败");
  }
};
const disableStorageRule = async (row) => {
  try {
    await ElMessageBox.confirm("停用后该规则不再用于新的利润测算。", "停用仓储规则", { type: "warning" });
    await productCenterApi.updateWarehouseStorageRule(row.rule_id, { status: "inactive" });
    await loadStorageRules();
    ElMessage.success("仓储规则已停用");
  } catch (error) {
    if (error !== "cancel") ElMessage.error(error.message || "停用仓储规则失败");
  }
};
const enableStorageRule = async (row) => {
  try {
    await ElMessageBox.confirm(
      `将基于此规则（${row.warehouse_code} ${row.version || ""}）创建一条新 active 版本，原规则作为历史保留。`,
      "启用仓储规则",
      { type: "warning" },
    );
    await productCenterApi.createWarehouseStorageRule({
      warehouse_code: row.warehouse_code,
      unit_rate_cny: row.unit_rate_cny,
      effective_from: new Date().toISOString().slice(0, 10),
      status: "active",
      source: row.source || "manual",
      version: `${row.version || "v1"}-restored`,
      notes: row.notes || "",
    });
    await loadStorageRules();
    ElMessage.success("仓储规则已启用为新版本");
  } catch (error) {
    if (error !== "cancel") ElMessage.error(error.message || "启用仓储规则失败");
  }
};
const removeStorageRuleRow = async (row) => {
  try {
    await ElMessageBox.confirm(
      "删除后该仓储规则将从列表中移除。历史利润记录中的 storage_rule_id 会被置空（但 storage_rule_version 字符串保留，可追溯历史）。",
      "删除仓储规则",
      { type: "warning" },
    );
    await productCenterApi.deleteWarehouseStorageRule(row.rule_id);
    storageRules.value = storageRules.value.filter((item) => item.rule_id !== row.rule_id);
    ElMessage.success("仓储规则已删除");
  } catch (error) {
    if (error !== "cancel") ElMessage.error(error.message || "删除仓储规则失败");
  }
};
const loadPurchaseOrders = async () => {
  try {
    purchaseOrders.value = await productCenterApi.listPurchaseOrders({
      page_size: 100,
    });
  } catch {
    purchaseOrders.value = [];
  }
};
const loadBatches = async () => {
  loadingBills.value = true;
  try {
    logisticsBatches.value = await productCenterApi.listLogisticsBatches({
      status: billStatus.value || undefined,
    });
  } catch {
    logisticsBatches.value = [];
  } finally {
    loadingBills.value = false;
  }
};
const loadOperatingDimensions = async () => {
  try {
    Object.assign(
      operatingDimensions,
      await productCenterApi.listSkuOperatingDimensions(),
    );
  } catch {
    operatingDimensions.platforms = [];
    operatingDimensions.spus = [];
    operatingDimensions.skus = [];
    operatingDimensions.warehouses = [];
  }
};
// 仓库统一错误信封：{"success": false, "error": {"code": ..., "detail": {...}}, "message": ...}
// 顶层没有 detail 键；axios 响应拦截器（frontend/src/api/index.js）已把
// responseData.error.detail 挂到 error.detail 上。
const readApiErrorDetail = (error) => {
  const raw =
    error?.detail ??
    error?.response?.data?.error?.detail ??
    error?.response?.data?.detail;
  return raw && typeof raw === "object" ? raw : null;
};
const openPlatformFeeDrawer = async (tab = "platform") => {
  pricingDrawer.tab = tab;
  if (tab === "tiers") {
    await loadPricingPolicies();
    pricingDrawer.visible = true;
    return;
  }
  const platform = operatingDimensions.platforms.find(
    (item) => item.platform_code === operatingQuery.platform_code,
  );
  if (!platform) {
    ElMessage.warning("请先选择销售平台");
    return;
  }
  pricingDrawer.label = platform.name || platform.platform_code;
  pricingDrawer.form = {
    default_fee_rate_pct: toPercent(platform.default_fee_rate),
    default_creator_commission_rate_pct: toPercent(platform.default_creator_commission_rate),
    other_cost_rate_pct: toPercent(platform.other_cost_rate),
    fee_rate_effective_from: platform.fee_rate_effective_from || new Date().toISOString().slice(0, 10),
    fee_rate_source: platform.fee_rate_source || "manual",
    fee_rate_version: platform.fee_rate_version || "v1",
  };
  pricingDrawer.visible = true;
};
const loadPricingPolicies = async () => {
  try {
    const rows = await productCenterApi.listCurrentSkuPricingPolicies();
    pricingDrawer.policies = (rows || []).map((row) => ({
      ...row,
      discount_rate_pct: toPercent(row.discount_rate),
      target_margin_rate_pct: toPercent(row.target_margin_rate),
    }));
  } catch (error) {
    pricingDrawer.policies = [];
    ElMessage.error(readApiErrorDetail(error)?.reason || error?.message || "加载库龄档位规则失败");
  }
};
const savePricingPolicies = async () => {
  saving.value = true;
  try {
    for (const row of pricingDrawer.policies) {
      await productCenterApi.updateSkuPricingPolicy(row.min_restock_days, {
        min_restock_days: row.min_restock_days,
        tier_label: row.tier_label,
        discount_rate: fromPercent(row.discount_rate_pct, null),
        target_margin_rate: fromPercent(row.target_margin_rate_pct, null),
        platform_basis: row.platform_basis,
        effective_from: row.effective_from,
      });
    }
    await loadPricingPolicies();
    await loadSkus();
    ElMessage.success("库龄档位规则已保存");
  } catch (error) {
    const detail = readApiErrorDetail(error);
    ElMessage.error(detail?.reason || error?.message || "保存库龄档位规则失败");
  } finally {
    saving.value = false;
  }
};
const savePlatformFeeRate = async () => {
  const platformCode = operatingQuery.platform_code;
  if (!platformCode) return;
  saving.value = true;
  try {
    const {
      default_fee_rate_pct,
      default_creator_commission_rate_pct,
      other_cost_rate_pct,
      ...feePayload
    } = pricingDrawer.form;
    await productCenterApi.updatePlatformFeeRate(platformCode, {
      ...feePayload,
      default_fee_rate: fromPercent(default_fee_rate_pct, null),
      default_creator_commission_rate: fromPercent(default_creator_commission_rate_pct, null),
      other_cost_rate: fromPercent(other_cost_rate_pct, null),
    });
    pricingDrawer.visible = false;
    await loadOperatingDimensions();
    await loadOperatingProfiles();
    await loadSkus();
    ElMessage.success("平台成本率已保存");
  } catch (error) {
    const detail = readApiErrorDetail(error);
    ElMessage.error(detail?.reason || error?.message || "保存平台成本率失败");
  } finally {
    saving.value = false;
  }
};
const loadOperatingProfiles = async () => {
  if (!operatingQuery.platform_code || !operatingQuery.warehouse_code || !operatingQuery.transport_type) {
    operatingProfiles.value = [];
    operatingTotal.value = 0;
    return;
  }
  loadingOperating.value = true;
  try {
    const response = await productCenterApi.listPlatformSkuProfitCandidates({
      platform_code: operatingQuery.platform_code,
      warehouse_code: operatingQuery.warehouse_code,
      transport_type: operatingQuery.transport_type,
      spu: operatingQuery.spu || undefined,
      sku_id: operatingQuery.sku_id || undefined,
      // 阶段 7：「仅有库存」是**后端**筛选 —— 前端筛只筛当前页，
      // 总数会对不上、翻页还会漏行。
      only_in_stock: operatingQuery.only_in_stock,
      page: operatingQuery.page,
      page_size: operatingQuery.page_size,
    });
    operatingProfiles.value = (response.data || []).map((row) => ({
      ...row,
      expected_selling_price: row.expected_selling_price ?? row.reference_selling_price,
      seller_coupon_amount: row.seller_coupon_amount ?? 0,
      expected_ad_rate_pct: toPercent(row.expected_ad_rate ?? 0),
      // 目标 ROI 预填：它是运营的**当前意图**，存在经营档案里 ⇒ 上一轮填的值继续带着。
      // ⚠️ 平台报告 ROI **不预填**：它是"某一次投放"的历史事实，预填了再存进新一版
      //    利润版本，就会把上一轮的事实悄悄带过去 —— 事后没人说得清这一版是哪一轮的。
      target_roi: row.target_roi ?? null,
      actual_roi: null,
      // 这一行是不是在用「广告分成率」口径（阶段 3 的高级逃生口）
      adRateEscapeUsed: false,
    }));
    operatingTotal.value = response.total ?? 0;
  } catch (error) {
    operatingProfiles.value = [];
    operatingTotal.value = 0;
    ElMessage.error(error.message || "加载平台 SKU 利润失败");
  } finally {
    loadingOperating.value = false;
  }
};
// --- 阶段 6 · 仓维度展示辅助 -----------------------------------------------
// 当前选中的仓自己有多少天库龄。**这个数就是底线用的那个数** ——
// 页面显示的库龄和底线依据的库龄必须是同一个，否则运营会看到两个打架的数字。
// 取不到时回落到 pricing_days_since_restock（页面不传仓时它是 SKU 级跨仓 MAX）。
const currentWarehouseRestock = (row) => {
  const items = row.warehouse_restocks || [];
  return (
    items.find((item) => item.warehouse_code === operatingQuery.warehouse_code) || null
  );
};
const currentWarehouseRestockDays = (row) => {
  const current = currentWarehouseRestock(row);
  if (current) return current.days_since_restock ?? null;
  return row.pricing_days_since_restock ?? null;
};
const currentWarehouseLabel = (row) => {
  const current = currentWarehouseRestock(row);
  if (current) return current.warehouse_name || current.warehouse_code || "";
  const known = (operatingDimensions.warehouses || []).find(
    (item) => item.warehouse_code === operatingQuery.warehouse_code,
  );
  return (
    known?.warehouse_name || known?.warehouse_code || operatingQuery.warehouse_code || "当前仓"
  );
};
// 其它仓的库龄：**老的排前面** —— 先看到最该处理的。
const otherWarehouseRestocks = (row) => {
  const items = row.warehouse_restocks || [];
  return items
    .filter((item) => item.warehouse_code !== operatingQuery.warehouse_code)
    .slice()
    .sort(
      (a, b) => (b.days_since_restock ?? -1) - (a.days_since_restock ?? -1),
    );
};
// --- 阶段 7 · 当前仓库存展示 -----------------------------------------------
// 「这个仓现在还剩多少货」和「这批货压了多久」是两件事：
//   在卖（in_stock） → 显示数量
//   已清仓（cleared）→ 显式标出来：这是**事实**（这个仓清过这货），不是缺数据
//   无记录（no_record）→ 这个仓压根没有它的货
//   取不到（unavailable）→ 状态层不可用，显示 "-"（不能当成"没有货"）
const currentWarehouseStockLabel = (row) => {
  const status = row.current_warehouse_stock_status;
  if (status === "in_stock") return String(row.current_warehouse_available_stock ?? 0);
  if (status === "cleared") return "已清仓";
  if (status === "no_record") return "无记录";
  if (status === "unavailable") return "-";
  return "-";
};
const resetOperatingPage = () => {
  operatingQuery.page = 1;
  loadOperatingProfiles();
};
const operatingPayload = (row) => ({
  sku_id: row.sku_id,
  platform_code: operatingQuery.platform_code,
  warehouse_code: operatingQuery.warehouse_code,
  transport_type: operatingQuery.transport_type,
  competitor_price: row.competitor_price ?? null,
  expected_selling_price: row.expected_selling_price ?? null,
  seller_coupon_amount: row.seller_coupon_amount ?? 0,
  expected_ad_rate: fromPercent(row.expected_ad_rate_pct, 0),
  // --- ROI 投放输入（阶段 2.2）---
  // 目标 ROI：运营打算投到多少。留空 = 不参与保本 ROI 护栏。
  target_roi: row.target_roi ?? null,
  // 平台报告 ROI：运营从平台后台抄回来的这次投放实际 ROI。
  // 它是**事实记录**，低于保本线也照样存（后端只标红不拦）。
  actual_roi: row.actual_roi ?? null,
});
const clearOperatingSkuOutsideSpu = () => {
  if (operatingQuery.sku_id && !filteredOperatingSkus.value.some((item) => item.sku_id === operatingQuery.sku_id)) {
    operatingQuery.sku_id = "";
  }
};
const handleOperatingSpuChange = () => {
  clearOperatingSkuOutsideSpu();
  resetOperatingPage();
};
// 测算售价 / 优惠券 / 广告分成率一改，下面的利润就该跟着变。
// el-input-number 的 change 事件要等失焦或回车才触发，
// 运营在格子里打完价直接看下一行的利润，就会看到**上一次的旧利润**。
// 用 input 事件 + 每行 400ms 防抖：边打边更新，又不会每个键都打一次接口。
const operatingPreviewTimers = new Map();
const scheduleOperatingPreview = (row) => {
  const key = row.sku_id;
  const existing = operatingPreviewTimers.get(key);
  if (existing) clearTimeout(existing);
  operatingPreviewTimers.set(
    key,
    setTimeout(() => {
      operatingPreviewTimers.delete(key);
      previewOperatingRow(row);
    }, 400),
  );
};
const previewOperatingRow = async (row) => {
  try {
    const result = await productCenterApi.previewPlatformSkuProfit(operatingPayload(row));
    row.preview = result;
    row.reference_label_fee = result.reference_label_fee ?? null;
  } catch (error) {
    ElMessage.error(error.message || "利润试算失败");
  }
};
const saveOperatingDraft = async (row) => {
  saving.value = true;
  try {
    await productCenterApi.savePlatformSkuProfitDraft(operatingPayload(row));
    ElMessage.success("测算草稿已保存");
  } catch (error) {
    ElMessage.error(error.message || "保存测算草稿失败");
  } finally {
    saving.value = false;
  }
};
const isBelowFloor = (row) =>
  row.min_selling_price != null &&
  row.expected_selling_price != null &&
  Number(row.expected_selling_price) < Number(row.min_selling_price);
const saveOperatingEstimate = async (row) => {
  saving.value = true;
  try {
    await productCenterApi.savePlatformSkuProfitEstimates(operatingPayload(row));
    await previewOperatingRow(row);
    ElMessage.success("利润版本已保存");
  } catch (error) {
    // ⚠️ 读 error.detail（axios 拦截器挂载点），**不是** error.response.data.detail
    // ——仓库错误信封没有顶层 detail 键，那个表达式恒为 undefined。
    const detail = readApiErrorDetail(error);
    if (detail?.code === "below_min_selling_price") {
      ElMessage.error(
        `测算售价低于最低售价 ${money(detail.min_selling_price)}（当前 ${money(detail.expected_selling_price)}）`,
      );
      return;
    }
    // --- ROI 投放护栏（阶段 2.2）---
    // ⚠️ 护栏错误排在「资料未完整」**之前** ⇒ 运营看到的第一个原因是 ROI，
    //    不是"去补物流规则"（补完可能还是亏）。
    if (detail?.code === "below_break_even_roi") {
      // basis=lower_bound 表示成本不全、只能给出保本线的**下界**：
      // 下界只可能偏松，所以"低于下界"是**已经能确定**亏，不是估计。
      const threshold =
        detail.basis === "lower_bound"
          ? `至少 ${roiDisplay(detail.break_even_roi)}`
          : roiDisplay(detail.break_even_roi);
      ElMessage.error(
        `目标 ROI ${roiDisplay(detail.target_roi)} 低于保本线（${threshold}），这一单投了就是亏`,
      );
      return;
    }
    if (detail?.code === "roi_cost_incomplete") {
      ElMessage.error(
        `成本资料未完整，保本 ROI 不可信，不能据此设定目标 ROI${
          detail.missing_fields?.length ? `：${detail.missing_fields.join("、")}` : ""
        }`,
      );
      return;
    }
    const missing = detail?.missing_fields;
    ElMessage.error(
      missing?.length
        ? `资料未完整，不能保存利润版本：${missing.join("、")}`
        : (error?.message || "保存利润版本失败"),
    );
  } finally {
    saving.value = false;
  }
};
const payloadSpu = (row) => {
  const { __new, ...payload } = row;
  payload.category_l1 = payload.category_l1_code;
  payload.category_l2 = payload.category_l2_code;
  delete payload.category_l1_code;
  delete payload.category_l2_code;
  return payload;
};
const payloadSku = (row) => {
  const { __new, ...payload } = row;
  // 剔除**只读计算字段**（服务端算出来的，提交回去没有意义）：
  // current_discount_rate / clearance_max_discount_rate / min_selling_price /
  // min_selling_price_source / min_selling_price_is_override /
  // min_selling_price_missing_reasons / pricing_tier_label / pricing_days_since_restock /
  // pricing_tier_source / creator_commission_rate_fallback
  // ⚠️ creator_commission_rate_fallback 也要剔除：它只是平台兜底值的展示，
  // 不是 SKU 自己设的值，回提交上去会被当成「单独设置过」。
  delete payload.current_discount_rate;
  delete payload.clearance_max_discount_rate;
  delete payload.min_selling_price;
  delete payload.min_selling_price_source;
  delete payload.min_selling_price_is_override;
  delete payload.min_selling_price_missing_reasons;
  delete payload.pricing_tier_label;
  delete payload.pricing_days_since_restock;
  delete payload.pricing_tier_source;
  delete payload.creator_commission_rate_fallback;
  // ⚠️ min_selling_price_override 也必须剔除（阶段 2.1b）：
  // 人工覆盖是 **SKU × 平台** 的量，已经从 SKU 主数据里拆出去，
  // 改走独立接口 PATCH /api/skus/{sku_id}/pricing-override。
  // 后端已从 SkuCreateRequest / SkuUpdateRequest / SkuBulkItem 移除该字段，
  // 留在载荷里会被判 422 或被静默丢弃。
  delete payload.min_selling_price_override;
  // ⚠️ min_selling_price_by_platform 是后端下发的**只读**分平台数据，也不能回提交。
  delete payload.min_selling_price_by_platform;
  // ⚠️ 阶段 4 的这几个基准售价字段同样是**服务端算出来**的：
  //   selling_price_age_days / selling_price_stale 是账龄与过期判定，
  //   selling_price_source_cleaned_at 是枚举清洗时间戳，
  //   selling_price_confirmed_at 由服务端在保存时自动写入。
  // 回提交等于把服务端刚算出来的状态当成「运营填的」再写回去，
  // 过期状态会被钉死在库里 ⇒ 必须剔除。
  delete payload.selling_price_age_days;
  delete payload.selling_price_stale;
  delete payload.selling_price_source_cleaned_at;
  delete payload.selling_price_confirmed_at;
  // creator_commission_rate 必须**保留**：它是可写字段（单独谈的达人佣金率）。
  // 清空要显式传 null，不是删掉这个键。
  payload.purchase_cost_currency = "CNY";
  payload.selling_price_currency = "CNY";
  return payload;
};
const validateSpu = (row) =>
  !/^[A-Z0-9-]+$/.test(row.spu || "")
    ? "SPU 只能使用大写英文、数字和短横线"
    : !row.spu_name
      ? "商品名称不能为空"
      : !row.category_l2_code
        ? "请选择二级品类"
        : "";
const saveSpuRows = async () => {
  saving.value = true;
  try {
    for (const row of spuDirty.value) {
      const message = validateSpu(row);
      if (message) throw new Error(message);
    }
    await productCenterApi.bulkSaveSpus({
      items: spuDirty.value.map(payloadSpu),
    });
    await loadSpus();
    dirtyRows.value.clear();
    ElMessage.success("SPU 变更已保存");
  } catch (error) {
    ElMessage.error(error.message || "保存 SPU 失败");
  } finally {
    saving.value = false;
  }
};
const saveSkuRows = async () => {
  saving.value = true;
  try {
    for (const row of skuDirty.value) {
      if (!row.sku_key || !row.spu) throw new Error("SKU 和所属 SPU 不能为空");
    }
    await productCenterApi.bulkSaveSkus({
      items: skuDirty.value.map(payloadSku),
    });
    await loadSkus();
    dirtyRows.value.clear();
    ElMessage.success("SKU 变更已保存");
  } catch (error) {
    ElMessage.error(error.message || "保存 SKU 失败");
  } finally {
    saving.value = false;
  }
};
const _buildProviderRulePatch = (row) => {
  // Only forward fields the user actually changed (or that are required for creates).
  // Sending empty strings / nulls back triggers Pydantic 422 on pattern / date fields.
  const { __new, __original, rule_id, ...payload } = row;
  if (__new) {
    return Object.fromEntries(
      Object.entries(payload).filter(([, value]) => value !== "" && value !== null),
    );
  }
  const diff = {};
  for (const field of _PROVIDER_RULE_PATCH_FIELDS) {
    if (payload[field] !== __original?.[field]) diff[field] = payload[field];
  }
  // Empty strings in unchanged optional fields would still 422, so drop them.
  for (const [key, value] of Object.entries(diff)) {
    if (value === "") delete diff[key];
  }
  return diff;
};
const saveRuleRows = async () => {
  try {
    for (const row of ruleDirty.value) {
      const payload = _buildProviderRulePatch(row);
      if (Object.keys(payload).length === 0) continue;
      if (row.__new) await productCenterApi.createProviderRule(payload);
      else await productCenterApi.updateProviderRule(row.rule_id, payload);
    }
    await loadRules();
    dirtyRuleRows.value.clear();
    ElMessage.success("物流规则已保存");
  } catch (error) {
    ElMessage.error(error.message || "保存物流规则失败");
  }
};
const removeProviderRule = async (row) => {
  try {
    await ElMessageBox.confirm(
      "删除后该规则不再用于新的物流账单测算。已落账的物流批次不受影响。",
      "删除物流服务商规则",
      { type: "warning" },
    );
    await productCenterApi.deleteProviderRule(row.rule_id);
    rules.value = rules.value.filter((item) => item.rule_id !== row.rule_id);
    dirtyRuleRows.value.delete(row.rule_id);
    ElMessage.success("物流规则已删除");
  } catch (error) {
    if (error !== "cancel") ElMessage.error(error.message || "删除物流规则失败");
  }
};
const showBindings = async (row) => {
  bindingDrawer.visible = true;
  bindingDrawer.spu = row.spu;
  try {
    bindingDrawer.rows = await productCenterApi.listSpuSkus(row.spu);
  } catch (error) {
    ElMessage.error(error.message || "加载绑定历史失败");
  }
};
const onSpuSelectionChange = (rows) => {
  selectedSpus.value = rows.filter((r) => !r.__new && r.active !== false);
};
const handleDeleteSku = async (row) => {
  if (row.__new || row.status === "inactive") return;
  let preview;
  try {
    preview = await productCenterApi.previewSkuDeletion(row.sku_id);
  } catch (error) {
    ElMessage.error(error.message || "停用预检失败");
    return;
  }
  const failChecks = (preview.checks || []).filter((c) => c.status === "fail");
  const warnChecks = (preview.checks || []).filter((c) => c.status === "warn");
  if (failChecks.length) {
    const failMsg = failChecks.map((c) => `• ${c.label}${c.detail ? `: ${c.detail}` : ""}`).join("\n");
    await ElMessageBox.alert(
      `以下前置条件未通过，暂不可停用：\n${failMsg}`,
      `SKU ${row.sku_key} 停用预检失败`,
      { type: "error", confirmButtonText: "我知道了" },
    );
    return;
  }
  const warnText = warnChecks.length
    ? `\n\n提示（不阻断）：\n${warnChecks.map((c) => `• ${c.label}${c.detail ? `: ${c.detail}` : ""}`).join("\n")}`
    : "";
  const summary = `SKU: ${row.sku_key} (${row.sku_name || ""})\n当前状态: ${preview.current_status}\n\n影响：\n• dim_erp_sku.status → inactive\n• bridge_spu_sku 失效 ${preview.soft_delete_impact?.bridge_spu_sku_inactive ?? 0} 条\n• fact_audit_log 新增 1 条\n• 业务表引用 ${preview.business_reference_count} 条（停用不影响业务数据）${warnText}`;
  try {
    await ElMessageBox.confirm(
      `${summary}\n\n确认停用吗？`,
      `确认停用 SKU ${row.sku_key}`,
      { type: "warning", confirmButtonText: "确认停用", cancelButtonText: "取消" },
    );
  } catch (e) {
    return;
  }
  try {
    const resp = await productCenterApi.softDeleteSku(row.sku_id, { confirm: true });
    ElMessage.success(
      `SKU ${resp.sku_key} 已停用 (${resp.previous_status} → ${resp.new_status}, 影响 binding=${resp.affected_bindings})`,
    );
    await loadSkus();
  } catch (error) {
    ElMessage.error(error.message || "停用失败");
  }
};
const handleRestoreSku = async (row) => {
  if (row.status !== "inactive") return;
  const summary = `SKU: ${row.sku_key} (${row.sku_name || ""})\n当前状态: ${row.status}\n\n影响：\n• dim_erp_sku.status → active\n• bridge_spu_sku 复活最早的 inactive binding（如有）\n• fact_audit_log 新增 1 条`;
  try {
    await ElMessageBox.confirm(
      `${summary}\n\n确认恢复吗？`,
      `确认恢复 SKU ${row.sku_key}`,
      { type: "warning", confirmButtonText: "确认恢复", cancelButtonText: "取消" },
    );
  } catch (e) {
    return;
  }
  try {
    const resp = await productCenterApi.restoreSku(row.sku_id, { confirm: true });
    ElMessage.success(
      `SKU ${resp.sku_key} 已恢复 (${resp.previous_status} → ${resp.new_status}, 复活 binding=${resp.restored_bindings})`,
    );
    await loadSkus();
  } catch (error) {
    ElMessage.error(error.message || "恢复失败");
  }
};
const handleRestoreSpu = async (row) => {
  if (row.active !== false) return;
  const summary = `SPU: ${row.spu} (${row.spu_name || ""})\n当前状态: 已软删 (active=false)\n\n影响：\n• dim_spu.active → true\n• dim_spu.biz_status: ${row.biz_status || "retired"} → promoted\n• bridge_spu_sku 复活最早的 inactive binding（如有）\n• fact_audit_log 新增 1 条`;
  try {
    await ElMessageBox.confirm(
      `${summary}\n\n确认恢复吗？`,
      `确认恢复 SPU ${row.spu}`,
      { type: "warning", confirmButtonText: "确认恢复", cancelButtonText: "取消" },
    );
  } catch (e) {
    return;
  }
  try {
    const resp = await productCenterApi.restoreSpu(row.spu, { confirm: true });
    ElMessage.success(
      `SPU ${resp.spu} 已恢复 (${resp.previous_biz_status} → ${resp.new_biz_status}, 复活 binding=${resp.restored_bindings})`,
    );
    await loadSpus();
  } catch (error) {
    ElMessage.error(error.message || "恢复失败");
  }
};
const handleDeleteSpu = async (row) => {
  if (row.__new || row.active === false) return;
  let preview;
  try {
    preview = await productCenterApi.previewSpuDeletion(row.spu);
  } catch (error) {
    ElMessage.error(error.message || "删除预检失败");
    return;
  }
  const failChecks = (preview.checks || []).filter((c) => c.status === "fail");
  const warnChecks = (preview.checks || []).filter((c) => c.status === "warn");
  if (failChecks.length) {
    const failMsg = failChecks.map((c) => `• ${c.label}${c.detail ? `: ${c.detail}` : ""}`).join("\n");
    const warnMsg = warnChecks.map((c) => `• ${c.label}${c.detail ? `: ${c.detail}` : ""}`).join("\n");
    await ElMessageBox.alert(
      `以下前置条件未通过，暂不可删除：\n${failMsg}\n${warnMsg ? `\n提示（不阻断）：\n${warnMsg}\n` : ""}\n请先在 SKU 归属页停用关联 SKU。`,
      `SPU ${row.spu} 删除预检失败`,
      { type: "error", confirmButtonText: "我知道了" },
    );
    return;
  }
  const warnText = warnChecks.length
    ? `\n\n提示（不阻断）：\n${warnChecks.map((c) => `• ${c.label}`).join("\n")}`
    : "";
  const summary = `SPU: ${row.spu} (${row.spu_name || ""})\n影响：\n• dim_spu 记录将置为 inactive + biz_status=retired\n• bridge_spu_sku 失效 ${preview.soft_delete_impact?.bridge_spu_sku_inactive ?? 0} 条\n• fact_audit_log 新增 1 条${warnText}`;
  try {
    await ElMessageBox.confirm(
      `${summary}\n\n确认软删除吗？`,
      `确认软删除 SPU ${row.spu}`,
      { type: "warning", confirmButtonText: "确认软删除", cancelButtonText: "取消" },
    );
  } catch (e) {
    return;
  }
  try {
    const resp = await productCenterApi.softDeleteSpu(row.spu, { confirm: true });
    ElMessage.success(`SPU ${resp.spu} 已软删除 (audit=${resp.audit_recorded})`);
    await loadSpus();
  } catch (error) {
    ElMessage.error(error.message || "软删除失败");
  }
};
const handleBatchDeleteSpu = async () => {
  const targets = selectedSpus.value.filter((r) => !r.__new && r.active !== false);
  if (!targets.length) return;
  // 阶段 1:对每个 SPU 调 preview
  const previews = await Promise.all(
    targets.map(async (row) => {
      try {
        const pv = await productCenterApi.previewSpuDeletion(row.spu);
        return { spu: row.spu, spu_name: row.spu_name, preview: pv, error: null };
      } catch (e) {
        return { spu: row.spu, spu_name: row.spu_name, preview: null, error: e.message || "预检失败" };
      }
    }),
  );
  const blockedEntries = previews.filter(
    (p) => p.error || (p.preview && !p.preview.can_soft_delete),
  );
  if (blockedEntries.length) {
    const list = blockedEntries
      .map((b) => {
        const reasons = b.error
          ? [b.error]
          : (b.preview.blocked_reasons || []);
        return `• ${b.spu}: ${reasons.join("; ") || "不通过"}`;
      })
      .join("\n");
    await ElMessageBox.alert(
      `以下 SPU 未通过预检，批量操作已取消（任一 fail 整体回滚）：\n${list}\n\n请先到 SKU 归属页停用关联 SKU 后再试。`,
      `批量软删预检失败（${blockedEntries.length}/${targets.length} 不通过）`,
      { type: "error", confirmButtonText: "我知道了" },
    );
    return;
  }
  // 阶段 2:弹窗输入 reason
  const warnBlock = previews
    .filter((p) => p.preview.checks.some((c) => c.status === "warn"))
    .map((p) => `• ${p.spu}: ${p.preview.checks.filter((c) => c.status === "warn").map((c) => c.label).join(", ")}`)
    .join("\n");
  const totalBindings = previews.reduce(
    (sum, p) => sum + (p.preview.soft_delete_impact?.bridge_spu_sku_inactive || 0),
    0,
  );
  const summary = `即将软删除 ${targets.length} 个 SPU：\n${targets.map((r) => `• ${r.spu} (${r.spu_name || ""})`).join("\n")}\n\n汇总影响：\n• dim_spu: ${targets.length} 条将置为 retired\n• bridge_spu_sku 失效 ${totalBindings} 条\n• fact_audit_log 新增 ${targets.length} 条${warnBlock ? `\n\n提示（不阻断）：\n${warnBlock}` : ""}`;
  try {
    await ElMessageBox.confirm(
      `${summary}\n\n确认批量软删除吗？`,
      `确认批量软删除 ${targets.length} 个 SPU`,
      { type: "warning", confirmButtonText: "确认批量删除", cancelButtonText: "取消" },
    );
  } catch (e) {
    return;
  }
  // 阶段 3:执行批量
  try {
    const resp = await productCenterApi.batchSoftDeleteSpus({
      spus: targets.map((r) => r.spu),
      confirm: true,
    });
    if (resp.rolled_back) {
      const blockedNames = resp.items
        .filter((it) => it.status === "blocked")
        .map((it) => `• ${it.spu}: ${it.blocked_reasons.join("; ")}`)
        .join("\n");
      ElMessageBox.alert(
        `整体回滚，无任何修改：\n${blockedNames}`,
        "批量软删已回滚",
        { type: "error", confirmButtonText: "我知道了" },
      );
      return;
    }
    ElMessage.success(
      `批量软删完成:成功 ${resp.deleted}/${resp.total},audit 已写入`,
    );
    selectedSpus.value = [];
    await loadSpus();
  } catch (error) {
    ElMessage.error(error.message || "批量软删失败");
  }
};
const openBatchCreate = () => {
  Object.assign(batchDrawer, {
    visible: true,
    editing: false,
    billId: null,
    lines: [],
  });
  Object.assign(batchDrawer.form, {
    bill_no: "",
    logistics_provider: "",
    bill_date: "",
    warehouse_code: "",
    transport_type: "sea",
    total_amount: 0,
    currency: "CNY",
  });
  selectedPurchaseOrders.value = [];
  unmappedPurchaseSkus.value = [];
  missingVolumeSkus.value = [];
};
const editBatch = async (row) => {
  try {
    const detail = await productCenterApi.getLogisticsBatch(
      row.bill_id || row.batch_id,
    );
    Object.assign(batchDrawer, {
      visible: true,
      editing: true,
      billId: detail.bill_id || detail.batch_id,
      form: { ...detail },
      lines: detail.lines || [],
    });
    selectedPurchaseOrders.value = detail.purchase_orders || [];
    unmappedPurchaseSkus.value = [];
    missingVolumeSkus.value = [];
  } catch (error) {
    ElMessage.error(error.message || "加载物流批次失败");
  }
};
const lineTotal = (row) => {
  const base =
    row.billing_basis === "weight"
      ? (row.actual_total_weight_kg || 0) * (row.billing_unit_rate || 0)
      : row.billing_basis === "quantity"
        ? (row.shipped_qty || 0) * (row.billing_unit_rate || 0)
        : row.billing_basis === "fixed"
          ? row.billing_unit_rate || 0
          : (row.actual_total_volume_cbm || 0) * (row.billing_unit_rate || 0);
  return (
    base +
    (row.headhaul_cost || 0) +
    (row.handling_cost || 0) +
    (row.last_mile_cost || 0) +
    (row.sensitive_surcharge || 0)
  );
};
const lineTotalSum = computed(() =>
  batchDrawer.lines.reduce((sum, row) => sum + lineTotal(row), 0),
);
const batchBalanced = computed(
  () =>
    Math.abs(Number(batchDrawer.form.total_amount || 0) - lineTotalSum.value) <
    0.01,
);
const saveBatch = async () => {
  try {
    if (unmappedPurchaseSkus.value.length) {
      throw new Error("请先完成待映射采购单 SKU 的 ERP SKU 映射");
    }
    let id = batchDrawer.billId;
    if (!batchDrawer.editing) {
      const created = await productCenterApi.createLogisticsBatch(
        batchDrawer.form,
      );
      id = created.bill_id || created.batch_id;
      batchDrawer.billId = id;
      batchDrawer.editing = true;
    }
    await productCenterApi.saveLogisticsBatchLines(id, {
      purchase_order_ids: selectedPurchaseOrders.value.map((item) =>
        typeof item === "string" ? item : item.po_id,
      ),
      lines: batchDrawer.lines.map(({ rate_source, rule_id, ...line }) => line),
    });
    batchDrawer.visible = false;
    await loadBatches();
    ElMessage.success("物流批次草稿已保存");
  } catch (error) {
    ElMessage.error(error.message || "保存物流批次失败");
  }
};
const confirmBatch = async (row) => {
  try {
    await ElMessageBox.confirm(
      "确认后账单行不可编辑，只能作废重建。",
      "确认物流批次",
      { type: "warning" },
    );
    await productCenterApi.confirmLogisticsBatch(row.bill_id || row.batch_id);
    await loadBatches();
    ElMessage.success("物流批次已确认");
  } catch (error) {
    if (error !== "cancel") ElMessage.error(error.message || "确认失败");
  }
};
const billingUnitFor = (basis) =>
  ({
    volume: "CNY/CBM",
    weight: "CNY/KG",
    quantity: "CNY/unit",
    fixed: "CNY",
  })[basis] || "CNY/CBM";
const matchProviderRule = (isSensitive, warehouseCode = batchDrawer.form.warehouse_code) => {
  const form = batchDrawer.form;
  if (!form.logistics_provider) return null;
  const cargoClass = isSensitive ? "sensitive" : "normal";
  const candidates = rules.value.filter(
    (rule) =>
      rule.logistics_provider === form.logistics_provider &&
      (rule.cargo_class === cargoClass ||
        Boolean(rule.is_sensitive) === isSensitive) &&
       (!rule.warehouse_code || rule.warehouse_code === warehouseCode) &&
      (!rule.transport_type || rule.transport_type === form.transport_type),
  );
  if (!candidates.length) return null;
  const score = (rule) =>
    Number(rule.warehouse_code === warehouseCode) * 2 +
    Number(rule.transport_type === form.transport_type);
  const highestScore = Math.max(...candidates.map(score));
  const bestRules = candidates.filter((rule) => score(rule) === highestScore);
  if (bestRules.length === 1) return bestRules[0];
  const defaultRules = bestRules.filter((rule) => rule.is_default);
  return defaultRules.length === 1 ? defaultRules[0] : null;
};
const applyRuleToLine = (line, { force = false } = {}) => {
  if (!force && line.rate_source === "manual") return;
  const rule = matchProviderRule(Boolean(line.is_sensitive), line.warehouse_code);
  if (!rule) return;
  line.rule_id = rule.rule_id;
  line.billing_basis = rule.billing_basis || "volume";
  line.billing_unit = rule.billing_unit || billingUnitFor(line.billing_basis);
  line.billing_unit_rate = rule.freight_unit_rate ?? null;
  line.rate_source = "rule";
};
const applyRuleToBatchLines = () => {
  batchDrawer.lines.forEach((line) => applyRuleToLine(line));
};
const generateBatchLinesFromPurchaseOrders = async (orders) => {
  const lines = [];
  const unmapped = [];
  const missingVolume = [];
  for (const order of orders) {
    const poLines = await productCenterApi.listPurchaseOrderLines(order.po_id);
    for (const poLine of poLines) {
      const sku =
        skus.value.find((item) => item.sku_id === poLine.sku_id) ||
        skus.value.find((item) => item.sku_key === poLine.platform_sku);
      if (sku) {
        const shippedQty = poLine.qty_received || poLine.qty_ordered || 0;
        const unitVolume = formatVolume(sku);
        // 单件体积没填 → 行体积为 0 → 按体积计费的金额偏低，但**不报错**。
        // 这是另一种静默失败：账单能保存、能确认，只是钱算少了。
        // 所以这里不丢行（丢了会卡住批次流程），而是记下来在抽屉里显式提示。
        if (!hasVolume(sku)) {
          missingVolume.push({
            id: sku.sku_id,
            label: `${sku.sku_key || sku.sku_id}（单件体积未填，金额会偏低）`,
          });
        }
        lines.push({
          po_id: order.po_id,
          warehouse_code: poLine.warehouse || order.warehouse || batchDrawer.form.warehouse_code,
          sku_id: sku.sku_id,
          sku_ids: [sku.sku_id],
          allocations: [
            {
              sku_id: sku.sku_id,
              po_id: order.po_id,
              shipped_qty: shippedQty,
            },
          ],
          shipped_qty: shippedQty,
          actual_total_volume_cbm: unitVolume * shippedQty,
          actual_total_weight_kg: Number(sku.weight_kg || 0) * shippedQty,
          billing_basis: "volume",
          billing_unit: "CNY/CBM",
          billing_unit_rate: null,
          rate_source: "rule",
          is_sensitive: false,
          sensitive_surcharge: 0,
          headhaul_cost: 0,
          handling_cost: 0,
          last_mile_cost: 0,
        });
      } else {
        unmapped.push(`${order.po_no || order.po_id} / ${poLine.platform_sku}`);
      }
    }
  }
  batchDrawer.lines = lines;
  unmappedPurchaseSkus.value = unmapped;
  missingVolumeSkus.value = missingVolume;
  applyRuleToBatchLines();
};
watch(selectedPurchaseOrders, (orders) => {
  if (!batchDrawer.editing && orders.length)
    generateBatchLinesFromPurchaseOrders(orders).catch((error) =>
      ElMessage.error(error.message || "生成采购单 SKU 行失败"),
    );
});
watch(
  () => [
    batchDrawer.form.logistics_provider,
     batchDrawer.form.warehouse_code,
    batchDrawer.form.transport_type,
  ],
  applyRuleToBatchLines,
);
const toPercent = (value) =>
  value == null ? null : Number((Number(value) * 100).toFixed(4));
const fromPercent = (value, fallback = 0) =>
  value == null || value === "" ? fallback : Number(value) / 100;
const money = (value) => (value == null ? "-" : `¥${Number(value).toFixed(2)}`);
const percent = (value) =>
  value == null ? "-" : `${(Number(value) * 100).toFixed(1)}%`;
// SKU 单件体积（m³）。物流/仓储账单按体积计费，行体积 = 单件体积 × 发货数量。
// ⚠️ 体积未填时返回 0 —— 账单金额会偏低但**不报错**，所以调用方必须能区分
// 「体积是 0」和「体积没填」，见 generateBatchLinesFromPurchaseOrders 的 missing_volume 归集。
const formatVolume = (sku) => {
  const value = Number(sku?.unit_volume_cbm);
  return Number.isFinite(value) && value > 0 ? value : 0;
};
const hasVolume = (sku) => formatVolume(sku) > 0;
const volumeMissing = (row) =>
  missingVolumeSkus.value.some((item) => item.id === row.sku_id);
// 缺资料原因 → 中文话术。ROI 守卫和参考成本列共用一份，别各写各的。
const MISSING_REASON_LABELS = {
  missing_sku_volume: "待补 SKU 体积",
  missing_sku_weight: "待补 SKU 重量",
  missing_turnover_class: "待设置周转类型",
  missing_logistics_rule: "待配置参考物流规则",
  missing_storage_rule: "待配置仓储规则",
  ambiguous_logistics_rule: "参考物流规则待指定默认",
};
const missingReasonLabel = (reason) => MISSING_REASON_LABELS[reason] || "待补资料";
const referenceCostDisplay = (row, kind) => {
  const value = kind === "logistics" ? referenceLogisticsCost(row) : referenceStorageCost(row);
  if (value != null) return money(value);
  const reason = (kind === "logistics"
    ? row.reference_logistics_missing_reasons
    : row.reference_storage_missing_reasons)?.[0];
  return missingReasonLabel(reason);
};
// ROI 展示：两位小数（运营填进平台后台的精度），算不出来显示 "-"
const roiDisplay = (value) => (value == null ? "-" : Number(value).toFixed(2));
// 成本完整度守卫（阶段 1 硬前提）：成本不全 → pre_ad_profit 高估 → 保本ROI 偏松
// → 看着宽松 → 运营真投广告 → 亏损。缺输入宁可不算不可乐观：三个 ROI 一律置灰。
const roiGuarded = (row) => row.reference_cost_status !== "ready";
// 缺失原因按三份清单分列（缺物流 / 缺仓储 / 缺体积），别混成一坨看不清缺什么
const roiGuardTooltip = (row) => {
  if (!roiGuarded(row)) {
    return "低于这个 ROI，广告就是亏的（财务口径）。分母为商家实收，与平台 GMV 同一把标尺";
  }
  const lines = ["成本不全，保本ROI 偏乐观"];
  const logistics = (row.reference_logistics_missing_reasons || []).map(missingReasonLabel);
  const storage = (row.reference_storage_missing_reasons || []).map(missingReasonLabel);
  const volume = (row.reference_cost_missing_reasons || [])
    .filter((reason) => reason === "missing_sku_volume" || reason === "missing_sku_weight")
    .map(missingReasonLabel);
  if (logistics.length) lines.push(`缺物流规则：${logistics.join("、")}`);
  if (storage.length) lines.push(`缺仓储规则：${storage.join("、")}`);
  if (volume.length) lines.push(`缺 SKU 体积/重量：${volume.join("、")}`);
  return lines.join("\n");
};
// 建议ROI 的 tooltip：把这个数「意味着什么」翻译给运营
const roiSuggestionTooltip = (row) => {
  const expected = row.preview?.expected;
  const lines = ["保本线上浮 20%（业界惯例 20–30%），超过平台可填上限时截断"];
  if (expected?.suggestion_note === "above_platform_ceiling") {
    lines.push(
      `未封顶原值 ${roiDisplay(expected.suggested_roi)}，超过平台可填上限 ${roiDisplay(row.target_roi_ceiling)}：广告空间不足，优先走自然流量/达人`,
    );
  } else if (expected?.suggested_roi != null) {
    lines.push(
      `按这个数投：单均广告费 ${money(expected.equivalent_ad_cost_per_order)}，单均净利 ${money(expected.equivalent_net_profit_per_order)}`,
    );
  }
  return lines.join("\n");
};
// --- ROI 投放判定（阶段 2.2）---
//
// 三色判定（上游设计稿 §2.5⑪）：
//   平台报告 ROI < 保本 ROI            → 亏损投放（红）
//   保本 ROI ≤ 平台报告 ROI < 建议 ROI  → 有利润但未达财务目标（黄）
//   平台报告 ROI ≥ 建议 ROI             → 达标（绿）
//   目标 ROI < 保本 ROI                  → 目标 ROI 低于保本线（红）
//
// ⚠️ 成本不全时**一律不判**：保本 ROI 算不出来 ⇒ 三色判定没有依据。
//    缺输入宁可不算，不可乐观 —— 宁可留白，也不要给一个看着能过的结论。
const roiVerdict = (row) => {
  const expected = row.preview?.expected;
  const actual = row.actual_roi;
  if (actual == null || expected == null) return null;
  const breakEven = expected.break_even_roi;
  if (breakEven == null) return null;
  // 用**表上显示的那个**建议 ROI（封顶后）做比较：运营看到什么就按什么判。
  // 封顶后仍达不到才叫"未达目标"；封顶前达不到是"广告空间不足"，那是另一条提示。
  const suggested = expected.suggested_roi_clamped ?? expected.suggested_roi;
  if (Number(actual) < Number(breakEven)) {
    return { type: "danger", label: "亏损投放", level: "red" };
  }
  if (suggested != null && Number(actual) >= Number(suggested)) {
    return { type: "success", label: "达标", level: "green" };
  }
  return { type: "warning", label: "有利润但未达财务目标", level: "yellow" };
};
const targetRoiBelowBreakEven = (row) => {
  const breakEven = row.preview?.expected?.break_even_roi;
  if (row.target_roi == null || breakEven == null) return false;
  return Number(row.target_roi) < Number(breakEven);
};
// --- 广告分成率（高级逃生口）与目标 ROI 的口径切换（阶段 3）---
//
// 两个口径说的是同一件事：广告费用占多少。
//   目标 ROI 口径（主输入）：广告费用 = 商家实收 ÷ 目标ROI（平台语言）
//   广告分成率口径（逃生口）：广告费用 = 广告前利润 × 分成率（老口径）
// 两者**数值等价**（目标ROI = 保本ROI ÷ 分成率 ⇒ 商家实收 ÷ 目标ROI = 广告前利润 × 分成率），
// 所以切换口径**不改变利润**。
//
// 为什么要清掉另一个：两个输入填着就"打架"（后端只能取一个）。
// 运营动了哪一个，就以那个为准 —— 另一个**可见地**清空，不搞"悄悄生效"。
const showAdRateEscape = ref(false);
// 运营改「广告分成率」⇒ 走老口径 ⇒ 清掉目标 ROI（后端就会用分成率算广告费）
const onAdRateEscapeInput = (row) => {
  row.target_roi = null;
  row.adRateEscapeUsed = true;
  scheduleOperatingPreview(row);
};
// 运营改「目标 ROI」⇒ 走平台口径 ⇒ 广告分成率不再参与计算（标记一下，提示语会跟着变）
const onTargetRoiInput = (row) => {
  row.adRateEscapeUsed = false;
  scheduleOperatingPreview(row);
};
// 目标 ROI 的 tooltip：把这个数「意味着什么」翻译给运营
const targetRoiTooltip = (row) => {
  const lines = ["运营打算投到的 ROI（商家实收 ÷ 广告费，与平台后台同一把标尺）"];
  const breakEven = row.preview?.expected?.break_even_roi;
  if (row.target_roi == null) {
    lines.push("留空 = 不参与保本 ROI 护栏");
    return lines.join("\n");
  }
  if (breakEven == null) {
    lines.push("成本不全，保本 ROI 算不出来 ⇒ 护栏按「成本不全」处理");
    return lines.join("\n");
  }
  if (targetRoiBelowBreakEven(row)) {
    lines.push(`低于保本线 ${roiDisplay(breakEven)}：这一单投了就是亏`);
  } else {
    lines.push(`保本线 ${roiDisplay(breakEven)}：不低于它，单均广告费才不超单均广告前利润`);
  }
  return lines.join("\n");
};
// 平台报告 ROI 的 tooltip：三色判定 + **归因警示**
//
// ⚠️ 归因警示是必须的（上游设计稿 §2.5⑧）：GMV Max 之类的归因窗口把自然流量和
//    达人带货也算进归因 GMV ⇒ 「达标」很可能只是归因虚高。
//    商品中心**目前拿不到归因放大系数**（没有平台广告数据源），
//    所以这里**只给警示文案、不给数字** —— 给不出数字时宁可不给，不能编。
const roiVerdictTooltip = (row) => {
  const verdict = roiVerdict(row);
  const expected = row.preview?.expected;
  const lines = [];
  if (row.actual_roi == null) {
    lines.push("运营从平台后台抄回来的这次投放实际 ROI");
    lines.push("留空 = 这次没有记录投放结果");
    return lines.join("\n");
  }
  if (!verdict) {
    lines.push("成本不全，保本 ROI 算不出来 ⇒ 不做判定（缺输入宁可不算）");
    return lines.join("\n");
  }
  lines.push(
    verdict.level === "red"
      ? `平台报告 ROI ${roiDisplay(row.actual_roi)} 低于保本线 ${roiDisplay(expected.break_even_roi)}：这次投放是亏的`
      : verdict.level === "green"
        ? `平台报告 ROI ${roiDisplay(row.actual_roi)} 已达到建议 ROI ${roiDisplay(expected.suggested_roi_clamped ?? expected.suggested_roi)}`
        : `平台报告 ROI ${roiDisplay(row.actual_roi)}：有利润，但没达到建议 ROI ${roiDisplay(expected.suggested_roi_clamped ?? expected.suggested_roi)}`,
  );
  if (verdict.level === "green") {
    lines.push("⚠ 达标归因可能虚高：平台归因窗口把自然流量和达人带货也算进归因 GMV");
    lines.push("商品中心目前拿不到归因放大系数（没有平台广告数据源），所以只提示、不给数字");
    lines.push("投多少不亏，以本表「保本ROI」为准");
  }
  return lines.join("\n");
};
// 优先用**试算里实际扣的金额**（preview.expected.label_fee），
// 退而用行上的贴单费——两者口径不一致时，以实际扣款为准，
// 否则会出现「列显示 -、利润却扣了钱」的错觉。
const referenceLabelFee = (row) =>
  row.preview?.expected?.label_fee ??
  row.reference_label_fee ??
  row.expected_label_fee ??
  null;
const referenceLabelFeeDisplay = (row) => {
  const value = referenceLabelFee(row);
  return value == null ? "-" : money(value);
};
onMounted(async () => {
  await Promise.all([
    loadSpus(),
    loadSkus(),
    loadCategories(),
    loadRules(),
    loadStorageRules(),
    loadPurchaseOrders(),
    loadBatches(),
    loadOperatingDimensions(),
    loadOperatingProfiles(),
    // 预热**可绑定**候选集：存量行的 SPU 单元格现在也是下拉框，
    // 运营一点开就该看到内容，而不是一个空列表（空列表看着像功能坏了）。
    spuAssignable.search(""),
  ]);
});
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 18px;
}
.page-subtitle {
  margin: 6px 0 0;
  color: var(--el-text-color-secondary);
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 14px;
  align-items: center;
}
.toolbar .el-input {
  max-width: 260px;
}
.toolbar .el-select {
  width: 170px;
}
.flat-table :deep(.el-input-number) {
  width: 100%;
}
.rate-cell {
  display: flex;
  align-items: center;
  gap: 4px;
}
.rate-cell :deep(.el-input-number) {
  flex: 1;
  width: auto;
  min-width: 0;
}
.rate-suffix {
  flex: none;
  color: var(--el-text-color-secondary);
}
/* --- 广告分成率（高级逃生口）：折叠态显示"当前生效口径"，旁边永远并排等效目标ROI --- */
.rate-locked {
  flex: 1;
  min-width: 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ad-rate-equivalent {
  margin-top: 2px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.ad-rate-escape-toggle {
  margin-left: 12px;
  color: var(--el-text-color-secondary);
}
.sku-table :deep(.el-table__cell) {
  padding: 6px 4px;
}
/* SPU 值域下拉：编码 + 名称一行展示。
   ⚠️ option 的 label 仍然只放编码（allow-create 要靠它判断「是否已存在」），
      名称只在这里渲染 —— 看得见，但不参与匹配判定。 */
.spu-option-code {
  margin-right: 8px;
  font-family: Consolas, Monaco, monospace;
}
.spu-option-name {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
/* 归属生效日：跟着 SPU 编码走的一行小字。
   ⚠️ 它回答的是「这个货是什么时候挂到这个款上的」——
      归属是**一段有时效的关联**，不是 SKU 身上的一个字段。 */
.spu-binding-since {
  display: block;
  color: var(--el-text-color-secondary);
  font-size: 11px;
  line-height: 14px;
}
/* SKU 行的 SPU 单元格：下拉框 + 生效日小字，竖着排。 */
.spu-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
}
.readonly-cell {
  display: inline-block;
  width: 100%;
  padding: 0 11px;
  line-height: 24px;
  color: var(--el-text-color-regular);
  background-color: var(--el-disabled-bg-color);
  border: 1px solid var(--el-disabled-border-color);
  border-radius: var(--el-border-radius-small);
  font-size: 12px;
  user-select: text;
}
/* --- SKU 定价底线 --- */
.pricing-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.pricing-cell-head {
  display: flex;
  align-items: center;
  gap: 6px;
}
/* 最低售价按平台分行：每个可定价平台一个小块 */
.pricing-platform-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-bottom: 4px;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
.pricing-platform-row:last-child {
  border-bottom: none;
  padding-bottom: 0;
}
.pricing-platform-name {
  flex: 0 0 auto;
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-regular);
  white-space: nowrap;
}
/* 底线数与来源标签跟在平台名后面，数字占剩余空间 */
.pricing-cell-head .readonly-cell {
  flex: 1 1 0;
  min-width: 0;
  width: auto;
}
.pricing-cell-head .el-tag {
  flex: 0 0 auto;
}
.pricing-override-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.pricing-override-row :deep(.el-input-number) {
  width: 120px;
}
.pricing-tier-hint {
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-secondary);
}
/* --- 阶段 4：基准售价即时影响预览 --- */
.selling-price-preview {
  margin-top: 4px;
  padding: 6px 8px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-regular);
  background-color: var(--el-fill-color-lighter);
  border-radius: 4px;
}
.selling-price-preview-title {
  font-weight: 600;
  color: var(--el-text-color-secondary);
}
.selling-price-preview-line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}
.selling-price-preview-platform {
  font-weight: 600;
}
.selling-price-preview-warning {
  color: var(--el-color-danger);
}
.selling-price-preview-hint {
  color: var(--el-text-color-secondary);
}
/* 过期未确认：标黄，提醒纪律线用的价格可能已经失真 */
.stale-hint {
  color: var(--el-color-warning);
}
/* 确认日期超过 90 天：标黄（与「是否过期」列的标红是两件事，
   一个是提醒价可能失真，一个是给出状态判定） */
.stale-date {
  color: var(--el-color-warning);
  border-color: var(--el-color-warning);
  font-weight: 600;
}
/* --- 阶段 4：基准售价巡检 --- */
.selling-price-check-summary {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}
.selling-price-check-block {
  margin-top: 14px;
}
.selling-price-check-title {
  margin-bottom: 6px;
  font-weight: 600;
}
/* 表头的问号提示：说明只说一次，不用每行重复 */
.pricing-header {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}
.pricing-header-help {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  cursor: help;
}
/* 输入框有未保存的覆盖值：只读值那一行标成「待生效」 */
.readonly-cell.pending-override {
  color: var(--el-color-warning);
  border-color: var(--el-color-warning);
  font-weight: 600;
}
/* ROI 守卫：成本不全时三个 ROI 一律置灰（缺输入宁可不算不可乐观） */
.roi-guarded {
  color: var(--el-text-color-placeholder);
  text-decoration: line-through;
  text-decoration-color: var(--el-text-color-placeholder);
}
.roi-guard-hint {
  font-size: 12px;
  line-height: 1.4;
  color: var(--el-color-warning);
}
/* ROI 免责提示：两条必须一直挂在表头上 */
.roi-disclaimer {
  margin-bottom: 10px;
  padding: 8px 12px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
}
/* 阶段 6：测算表四段分区 —— 事实 / 输入 / 结果 / 成本。
   表头用「顶部色条 + 浅底色」区分四段：运营从左到右按
   「看事实 → 填输入 → 看结果 → 查成本」的顺序读表，
   不用在一堆列里找下一步该动哪个。 */
.operating-table :deep(.el-table__header th.seg-fact) {
  background-color: #f4f5f7;
  box-shadow: inset 0 3px 0 #909399;
}
.operating-table :deep(.el-table__header th.seg-input) {
  background-color: #ecf5ff;
  box-shadow: inset 0 3px 0 #409eff;
}
.operating-table :deep(.el-table__header th.seg-result) {
  background-color: #f0f9eb;
  box-shadow: inset 0 3px 0 #67c23a;
}
.operating-table :deep(.el-table__header th.seg-cost) {
  background-color: #fdf6ec;
  box-shadow: inset 0 3px 0 #e6a23c;
}
/* 分段图例：表头颜色对应的文字说明 */
.segment-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.segment-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.segment-legend-item i {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 2px;
}
.segment-legend-item i.seg-fact {
  background: #909399;
}
.segment-legend-item i.seg-input {
  background: #409eff;
}
.segment-legend-item i.seg-result {
  background: #67c23a;
}
.segment-legend-item i.seg-cost {
  background: #e6a23c;
}
/* 跨仓提示（阶段 6）：同一 SKU 在别的仓滞销 ⇒ 提示调拨，而不是压低全站点底线 */
.warehouse-divergence-hint {
  margin-top: 2px;
  font-size: 12px;
  line-height: 1.4;
  color: var(--el-color-warning);
}
/* 利润测算页：测算售价低于最低售价时标红 */
.price-below-floor :deep(.el-input__inner) {
  border-color: var(--el-color-danger);
  box-shadow: 0 0 0 1px var(--el-color-danger) inset;
}
/* 已软删的 SPU 行灰显 */
.spu-inactive-row :deep(.el-table__cell) {
  color: var(--el-text-color-secondary);
  background-color: var(--el-fill-color-light);
  opacity: 0.75;
}
/* 物流批次：单件体积未填 → 行体积为 0 → 金额偏低，标红提示 */
.volume-missing :deep(.el-input__inner) {
  border-color: var(--el-color-warning);
  box-shadow: 0 0 0 1px var(--el-color-warning) inset;
}
.price-floor-hint {
  font-size: 12px;
  line-height: 1.4;
  color: var(--el-color-danger);
}
.inline-numbers {
  display: flex;
  gap: 3px;
}
.inline-numbers .el-input-number {
  width: 54px;
}
.muted {
  color: var(--el-text-color-secondary);
}
.el-pagination {
  margin-top: 14px;
  justify-content: flex-end;
}
.batch-form {
  display: flex;
  flex-wrap: wrap;
}
.batch-summary {
  display: flex;
  gap: 24px;
  justify-content: flex-end;
  align-items: center;
  margin-top: 16px;
  font-weight: 600;
}
.bill-lines :deep(.el-input-number) {
  width: 100%;
}
</style>
