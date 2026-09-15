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
          ><el-table-column label="采购成本" width="115"><template #default="{ row }"><el-input-number v-model="row.default_purchase_cost" :min="0" :precision="2" :controls="false" size="small" @change="markDirty('sku', row)" /></template></el-table-column
          ><el-table-column label="采购成本来源" width="120"><template #default="{ row }">{{ row.purchase_cost_source || "待补充" }}</template></el-table-column
          ><el-table-column label="采购成本确认时间" width="145"><template #default="{ row }">{{ row.purchase_cost_confirmed_at || "-" }}</template></el-table-column
          ><el-table-column label="参考售价" width="115"><template #default="{ row }"><el-input-number v-model="row.reference_selling_price" :min="0" :precision="2" :controls="false" size="small" @change="markDirty('sku', row)" /></template></el-table-column
          ><el-table-column label="售价来源" width="120"><template #default="{ row }"><el-input v-model="row.selling_price_source" size="small" @change="markDirty('sku', row)" /></template></el-table-column
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
          <el-button v-if="canManagePlatformFee" plain @click="openPlatformFeeDrawer">平台费率管理</el-button>
        </div>
        <el-alert v-if="!operatingQuery.platform_code || !operatingQuery.warehouse_code || !operatingQuery.transport_type" type="info" :closable="false" title="请选择平台、收货仓库和物流方式后加载 SKU 测算数据" />
        <el-table
          :data="operatingProfiles"
          v-loading="loadingOperating"
          stripe
          border
          class="flat-table operating-table"
        >
          <el-table-column prop="spu" label="SPU" width="160" />
          <el-table-column prop="sku_key" label="ERP SKU" width="155" />
          <el-table-column prop="sku_name" label="商品名称" min-width="200" show-overflow-tooltip />
          <el-table-column label="参考售价" width="105"><template #default="{ row }">{{ money(row.reference_selling_price) }}</template></el-table-column>
          <el-table-column label="竞品价格" width="110"><template #default="{ row }"><el-input-number v-model="row.competitor_price" :min="0" :controls="false" size="small" /></template></el-table-column>
          <el-table-column label="预计售价" width="110"
            ><template #default="{ row }"
              ><el-input-number
                v-model="row.expected_selling_price"
                :min="0"
                :controls="false"
                size="small"
                @change="previewOperatingRow(row)" /></template
          ></el-table-column>
          <el-table-column label="优惠券" width="110"
            ><template #default="{ row }"
              ><el-input-number
                v-model="row.seller_coupon_amount"
                :min="0"
                :controls="false"
                size="small"
                @change="previewOperatingRow(row)" /></template
          ></el-table-column>
          <el-table-column label="采购成本" width="110"
            ><template #default="{ row }">{{
              money(row.purchase_cost)
            }}</template></el-table-column
          >
          <el-table-column label="物流方式" width="100"><template #default="{ row }">{{ transportLabel(row.transport_type) }}</template></el-table-column>
          <el-table-column label="参考物流" width="120"><template #default="{ row }">{{ money(referenceLogisticsCost(row)) }}</template></el-table-column>
          <el-table-column label="参考仓储" width="120"><template #default="{ row }">{{ money(referenceStorageCost(row)) }}</template></el-table-column>
          <el-table-column label="广告费率" width="105"><template #default="{ row }"><el-input-number v-model="row.expected_ad_rate" :min="0" :max="1" :step="0.01" :controls="false" size="small" @change="previewOperatingRow(row)" /></template></el-table-column>
          <el-table-column label="平台费率" width="100"><template #default="{ row }">{{ percent(row.platform_fee_rate) }}</template></el-table-column>
          <el-table-column label="平台费用" width="105"><template #default="{ row }">{{ money(row.preview?.expected?.platform_fee) }}</template></el-table-column>
          <el-table-column label="预计广告费用" width="105"><template #default="{ row }">{{ money(row.preview?.expected?.ad_cost) }}</template></el-table-column>
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
                ? "未录入/参考回退"
                : money(row.actual_storage_cost)
            }}</template></el-table-column
          >
          <el-table-column label="预计利润" width="120"
            ><template #default="{ row }">{{
              money(row.preview?.expected?.profit)
            }}</template></el-table-column
          >
          <el-table-column label="利润率" width="100"
            ><template #default="{ row }">{{
              percent(row.preview?.expected?.margin_rate)
            }}</template></el-table-column
          >
          <el-table-column label="重估利润" width="120"><template #default="{ row }">{{ money(row.preview?.actual_recost?.profit) }}</template></el-table-column>
          <el-table-column label="重估完整度" width="105"><template #default="{ row }">{{ row.preview?.actual_recost?.completeness || row.configuration_status }}</template></el-table-column>
          <el-table-column label="操作" width="180" fixed="right"
            ><template #default="{ row }"
              ><el-button link type="primary" @click="previewOperatingRow(row)">试算</el-button
              ><el-button link type="success" @click="saveOperatingEstimate(row)">保存版本</el-button
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
          ><el-tab-pane label="仓储规则" name="storage-rules"
            ><div class="toolbar">
              <el-button type="primary" :icon="Plus" @click="addStorageRuleRow">新增仓储规则</el-button>
              <span class="muted">固定按体积计费：CNY/CBM/月</span>
            </div>
            <el-table :data="storageRules" v-loading="loadingStorageRules" stripe border>
              <el-table-column label="收货仓库" min-width="180"><template #default="{ row }"><el-select v-model="row.warehouse_code" size="small" filterable :disabled="!row.__new"><el-option v-for="item in operatingDimensions.warehouses" :key="item.warehouse_code" :label="`${item.warehouse_name} (${item.country_name})`" :value="item.warehouse_code" /></el-select></template></el-table-column>
              <el-table-column label="计费方式" width="110"><template #default>按体积</template></el-table-column>
              <el-table-column label="计费单位" width="130"><template #default>CNY/CBM/月</template></el-table-column>
              <el-table-column label="仓储单价" width="120"><template #default="{ row }"><el-input-number v-model="row.unit_rate_cny" :min="0" :precision="4" :controls="false" size="small" :disabled="!row.__new" /></template></el-table-column>
              <el-table-column label="生效日期" width="145"><template #default="{ row }"><el-date-picker v-model="row.effective_from" type="date" value-format="YYYY-MM-DD" size="small" :disabled="!row.__new" /></template></el-table-column>
              <el-table-column label="状态" width="105"><template #default="{ row }"><el-tag :type="row.status === 'active' ? 'success' : 'info'">{{ row.status === 'active' ? '启用' : '已停用' }}</el-tag></template></el-table-column>
              <el-table-column label="版本" width="120"><template #default="{ row }"><el-input v-model="row.version" size="small" /></template></el-table-column>
              <el-table-column label="来源" width="130"><template #default="{ row }"><el-input v-model="row.source" size="small" /></template></el-table-column>
              <el-table-column label="备注" min-width="150"><template #default="{ row }"><el-input v-model="row.notes" size="small" /></template></el-table-column>
              <el-table-column label="操作" width="150" fixed="right"><template #default="{ row }"><el-button link type="primary" @click="saveStorageRule(row)">保存</el-button><el-button v-if="!row.__new && row.status === 'active'" link type="danger" @click="disableStorageRule(row)">停用</el-button></template></el-table-column>
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
      v-model="platformFeeDrawer.visible"
      title="平台费率管理"
      size="460px"
      destroy-on-close
    >
      <el-alert type="info" :closable="false" title="平台综合费率用于预计利润计算，仅管理员、主管和财务可维护。" />
      <el-form :model="platformFeeDrawer.form" label-width="110px" class="drawer-form">
        <el-form-item label="平台"><span>{{ platformFeeDrawer.label }}</span></el-form-item>
        <el-form-item label="综合费率"><el-input-number v-model="platformFeeDrawer.form.default_fee_rate" :min="0" :max="1" :step="0.01" :precision="4" :controls="false" /></el-form-item>
        <el-form-item label="生效日期"><el-date-picker v-model="platformFeeDrawer.form.fee_rate_effective_from" type="date" value-format="YYYY-MM-DD" /></el-form-item>
        <el-form-item label="来源"><el-input v-model="platformFeeDrawer.form.fee_rate_source" /></el-form-item>
        <el-form-item label="版本"><el-input v-model="platformFeeDrawer.form.fee_rate_version" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="platformFeeDrawer.visible = false">取消</el-button><el-button type="primary" :loading="saving" @click="savePlatformFeeRate">保存</el-button></template>
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
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Check, Plus } from "@element-plus/icons-vue";
import productCenterApi from "@/api/productCenter";
import { useUserStore } from "@/stores/user";

const userStore = useUserStore();
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
  page: 1,
  page_size: 20,
});
const platformFeeDrawer = reactive({
  visible: false,
  label: "",
  form: {
    default_fee_rate: null,
    fee_rate_effective_from: "",
    fee_rate_source: "",
    fee_rate_version: "",
  },
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
const transportLabel = (value) =>
  ({ sea: "海运", air: "空运", rail: "铁路运输" })[value] || "待选择";
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
  reference_selling_price: null,
  selling_price_source: "manual",
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
const loadStorageRules = async () => {
  loadingStorageRules.value = true;
  try {
    storageRules.value = await productCenterApi.listWarehouseStorageRules({
      include_inactive: true,
    });
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
    effective_from: new Date().toISOString().slice(0, 10),
    status: "active",
    source: "manual",
    version: "v1",
    notes: "",
  });
const storageRulePayload = (row) => {
  const { __new, rule_id, billing_basis, billing_unit, ...payload } = row;
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
const openPlatformFeeDrawer = () => {
  const platform = operatingDimensions.platforms.find(
    (item) => item.platform_code === operatingQuery.platform_code,
  );
  if (!platform) {
    ElMessage.warning("请先选择销售平台");
    return;
  }
  platformFeeDrawer.label = platform.name || platform.platform_code;
  platformFeeDrawer.form = {
    default_fee_rate: platform.default_fee_rate ?? null,
    fee_rate_effective_from: platform.fee_rate_effective_from || new Date().toISOString().slice(0, 10),
    fee_rate_source: platform.fee_rate_source || "manual",
    fee_rate_version: platform.fee_rate_version || "v1",
  };
  platformFeeDrawer.visible = true;
};
const savePlatformFeeRate = async () => {
  const platformCode = operatingQuery.platform_code;
  if (!platformCode) return;
  saving.value = true;
  try {
    await productCenterApi.updatePlatformFeeRate(platformCode, platformFeeDrawer.form);
    platformFeeDrawer.visible = false;
    await loadOperatingDimensions();
    await loadOperatingProfiles();
    ElMessage.success("平台费率已保存");
  } catch (error) {
    ElMessage.error(error.message || "保存平台费率失败");
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
      page: operatingQuery.page,
      page_size: operatingQuery.page_size,
    });
    operatingProfiles.value = (response.data || []).map((row) => ({
      ...row,
      expected_selling_price: row.expected_selling_price ?? row.reference_selling_price,
      seller_coupon_amount: row.seller_coupon_amount ?? 0,
      expected_ad_rate: row.expected_ad_rate ?? 0,
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
  expected_ad_rate: row.expected_ad_rate ?? 0,
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
const previewOperatingRow = async (row) => {
  try {
    row.preview = await productCenterApi.previewPlatformSkuProfit(operatingPayload(row));
  } catch (error) {
    ElMessage.error(error.message || "利润试算失败");
  }
};
const saveOperatingEstimate = async (row) => {
  saving.value = true;
  try {
    await productCenterApi.savePlatformSkuProfitEstimates(operatingPayload(row));
    await previewOperatingRow(row);
    ElMessage.success("利润版本已保存");
  } catch (error) {
    ElMessage.error(error.message || "保存利润版本失败");
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
    loadStorageRules(),
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
