<template>
  <div class="product-center erp-page-container">
    <div class="page-header">
      <div>
        <h1 class="page-title">商品中心</h1>
        <p class="page-subtitle">维护公司级 SPU、ERP SKU 资料和商品成本基础数据</p>
      </div>
      <el-tag type="info">ERP 主数据</el-tag>
    </div>

    <el-tabs v-model="activeTab" class="product-tabs">
      <el-tab-pane label="SPU 管理" name="spu">
        <div class="toolbar">
          <el-input v-model="spuQuery.keyword" clearable placeholder="搜索 SPU 或名称" @keyup.enter="loadSpus" />
          <el-select v-model="spuQuery.biz_status" clearable placeholder="经营状态" @change="loadSpus">
            <el-option label="候选" value="candidate" />
            <el-option label="测试" value="testing" />
            <el-option label="主推" value="promoted" />
            <el-option label="淘汰" value="retired" />
          </el-select>
          <el-button type="primary" :icon="Plus" @click="openSpuCreate">新增 SPU</el-button>
        </div>
        <el-table :data="spus" v-loading="loadingSpus" stripe>
          <el-table-column prop="spu" label="SPU" width="170" />
          <el-table-column prop="spu_name" label="商品名称" min-width="220" show-overflow-tooltip />
          <el-table-column prop="category_l1" label="一级品类" width="130" />
          <el-table-column prop="category_l2" label="二级品类" width="130" />
          <el-table-column prop="biz_status" label="状态" width="110" />
          <el-table-column prop="owner_user_id" label="负责人" width="100" />
          <el-table-column label="操作" width="210" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="editSpu(row)">编辑</el-button>
              <el-button link @click="showBindings(row)">SKU 归属</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination v-model:current-page="spuQuery.page" v-model:page-size="spuQuery.page_size" :total="spuTotal" layout="total, sizes, prev, pager, next" @current-change="loadSpus" @size-change="loadSpus" />
      </el-tab-pane>

      <el-tab-pane label="SKU 资料" name="sku">
        <div class="toolbar">
          <el-input v-model="skuQuery.keyword" clearable placeholder="搜索 SKU 或名称" @keyup.enter="loadSkus" />
          <el-button type="primary" :icon="Plus" @click="openSkuCreate">新增 SKU</el-button>
        </div>
        <el-table :data="skus" v-loading="loadingSkus" stripe>
          <el-table-column prop="sku_key" label="ERP SKU" min-width="190" />
          <el-table-column prop="sku_name" label="名称" min-width="220" show-overflow-tooltip />
          <el-table-column prop="specification" label="规格" min-width="160" />
          <el-table-column prop="weight_kg" label="重量(kg)" width="110" />
          <el-table-column prop="default_purchase_cost" label="默认采购成本" width="120" />
          <el-table-column label="包装尺寸(cm)" width="180">
            <template #default="{ row }">{{ formatSize(row) }}</template>
          </el-table-column>
          <el-table-column prop="units_per_carton" label="箱规" width="90" />
          <el-table-column label="操作" width="100" fixed="right">
            <template #default="{ row }"><el-button link type="primary" @click="editSku(row)">编辑</el-button></template>
          </el-table-column>
        </el-table>
        <el-pagination v-model:current-page="skuQuery.page" v-model:page-size="skuQuery.page_size" :total="skuTotal" layout="total, sizes, prev, pager, next" @current-change="loadSkus" @size-change="loadSkus" />
      </el-tab-pane>

      <el-tab-pane label="成本与预计利润" name="cost">
        <el-tabs v-model="costTab" class="cost-tabs">
          <el-tab-pane label="成本假设" name="assumption">
            <div class="toolbar"><el-button type="primary" :icon="Plus" @click="assumptionDialog.visible = true">新增成本假设</el-button></div>
            <el-table :data="costAssumptions" v-loading="loadingCosts" stripe><el-table-column prop="profile_name" label="名称" /><el-table-column prop="destination" label="目的地" /><el-table-column prop="transport_type" label="运输方式" /><el-table-column prop="freight_unit_rate" label="物流费率" /><el-table-column prop="storage_unit_rate" label="仓储费率" /><el-table-column prop="platform_fee_rate" label="平台费率" /><el-table-column prop="confidence_level" label="置信度" /></el-table>
          </el-tab-pane>
          <el-tab-pane label="物流账单" name="bill">
            <div class="toolbar"><el-button type="primary" :icon="Plus" @click="openBillCreate">新增物流账单</el-button></div>
            <el-table :data="logisticsBills" v-loading="loadingBills" stripe><el-table-column prop="bill_no" label="账单号" /><el-table-column prop="logistics_provider" label="物流公司" /><el-table-column prop="bill_date" label="账单日期" /><el-table-column prop="destination" label="目的地" /><el-table-column prop="total_amount" label="账单总额" /><el-table-column prop="status" label="状态" /><el-table-column label="操作" width="160"><template #default="{row}"><el-button link type="primary" @click="editBill(row)">录入 SKU 行</el-button><el-button v-if="row.status === 'draft'" link type="success" @click="confirmBill(row)">确认</el-button></template></el-table-column></el-table>
          </el-tab-pane>
          <el-tab-pane label="基准预计利润" name="profit">
            <div class="toolbar"><el-button type="primary" @click="openProfitDialog">新建基准估算</el-button></div>
            <el-table :data="profitEstimates" v-loading="loadingCosts" stripe><el-table-column prop="sku_id" label="SKU ID" /><el-table-column prop="assumption_version" label="成本版本" /><el-table-column prop="estimated_contribution_profit" label="预计贡献利润" /><el-table-column prop="estimated_margin_rate" label="预计利润率"><template #default="{ row }">{{ row.estimated_margin_rate == null ? '-' : `${(row.estimated_margin_rate * 100).toFixed(1)}%` }}</template></el-table-column><el-table-column prop="cost_completeness" label="完整度" /><el-table-column prop="confidence_level" label="置信度" /></el-table>
          </el-tab-pane>
        </el-tabs>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="spuDialog.visible" :title="spuDialog.editing ? '编辑 SPU' : '新增 SPU'" width="560px">
      <el-form :model="spuDialog.form" label-width="100px">
        <el-form-item label="SPU" required><el-input v-model="spuDialog.form.spu" :disabled="spuDialog.editing" /></el-form-item>
        <el-form-item label="名称" required><el-input v-model="spuDialog.form.spu_name" /></el-form-item>
        <el-form-item label="一级品类"><el-input v-model="spuDialog.form.category_l1" /></el-form-item>
        <el-form-item label="二级品类"><el-input v-model="spuDialog.form.category_l2" /></el-form-item>
        <el-form-item label="经营状态"><el-select v-model="spuDialog.form.biz_status"><el-option label="候选" value="candidate" /><el-option label="测试" value="testing" /><el-option label="主推" value="promoted" /><el-option label="淘汰" value="retired" /></el-select></el-form-item>
        <el-form-item label="负责人 ID"><el-input-number v-model="spuDialog.form.owner_user_id" :min="1" controls-position="right" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="spuDialog.visible = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveSpu">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="skuDialog.visible" :title="skuDialog.editing ? '编辑 SKU' : '新增 SKU'" width="620px">
      <el-form :model="skuDialog.form" label-width="120px">
        <el-form-item label="ERP SKU" required><el-input v-model="skuDialog.form.sku_key" :disabled="skuDialog.editing" /></el-form-item>
        <el-form-item label="名称"><el-input v-model="skuDialog.form.sku_name" /></el-form-item>
        <el-form-item label="规格"><el-input v-model="skuDialog.form.specification" /></el-form-item>
        <el-form-item label="重量(kg)"><el-input-number v-model="skuDialog.form.weight_kg" :min="0" :precision="3" /></el-form-item>
        <el-form-item label="包装尺寸(cm)"><div class="size-fields"><el-input-number v-model="skuDialog.form.package_length_cm" :min="0" /><el-input-number v-model="skuDialog.form.package_width_cm" :min="0" /><el-input-number v-model="skuDialog.form.package_height_cm" :min="0" /></div></el-form-item>
        <el-form-item label="箱规"><el-input-number v-model="skuDialog.form.units_per_carton" :min="1" /></el-form-item>
        <el-form-item label="默认采购成本"><el-input-number v-model="skuDialog.form.default_purchase_cost" :min="0" :precision="2" /></el-form-item>
        <el-form-item label="成本来源"><el-input v-model="skuDialog.form.purchase_cost_source" /></el-form-item>
        <el-form-item label="成本置信度"><el-select v-model="skuDialog.form.purchase_cost_confidence"><el-option label="低" value="low" /><el-option label="中" value="medium" /><el-option label="高" value="high" /></el-select></el-form-item>
      </el-form>
      <template #footer><el-button @click="skuDialog.visible = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveSku">保存</el-button></template>
    </el-dialog>

    <el-drawer v-model="bindingDrawer.visible" title="SKU 归属历史" size="520px">
      <el-descriptions :column="1" border><el-descriptions-item label="SPU">{{ bindingDrawer.spu }}</el-descriptions-item></el-descriptions>
      <el-table :data="bindingDrawer.rows" v-loading="bindingDrawer.loading" stripe>
        <el-table-column prop="sku_id" label="SKU ID" />
        <el-table-column prop="effective_from" label="生效日期" />
        <el-table-column prop="effective_to" label="失效日期" />
        <el-table-column prop="binding_status" label="状态" />
      </el-table>
    </el-drawer>

    <el-dialog v-model="assumptionDialog.visible" title="新增成本假设" width="600px"><el-form :model="assumptionDialog.form" label-width="110px"><el-form-item label="名称" required><el-input v-model="assumptionDialog.form.profile_name" /></el-form-item><el-form-item label="目的地"><el-input v-model="assumptionDialog.form.destination" /></el-form-item><el-form-item label="运输方式"><el-input v-model="assumptionDialog.form.transport_type" /></el-form-item><el-form-item label="物流费率"><el-input-number v-model="assumptionDialog.form.freight_unit_rate" :min="0" /></el-form-item><el-form-item label="仓储费率"><el-input-number v-model="assumptionDialog.form.storage_unit_rate" :min="0" /></el-form-item><el-form-item label="平台费率"><el-input-number v-model="assumptionDialog.form.platform_fee_rate" :min="0" :max="1" :step="0.01" /></el-form-item><el-form-item label="退货率"><el-input-number v-model="assumptionDialog.form.return_rate" :min="0" :max="1" :step="0.01" /></el-form-item><el-form-item label="货损率"><el-input-number v-model="assumptionDialog.form.damage_rate" :min="0" :max="1" :step="0.01" /></el-form-item><el-form-item label="生效日期"><el-date-picker v-model="assumptionDialog.form.effective_from" value-format="YYYY-MM-DD" type="date" /></el-form-item></el-form><template #footer><el-button @click="assumptionDialog.visible=false">取消</el-button><el-button type="primary" @click="saveAssumption">保存</el-button></template></el-dialog>

    <el-dialog v-model="billDialog.visible" :title="billDialog.editing ? '物流账单 SKU 行' : '新增物流账单'" width="900px"><template v-if="!billDialog.editing"><el-form :model="billDialog.form" label-width="100px"><el-form-item label="账单号"><el-input v-model="billDialog.form.bill_no" /></el-form-item><el-form-item label="物流公司"><el-input v-model="billDialog.form.logistics_provider" /></el-form-item><el-form-item label="账单日期"><el-date-picker v-model="billDialog.form.bill_date" value-format="YYYY-MM-DD" type="date" /></el-form-item><el-form-item label="目的地"><el-input v-model="billDialog.form.destination" /></el-form-item><el-form-item label="运输方式"><el-input v-model="billDialog.form.transport_type" /></el-form-item><el-form-item label="账单总额"><el-input-number v-model="billDialog.form.total_amount" :min="0" :precision="2" /></el-form-item></el-form></template><template v-else><el-alert title="每行直接对应一个 ERP SKU；重量和体积默认由 SKU 主数据计算，可填写本批实际总量覆盖。确认前所有 SKU 三段成本合计必须等于账单总额。" type="info" :closable="false" show-icon /><el-table :data="billDialog.lines" border><el-table-column label="SKU ID" width="120"><template #default="{row}"><el-input-number v-model="row.sku_id" :min="1" /></template></el-table-column><el-table-column label="发运数量"><template #default="{row}"><el-input-number v-model="row.shipped_qty" :min="0.001" /></template></el-table-column><el-table-column label="实际重量 kg"><template #default="{row}"><el-input-number v-model="row.actual_total_weight_kg" :min="0" /></template></el-table-column><el-table-column label="实际体积 m³"><template #default="{row}"><el-input-number v-model="row.actual_total_volume_cbm" :min="0" /></template></el-table-column><el-table-column label="头程"><template #default="{row}"><el-input-number v-model="row.headhaul_cost" :min="0" /></template></el-table-column><el-table-column label="操作费"><template #default="{row}"><el-input-number v-model="row.handling_cost" :min="0" /></template></el-table-column><el-table-column label="尾程"><template #default="{row}"><el-input-number v-model="row.last_mile_cost" :min="0" /></template></el-table-column></el-table><el-button class="add-line" @click="billDialog.lines.push(blankBillLine())">新增 SKU 行</el-button></template><template #footer><el-button @click="billDialog.visible=false">取消</el-button><el-button type="primary" @click="saveBill">保存</el-button></template></el-dialog>

    <el-dialog v-model="profitDialog.visible" title="基准预计利润" width="560px"><el-form :model="profitDialog.form" label-width="110px"><el-form-item label="SKU ID"><el-input-number v-model="profitDialog.form.sku_id" :min="1" /></el-form-item><el-form-item label="售价"><el-input-number v-model="profitDialog.form.selling_price" :min="0" :precision="2" /></el-form-item><el-form-item label="优惠券"><el-input-number v-model="profitDialog.form.coupon_amount" :min="0" :precision="2" /></el-form-item><el-form-item label="目的地"><el-input v-model="profitDialog.form.destination" /></el-form-item><el-form-item label="运输方式"><el-input v-model="profitDialog.form.transport_type" /></el-form-item><el-form-item label="成本版本"><el-input v-model="profitDialog.form.assumption_version" /></el-form-item></el-form><el-descriptions v-if="profitDialog.preview" :column="2" border><el-descriptions-item label="采购成本">{{ profitDialog.preview.purchase_cost }}</el-descriptions-item><el-descriptions-item label="物流成本">{{ profitDialog.preview.logistics_cost }}</el-descriptions-item><el-descriptions-item label="预计贡献利润">{{ profitDialog.preview.estimated_contribution_profit }}</el-descriptions-item><el-descriptions-item label="预计利润率">{{ (profitDialog.preview.estimated_margin_rate * 100).toFixed(1) }}%</el-descriptions-item></el-descriptions><template #footer><el-button @click="previewProfit">预览</el-button><el-button type="primary" @click="saveProfit">保存版本</el-button></template></el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import productCenterApi from '@/api/productCenter'

const activeTab = ref('spu')
const costTab = ref('assumption')
const saving = ref(false)
const loadingSpus = ref(false)
const loadingSkus = ref(false)
const loadingCosts = ref(false)
const loadingBills = ref(false)
const spus = ref([])
const skus = ref([])
const costAssumptions = ref([])
const profitEstimates = ref([])
const logisticsBills = ref([])
const spuTotal = ref(0)
const skuTotal = ref(0)
const spuQuery = reactive({ keyword: '', biz_status: '', page: 1, page_size: 20 })
const skuQuery = reactive({ keyword: '', page: 1, page_size: 20 })
const blankSpu = () => ({ spu: '', spu_name: '', category_l1: '', category_l2: '', biz_status: 'candidate', owner_user_id: null })
const blankSku = () => ({ sku_key: '', sku_name: '', specification: '', weight_kg: null, package_length_cm: null, package_width_cm: null, package_height_cm: null, units_per_carton: null, default_purchase_cost: null, purchase_cost_source: '', purchase_cost_confidence: 'low' })
const spuDialog = reactive({ visible: false, editing: false, form: blankSpu() })
const skuDialog = reactive({ visible: false, editing: false, form: blankSku() })
const bindingDrawer = reactive({ visible: false, loading: false, spu: '', rows: [] })
const assumptionDialog = reactive({ visible: false, form: { profile_name: '', destination: '', transport_type: '', freight_unit_rate: null, storage_unit_rate: null, platform_fee_rate: null, return_rate: null, damage_rate: null, effective_from: '' } })
const blankBillLine = () => ({ sku_id: null, shipped_qty: 1, actual_total_weight_kg: null, actual_total_volume_cbm: null, headhaul_cost: 0, handling_cost: 0, last_mile_cost: 0 })
const billDialog = reactive({ visible: false, editing: false, billId: null, form: { bill_no: '', logistics_provider: '', bill_date: '', destination: '', transport_type: '', total_amount: 0 }, lines: [] })
const profitDialog = reactive({ visible: false, form: { sku_id: null, selling_price: 0, coupon_amount: 0, destination: '', transport_type: '', assumption_version: '' }, preview: null })

const loadSpus = async () => { loadingSpus.value = true; try { const res = await productCenterApi.listSpus(spuQuery); spus.value = res.data || []; spuTotal.value = res.total || 0 } catch (e) { ElMessage.error(e.message || '加载 SPU 失败') } finally { loadingSpus.value = false } }
const loadSkus = async () => { loadingSkus.value = true; try { const res = await productCenterApi.listSkus(skuQuery); skus.value = res.data || []; skuTotal.value = res.total || 0 } catch (e) { ElMessage.error(e.message || '加载 SKU 失败') } finally { loadingSkus.value = false } }
const loadCosts = async () => { loadingCosts.value = true; try { costAssumptions.value = await productCenterApi.listCostAssumptions(); profitEstimates.value = await productCenterApi.listProfitEstimates({ limit: 20 }) } catch (e) { ElMessage.error(e.message || '加载成本和利润失败') } finally { loadingCosts.value = false } }
const loadBills = async () => { loadingBills.value = true; try { logisticsBills.value = await productCenterApi.listLogisticsBills() } catch (e) { ElMessage.error(e.message || '加载物流账单失败') } finally { loadingBills.value = false } }
const openSpuCreate = () => { spuDialog.editing = false; spuDialog.form = blankSpu(); spuDialog.visible = true }
const editSpu = row => { spuDialog.editing = true; spuDialog.form = { ...row }; spuDialog.visible = true }
const saveSpu = async () => { saving.value = true; try { if (spuDialog.editing) await productCenterApi.updateSpu(spuDialog.form.spu, spuDialog.form); else await productCenterApi.createSpu(spuDialog.form); spuDialog.visible = false; await loadSpus(); ElMessage.success('SPU 已保存') } catch (e) { ElMessage.error(e.message || '保存 SPU 失败') } finally { saving.value = false } }
const openSkuCreate = () => { skuDialog.editing = false; skuDialog.form = blankSku(); skuDialog.visible = true }
const editSku = row => { skuDialog.editing = true; skuDialog.form = { ...row }; skuDialog.visible = true }
const saveSku = async () => { saving.value = true; try { if (skuDialog.editing) await productCenterApi.updateSku(skuDialog.form.sku_id, skuDialog.form); else await productCenterApi.createSku(skuDialog.form); skuDialog.visible = false; await loadSkus(); ElMessage.success('SKU 已保存') } catch (e) { ElMessage.error(e.message || '保存 SKU 失败') } finally { saving.value = false } }
const showBindings = async row => { bindingDrawer.visible = true; bindingDrawer.spu = row.spu; bindingDrawer.loading = true; try { bindingDrawer.rows = await productCenterApi.listSpuSkus(row.spu) } catch (e) { ElMessage.error(e.message || '加载绑定历史失败') } finally { bindingDrawer.loading = false } }
const saveAssumption = async () => { try { await productCenterApi.createCostAssumption(assumptionDialog.form); assumptionDialog.visible = false; await loadCosts(); ElMessage.success('成本假设已保存') } catch (e) { ElMessage.error(e.message || '保存成本假设失败') } }
const openBillCreate = () => { billDialog.editing = false; billDialog.form = { bill_no: '', logistics_provider: '', bill_date: '', destination: '', transport_type: '', total_amount: 0, currency: 'CNY' }; billDialog.lines = []; billDialog.visible = true }
const editBill = async row => { try { const detail = await productCenterApi.getLogisticsBill(row.bill_id); billDialog.editing = true; billDialog.billId = row.bill_id; billDialog.form = detail; billDialog.lines = detail.lines?.length ? detail.lines : [blankBillLine()]; billDialog.visible = true } catch (e) { ElMessage.error(e.message || '加载账单失败') } }
const saveBill = async () => { try { if (!billDialog.editing) { const created = await productCenterApi.createLogisticsBill(billDialog.form); billDialog.editing = true; billDialog.billId = created.bill_id; billDialog.lines = [blankBillLine()]; ElMessage.success('账单草稿已创建，请录入 SKU 行') } else { await productCenterApi.saveLogisticsBillLines(billDialog.billId, { lines: billDialog.lines }); billDialog.visible = false; await loadBills(); ElMessage.success('账单 SKU 行已保存') } } catch (e) { ElMessage.error(e.message || '保存物流账单失败') } }
const confirmBill = async row => { try { await productCenterApi.confirmLogisticsBill(row.bill_id); await loadBills(); ElMessage.success('物流账单已确认') } catch (e) { ElMessage.error(e.message || '确认失败：请检查账单总额与 SKU 行三段费用合计') } }
const openProfitDialog = () => { profitDialog.form = { sku_id: null, selling_price: 0, coupon_amount: 0, destination: '', transport_type: '', assumption_version: '' }; profitDialog.preview = null; profitDialog.visible = true }
const previewProfit = async () => { try { profitDialog.preview = await productCenterApi.previewProfit(profitDialog.form) } catch (e) { ElMessage.error(e.message || '利润预览失败') } }
const saveProfit = async () => { try { await productCenterApi.saveBaselineProfit(profitDialog.form); profitDialog.visible = false; await loadCosts(); ElMessage.success('基准预计利润版本已保存') } catch (e) { ElMessage.error(e.message || '保存预计利润失败') } }
const formatSize = row => [row.package_length_cm, row.package_width_cm, row.package_height_cm].every(v => v != null) ? `${row.package_length_cm} × ${row.package_width_cm} × ${row.package_height_cm}` : '-'
onMounted(() => { loadSpus(); loadSkus(); loadCosts(); loadBills() })
</script>

<style scoped>
.page-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 18px; }
.page-subtitle { margin: 6px 0 0; color: var(--el-text-color-secondary); }
.toolbar { display: flex; gap: 12px; margin-bottom: 16px; }
.toolbar .el-input { max-width: 280px; }
.toolbar .el-select { width: 150px; }
.el-pagination { margin-top: 16px; justify-content: flex-end; }
.size-fields { display: flex; gap: 8px; }
.size-fields .el-input-number { width: 130px; }
</style>
