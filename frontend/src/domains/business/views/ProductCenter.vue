<template>
  <div class="product-center erp-page-container">
    <div class="page-header">
      <div>
        <h1 class="page-title">商品中心</h1>
        <p class="page-subtitle">公司商品主数据、采购批次与可追溯成本</p>
      </div>
      <el-tag type="info">ERP 主数据</el-tag>
    </div>
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
          >
        </div>
        <el-table
          :data="spus"
          v-loading="loadingSpus"
          stripe
          border
          class="flat-table"
          ><el-table-column label="SPU" min-width="150"
            ><template #default="{ row }"
              ><el-input
                v-model="row.spu"
                :disabled="!row.__new"
                size="small"
                placeholder="HOME-0001" /></template></el-table-column
          ><el-table-column label="商品名称" min-width="190"
            ><template #default="{ row }"
              ><el-input
                v-model="row.spu_name"
                size="small" /></template></el-table-column
          ><el-table-column label="一级品类" width="150"
            ><template #default="{ row }"
              ><el-select
                v-model="row.category_l1_code"
                size="small"
                placeholder="选择"
                @change="row.category_l2_code = ''"
                ><el-option
                  v-for="cat in l1Categories"
                  :key="categoryCode(cat)"
                  :label="cat.name_zh"
                  :disabled="cat.status !== 'active' || !cat.is_selectable || legacyUnselectableCodes.has(categoryCode(cat))"
                  :value="
                    categoryCode(cat)
                  " /></el-select></template></el-table-column
          ><el-table-column label="二级品类" width="170"
            ><template #default="{ row }"
              ><el-select
                v-model="row.category_l2_code"
                size="small"
                placeholder="选择"
                ><el-option
                  v-for="cat in childCategories(row.category_l1_code)"
                  :key="categoryCode(cat)"
                  :label="cat.name_zh"
                  :disabled="cat.status !== 'active' || !cat.is_selectable || legacyUnselectableCodes.has(categoryCode(cat))"
                  :value="
                    categoryCode(cat)
                  " /></el-select></template></el-table-column
          ><el-table-column label="物流货损率" width="120"
            ><template #default="{ row }"
              ><el-input-number
                v-model="row.logistics_damage_rate"
                :min="0"
                :max="1"
                :step="0.01"
                :controls="false"
                size="small" /></template></el-table-column
          ><el-table-column label="退货损失率" width="120"
            ><template #default="{ row }"
              ><el-input-number
                v-model="row.return_loss_rate"
                :min="0"
                :max="1"
                :step="0.01"
                :controls="false"
                size="small" /></template></el-table-column
          ><el-table-column label="状态" width="110"
            ><template #default="{ row }"
              ><el-select v-model="row.biz_status" size="small"
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
                size="small" /></template></el-table-column
          ><el-table-column label="操作" width="110" fixed="right"
            ><template #default="{ row }"
              ><el-button link type="primary" @click="showBindings(row)"
                >SKU 归属</el-button
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
            placeholder="所属 SPU"
            @change="loadSkus"
            ><el-option
              v-for="spu in spus"
              :key="spu.spu"
              :label="`${spu.spu} ${spu.spu_name || ''}`"
              :value="spu.spu" /></el-select
          ><el-button type="primary" :icon="Plus" @click="addSkuRow"
            >新增行</el-button
          ><el-button
            :icon="Check"
            :disabled="!skuDirty.length"
            :loading="saving"
            @click="saveSkuRows"
            >保存变更</el-button
          >
        </div>
        <el-table
          :data="skus"
          v-loading="loadingSkus"
          stripe
          border
          class="flat-table sku-table"
          ><el-table-column label="SPU" width="155"
            ><template #default="{ row }"
              ><el-select
                v-model="row.spu"
                filterable
                clearable
                size="small"
                placeholder="选择 SPU"
                ><el-option
                  v-for="spu in spus"
                  :key="spu.spu"
                  :label="spu.spu"
                  :value="spu.spu" /></el-select></template></el-table-column
          ><el-table-column label="ERP SKU" width="160"
            ><template #default="{ row }"
              ><el-input
                v-model="row.sku_key"
                :disabled="!row.__new"
                size="small" /></template></el-table-column
          ><el-table-column label="名称" min-width="180"
            ><template #default="{ row }"
              ><el-input
                v-model="row.sku_name"
                size="small" /></template></el-table-column
          ><el-table-column label="规格" width="140"
            ><template #default="{ row }"
              ><el-input
                v-model="row.specification"
                size="small" /></template></el-table-column
          ><el-table-column label="重量 kg" width="105"
            ><template #default="{ row }"
              ><el-input-number
                v-model="row.weight_kg"
                :min="0"
                :precision="3"
                :controls="false"
                size="small" /></template></el-table-column
          ><el-table-column label="包装 cm" width="175"
            ><template #default="{ row }"
              ><div class="inline-numbers">
                <el-input-number
                  v-model="row.package_length_cm"
                  :min="0"
                  :controls="false"
                  size="small"
                /><el-input-number
                  v-model="row.package_width_cm"
                  :min="0"
                  :controls="false"
                  size="small"
                /><el-input-number
                  v-model="row.package_height_cm"
                  :min="0"
                  :controls="false"
                  size="small"
                /></div></template></el-table-column
          ><el-table-column label="体积 m³" width="100"
            ><template #default="{ row }">{{
              formatVolume(row)
            }}</template></el-table-column
          ><el-table-column label="箱规" width="80"
            ><template #default="{ row }"
              ><el-input-number
                v-model="row.units_per_carton"
                :min="1"
                :controls="false"
                size="small" /></template></el-table-column
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
      <el-tab-pane label="平台 SKU 利润" name="operating">
        <div class="toolbar">
          <el-select
            v-model="operatingQuery.platform_code"
            clearable
            filterable
            placeholder="平台"
            @change="loadOperatingProfiles"
            ><el-option
              v-for="item in operatingDimensions.platforms"
              :key="item.platform_code"
              :label="item.name || item.platform_code"
              :value="item.platform_code"
          /></el-select>
          <el-select v-model="operatingQuery.spu" clearable filterable placeholder="SPU" @change="loadOperatingProfiles">
            <el-option v-for="item in operatingDimensions.spus || []" :key="item" :label="item" :value="item" />
          </el-select>
          <el-select v-model="operatingQuery.sku_id" clearable filterable placeholder="ERP SKU" @change="loadOperatingProfiles">
            <el-option v-for="item in operatingDimensions.skus || []" :key="item.sku_id" :label="item.sku_key" :value="item.sku_id" />
          </el-select>
          <el-select
            v-model="operatingQuery.warehouse_code"
            clearable
            filterable
            placeholder="收货仓库"
            @change="loadOperatingProfiles"
            ><el-option
              v-for="item in operatingDimensions.warehouses"
              :key="item.warehouse_code || item"
              :label="item.warehouse_name || item.warehouse_code || item"
              :value="item.warehouse_code || item"
          /></el-select>
          <el-button type="primary" :icon="Plus" @click="addOperatingRow"
            >新增行</el-button
          >
          <el-button
            :icon="Check"
            :disabled="!operatingDirty.length"
            :loading="saving"
            @click="saveOperatingRows"
            >保存变更</el-button
          >
        </div>
        <el-table
          :data="operatingProfiles"
          v-loading="loadingOperating"
          stripe
          border
          class="flat-table operating-table"
        >
          <el-table-column label="平台" width="120"
            ><template #default="{ row }"
              ><el-select
                v-model="row.platform_code"
                filterable
                size="small"
                @change="markOperatingDirty(row)"
                ><el-option
                  v-for="item in operatingDimensions.platforms"
                  :key="item.platform_code"
                  :label="item.name || item.platform_code"
                  :value="item.platform_code" /></el-select></template
          ></el-table-column>
          <el-table-column label="收货仓库" width="150"
            ><template #default="{ row }"
              ><el-select
                v-model="row.warehouse_code"
                filterable
                size="small"
                @change="markOperatingDirty(row)"
                ><el-option
                  v-for="item in operatingDimensions.warehouses"
                  :key="item.warehouse_code || item"
                  :label="item.warehouse_name || item.warehouse_code || item"
                  :value="item.warehouse_code || item" /></el-select></template
          ></el-table-column>
          <el-table-column label="运输方式" width="120"><template #default="{ row }"><el-select v-model="row.transport_type" size="small" @change="markOperatingDirty(row)"><el-option label="海运" value="sea" /><el-option label="空运" value="air" /><el-option label="铁路运输" value="rail" /></el-select></template></el-table-column>
          <el-table-column label="ERP SKU" width="150"
            ><template #default="{ row }"
              ><el-select
                v-model="row.sku_id"
                filterable
                size="small"
                @change="markOperatingDirty(row)"
                ><el-option
                  v-for="item in skus"
                  :key="item.sku_id"
                  :label="item.sku_key"
                  :value="item.sku_id" /></el-select></template
          ></el-table-column>
          <el-table-column label="售价" width="110"
            ><template #default="{ row }"
              ><el-input-number
                v-model="row.selling_price"
                :min="0"
                :controls="false"
                size="small"
                @change="markOperatingDirty(row)" /></template
          ></el-table-column>
          <el-table-column label="优惠券" width="110"
            ><template #default="{ row }"
              ><el-input-number
                v-model="row.default_coupon_amount"
                :min="0"
                :controls="false"
                size="small"
                @change="markOperatingDirty(row)" /></template
          ></el-table-column>
          <el-table-column label="采购成本" width="110"
            ><template #default="{ row }">{{
              money(row.purchase_cost)
            }}</template></el-table-column
          >
          <el-table-column label="预计物流" width="120"
            ><template #default="{ row }"
              ><el-input-number
                v-model="row.expected_logistics_cost"
                :min="0"
                :precision="2"
                :controls="false"
                size="small"
                @change="markOperatingDirty(row)" /></template
          ></el-table-column>
          <el-table-column label="预计仓储" width="120"
            ><template #default="{ row }"
              ><el-input-number
                v-model="row.expected_storage_cost"
                :min="0"
                :precision="2"
                :controls="false"
                size="small"
                @change="markOperatingDirty(row)" /></template
          ></el-table-column>
          <el-table-column label="平台费率" width="100"><template #default="{ row }">{{ percent(row.platform_fee_rate) }}</template></el-table-column>
          <el-table-column label="继承货损率" width="110"><template #default="{ row }">{{ percent(row.logistics_damage_rate) }}</template></el-table-column>
          <el-table-column label="继承退货损失率" width="130"><template #default="{ row }">{{ percent(row.return_loss_rate) }}</template></el-table-column>
          <el-table-column label="实际物流" width="110"
            ><template #default="{ row }">{{
              money(row.actual_logistics_cost)
            }}</template></el-table-column
          >
          <el-table-column label="实际仓储" width="110"
            ><template #default="{ row }">{{
              row.actual_storage_cost == null
                ? "未录入"
                : money(row.actual_storage_cost)
            }}</template></el-table-column
          >
          <el-table-column label="预计利润" width="120"
            ><template #default="{ row }">{{
              money(row.estimated_contribution_profit)
            }}</template></el-table-column
          >
          <el-table-column label="利润率" width="100"
            ><template #default="{ row }">{{
              percent(row.estimated_margin_rate)
            }}</template></el-table-column
          >
          <el-table-column prop="cost_completeness" label="完整度" width="90" />
          <el-table-column label="操作" width="180" fixed="right"
            ><template #default="{ row }"
              ><el-tag v-if="!row.profile_id" type="warning" size="small">待配置</el-tag><el-button v-else link type="primary" @click="openOperatingProfit(row)"
                >计算利润</el-button
              ><el-button v-if="row.profile_id" link @click="showOperatingHistory(row)"
                >历史版本</el-button
              ></template
            ></el-table-column
          >
        </el-table>
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
            <el-table :data="rules" stripe border
              ><el-table-column label="服务商"
                ><template #default="{ row }"
                  ><el-input
                    v-model="row.logistics_provider"
                    size="small" /></template></el-table-column
              ><el-table-column label="收货仓库"
                ><template #default="{ row }"
                  ><el-select v-model="row.warehouse_code" size="small" filterable>
                    <el-option v-for="item in operatingDimensions.warehouses" :key="item.warehouse_code" :label="`${item.warehouse_name} (${item.country_name})`" :value="item.warehouse_code" />
                  </el-select></template></el-table-column
              ><el-table-column label="运输方式"
                ><template #default="{ row }"
                  ><el-select v-model="row.transport_type" size="small"><el-option label="海运" value="sea" /><el-option label="空运" value="air" /><el-option label="铁路运输" value="rail" /></el-select></template></el-table-column
              ><el-table-column label="货物类型"
                ><template #default="{ row }"
                  ><el-select v-model="row.cargo_class" size="small"
                    ><el-option label="普通货" value="normal" /><el-option
                      label="敏感货 M"
                      value="sensitive" /></el-select></template></el-table-column
              ><el-table-column label="计费方式"
                ><template #default="{ row }"
                  ><el-select v-model="row.billing_basis" size="small"
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
                    size="small" /></template></el-table-column
              ><el-table-column label="生效日期"
                ><template #default="{ row }"
                  ><el-date-picker
                    v-model="row.effective_from"
                    type="date"
                    value-format="YYYY-MM-DD"
                    size="small" /></template></el-table-column></el-table></el-tab-pane
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
    <el-drawer
      v-model="operatingProfitDrawer.visible"
      title="平台 SKU 利润试算"
      size="560px"
    >
      <el-form :model="operatingProfitDrawer.form" label-width="110px">
        <el-form-item label="SKU / 经营范围"
          ><span>{{ operatingProfitDrawer.label }}</span></el-form-item
        >
        <el-form-item label="售价"
          ><el-input-number
            v-model="operatingProfitDrawer.form.selling_price"
            :min="0"
            :precision="2"
            :controls="false"
        /></el-form-item>
        <el-form-item label="优惠券"
          ><el-input-number
            v-model="operatingProfitDrawer.form.coupon_amount"
            :min="0"
            :precision="2"
            :controls="false"
        /></el-form-item>
        <el-form-item label="运输方式"
          ><el-input v-model="operatingProfitDrawer.form.transport_type"
        /></el-form-item>
      </el-form>
      <el-descriptions v-if="operatingProfitDrawer.preview" :column="2" border>
        <el-descriptions-item label="净收入">{{
          money(operatingProfitDrawer.preview.net_revenue)
        }}</el-descriptions-item>
        <el-descriptions-item label="采购成本">{{
          money(operatingProfitDrawer.preview.purchase_cost)
        }}</el-descriptions-item>
        <el-descriptions-item label="物流成本">{{
          money(operatingProfitDrawer.preview.logistics_cost)
        }}</el-descriptions-item>
        <el-descriptions-item label="仓储成本">{{
          money(operatingProfitDrawer.preview.storage_cost)
        }}</el-descriptions-item>
        <el-descriptions-item label="预计货损">{{
          money(operatingProfitDrawer.preview.expected_damage_loss)
        }}</el-descriptions-item>
        <el-descriptions-item label="预计退货损失">{{
          money(operatingProfitDrawer.preview.expected_return_loss)
        }}</el-descriptions-item>
        <el-descriptions-item label="预计贡献利润">{{
          money(operatingProfitDrawer.preview.estimated_contribution_profit)
        }}</el-descriptions-item>
        <el-descriptions-item label="预计利润率">{{
          percent(operatingProfitDrawer.preview.estimated_margin_rate)
        }}</el-descriptions-item>
        <el-descriptions-item label="完整度">{{
          operatingProfitDrawer.preview.cost_completeness
        }}</el-descriptions-item>
      </el-descriptions>
      <template #footer
        ><el-button @click="previewOperatingProfit">计算</el-button
        ><el-button
          type="primary"
          :disabled="!operatingProfitDrawer.preview"
          @click="saveOperatingProfit"
          >保存版本</el-button
        ></template
      >
    </el-drawer>
    <el-drawer
      v-model="operatingHistoryDrawer.visible"
      title="利润版本历史"
      size="620px"
    >
      <el-table :data="operatingHistoryDrawer.rows" stripe border>
        <el-table-column prop="estimate_as_of" label="估算时间" />
        <el-table-column
          prop="estimated_contribution_profit"
          label="预计利润"
        />
        <el-table-column prop="estimated_margin_rate" label="利润率"
          ><template #default="{ row }">{{
            percent(row.estimated_margin_rate)
          }}</template></el-table-column
        >
        <el-table-column prop="cost_completeness" label="完整度" />
      </el-table>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Check, Plus } from "@element-plus/icons-vue";
import productCenterApi from "@/api/productCenter";

const activeTab = ref("spu");
const costTab = ref("rules");
const saving = ref(false);
const loadingSpus = ref(false);
const loadingSkus = ref(false);
const loadingBills = ref(false);
const spus = ref([]);
const skus = ref([]);
const categories = ref([]);
const rules = ref([]);
const purchaseOrders = ref([]);
const logisticsBatches = ref([]);
const operatingProfiles = ref([]);
const operatingDimensions = reactive({
  platforms: [],
  spus: [],
  skus: [],
  warehouses: [],
});
const operatingHistoryDrawer = reactive({ visible: false, rows: [] });
const operatingProfitDrawer = reactive({
  visible: false,
  label: "",
  profileId: null,
  form: {},
  preview: null,
});
const loadingOperating = ref(false);
const spuTotal = ref(0);
const skuTotal = ref(0);
const skuSpuFilter = ref("");
const operatingQuery = reactive({
  platform_code: "",
  spu: "",
  sku_id: "",
  warehouse_code: "",
});
const billStatus = ref("");
const selectedPurchaseOrders = ref([]);
const unmappedPurchaseSkus = ref([]);
const dirtyRows = ref(new Set());
const dirtyRuleRows = ref(new Set());
const spuQuery = reactive({
  keyword: "",
  biz_status: "",
  page: 1,
  page_size: 20,
});
const skuQuery = reactive({ keyword: "", page: 1, page_size: 20 });
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
const legacyUnselectableCodes = new Set(["PET_DAILY"]);
const l1Categories = computed(() =>
  categories.value.filter((item) => item.level === 1 || !parentCode(item)),
);
const childCategories = (code) =>
  categories.value.filter(
    (item) =>
      (item.level === 2 || parentCode(item)) && parentCode(item) === code,
  );
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
  units_per_carton: null,
  default_purchase_cost: null,
  expected_logistics_cost: null,
  expected_storage_cost: null,
  purchase_cost_source: "manual",
  purchase_cost_confidence: "low",
});
const addSpuRow = () => spus.value.unshift(blankSpu());
const addSkuRow = () => skus.value.unshift(blankSku());
const addRuleRow = () =>
  rules.value.unshift({
    __new: true,
    logistics_provider: "",
    warehouse_code: "",
    transport_type: "sea",
    cargo_class: "normal",
    billing_basis: "volume",
    freight_unit_rate: null,
    effective_from: "",
  });
const loadSpus = async () => {
  loadingSpus.value = true;
  try {
    const res = await productCenterApi.listSpus(spuQuery);
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
const loadCategories = async () => {
  try {
    categories.value = await productCenterApi.listCategories({
      include_inactive: true,
    });
  } catch {
    categories.value = [];
  }
};
const loadRules = async () => {
  try {
    rules.value = await productCenterApi.listProviderRules({
      status: "active",
    });
  } catch {
    rules.value = [];
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
const loadOperatingProfiles = async () => {
  loadingOperating.value = true;
  try {
    operatingProfiles.value = await productCenterApi.listSkuOperatingProfiles({
      platform_code: operatingQuery.platform_code || undefined,
      spu: operatingQuery.spu || undefined,
      sku_id: operatingQuery.sku_id || undefined,
      warehouse_code: operatingQuery.warehouse_code || undefined,
      status: "active",
    });
  } catch (error) {
    operatingProfiles.value = [];
    ElMessage.error(error.message || "加载平台 SKU 利润失败");
  } finally {
    loadingOperating.value = false;
  }
};
const operatingDirty = computed(() =>
  operatingProfiles.value.filter((row) => row.__new || row.__dirty),
);
const markOperatingDirty = (row) => {
  row.__dirty = true;
};
const addOperatingRow = () => {
  const sku = skus.value[0];
  operatingProfiles.value.unshift({
    __new: true,
    sku_id: sku?.sku_id || null,
    platform_code:
      operatingQuery.platform_code ||
      operatingDimensions.platforms[0]?.platform_code ||
      "",
    warehouse_code:
      operatingQuery.warehouse_code || operatingDimensions.warehouses[0]?.warehouse_code || "",
    warehouse_name: "",
    transport_type: "sea",
    selling_price: null,
    default_coupon_amount: 0,
    platform_fee_rate: null,
    expected_logistics_cost: null,
    expected_storage_cost: null,
    cost_completeness: "incomplete",
  });
};
const saveOperatingRows = async () => {
  saving.value = true;
  try {
    const items = operatingDirty.value.map(({ __new, __dirty, ...row }) => row);
    await productCenterApi.bulkSaveSkuOperatingProfiles({ items });
    await loadOperatingProfiles();
    ElMessage.success("平台 SKU 利润配置已保存");
  } catch (error) {
    ElMessage.error(error.message || "保存平台 SKU 利润配置失败");
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
const saveRuleRows = async () => {
  try {
    for (const row of ruleDirty.value) {
      const { __new, ...payload } = row;
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
const showBindings = async (row) => {
  bindingDrawer.visible = true;
  bindingDrawer.spu = row.spu;
  try {
    bindingDrawer.rows = await productCenterApi.listSpuSkus(row.spu);
  } catch (error) {
    ElMessage.error(error.message || "加载绑定历史失败");
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
const openOperatingProfit = (row) => {
  operatingProfitDrawer.visible = true;
  operatingProfitDrawer.profileId = row.profile_id;
  operatingProfitDrawer.label = `${row.sku_id} / ${row.platform_code} / ${row.warehouse_code}`;
  operatingProfitDrawer.form = {
    selling_price: row.selling_price,
    coupon_amount: row.default_coupon_amount || 0,
    transport_type: row.transport_type || "sea",
  };
  operatingProfitDrawer.preview = null;
};
const previewOperatingProfit = async () => {
  try {
    operatingProfitDrawer.preview =
      await productCenterApi.previewSkuOperatingProfit(
        operatingProfitDrawer.profileId,
        operatingProfitDrawer.form,
      );
  } catch (error) {
    ElMessage.error(error.message || "利润预览失败");
  }
};
const saveOperatingProfit = async () => {
  try {
    await productCenterApi.saveSkuOperatingProfit(
      operatingProfitDrawer.profileId,
      operatingProfitDrawer.form,
    );
    operatingProfitDrawer.visible = false;
    await loadOperatingProfiles();
    ElMessage.success("平台 SKU 利润版本已保存");
  } catch (error) {
    ElMessage.error(error.message || "保存利润版本失败");
  }
};
const showOperatingHistory = async (row) => {
  try {
    operatingHistoryDrawer.rows =
      await productCenterApi.listSkuOperatingProfitHistory(row.profile_id);
    operatingHistoryDrawer.visible = true;
  } catch (error) {
    ElMessage.error(error.message || "加载利润历史失败");
  }
};
const billingUnitFor = (basis) =>
  ({
    volume: "RMB/CBM",
    weight: "RMB/KG",
    quantity: "RMB/件",
    fixed: "RMB/票",
  })[basis] || "RMB/CBM";
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
  return (
    candidates.sort((left, right) => {
      const score = (rule) =>
         Number(rule.warehouse_code === warehouseCode) * 2 +
        Number(rule.transport_type === form.transport_type);
      return score(right) - score(left);
    })[0] || null
  );
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
  for (const order of orders) {
    const poLines = await productCenterApi.listPurchaseOrderLines(order.po_id);
    for (const poLine of poLines) {
      const sku =
        skus.value.find((item) => item.sku_id === poLine.sku_id) ||
        skus.value.find((item) => item.sku_key === poLine.platform_sku);
      if (sku) {
        const shippedQty = poLine.qty_received || poLine.qty_ordered || 0;
        const unitVolume = Number(formatVolume(sku)) || 0;
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
          billing_unit: "RMB/CBM",
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
const formatVolume = (row) =>
  [row.package_length_cm, row.package_width_cm, row.package_height_cm].every(
    (value) => value != null,
  )
    ? (
        (row.package_length_cm * row.package_width_cm * row.package_height_cm) /
        1000000
      ).toFixed(4)
    : "-";
const money = (value) => (value == null ? "-" : `¥${Number(value).toFixed(2)}`);
const percent = (value) =>
  value == null ? "-" : `${(Number(value) * 100).toFixed(1)}%`;
onMounted(async () => {
  await Promise.all([
    loadSpus(),
    loadSkus(),
    loadCategories(),
    loadRules(),
    loadPurchaseOrders(),
    loadBatches(),
    loadOperatingDimensions(),
    loadOperatingProfiles(),
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
.sku-table :deep(.el-table__cell) {
  padding: 6px 4px;
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
