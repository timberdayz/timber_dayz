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
        <el-alert title="成本和预计利润将基于 ERP 财务域、物流账单和成本假设版本计算。当前页面先提供统一入口，原始账单仍通过数据同步模块导入。" type="info" :closable="false" show-icon />
        <el-row :gutter="16" class="cost-grid" v-loading="loadingCosts">
          <el-col :span="12"><el-card shadow="never"><template #header>成本假设版本</template><el-table :data="costAssumptions" size="small"><el-table-column prop="profile_name" label="名称" /><el-table-column prop="destination" label="目的地" /><el-table-column prop="transport_type" label="运输方式" /><el-table-column prop="confidence_level" label="置信度" /></el-table></el-card></el-col>
          <el-col :span="12"><el-card shadow="never"><template #header>最近预计利润</template><el-table :data="profitEstimates" size="small"><el-table-column prop="sku_id" label="SKU ID" /><el-table-column prop="scenario" label="情景" /><el-table-column prop="estimated_contribution_profit" label="预计贡献利润" /><el-table-column prop="estimated_margin_rate" label="预计利润率"><template #default="{ row }">{{ row.estimated_margin_rate == null ? '-' : `${(row.estimated_margin_rate * 100).toFixed(1)}%` }}</template></el-table-column></el-table></el-card></el-col>
        </el-row>
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
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import productCenterApi from '@/api/productCenter'

const activeTab = ref('spu')
const saving = ref(false)
const loadingSpus = ref(false)
const loadingSkus = ref(false)
const loadingCosts = ref(false)
const spus = ref([])
const skus = ref([])
const costAssumptions = ref([])
const profitEstimates = ref([])
const spuTotal = ref(0)
const skuTotal = ref(0)
const spuQuery = reactive({ keyword: '', biz_status: '', page: 1, page_size: 20 })
const skuQuery = reactive({ keyword: '', page: 1, page_size: 20 })
const blankSpu = () => ({ spu: '', spu_name: '', category_l1: '', category_l2: '', biz_status: 'candidate', owner_user_id: null })
const blankSku = () => ({ sku_key: '', sku_name: '', specification: '', weight_kg: null, package_length_cm: null, package_width_cm: null, package_height_cm: null, units_per_carton: null })
const spuDialog = reactive({ visible: false, editing: false, form: blankSpu() })
const skuDialog = reactive({ visible: false, editing: false, form: blankSku() })
const bindingDrawer = reactive({ visible: false, loading: false, spu: '', rows: [] })

const loadSpus = async () => { loadingSpus.value = true; try { const res = await productCenterApi.listSpus(spuQuery); spus.value = res.data || []; spuTotal.value = res.total || 0 } catch (e) { ElMessage.error(e.message || '加载 SPU 失败') } finally { loadingSpus.value = false } }
const loadSkus = async () => { loadingSkus.value = true; try { const res = await productCenterApi.listSkus(skuQuery); skus.value = res.data || []; skuTotal.value = res.total || 0 } catch (e) { ElMessage.error(e.message || '加载 SKU 失败') } finally { loadingSkus.value = false } }
const loadCosts = async () => { loadingCosts.value = true; try { costAssumptions.value = await productCenterApi.listCostAssumptions(); profitEstimates.value = await productCenterApi.listProfitEstimates({ limit: 20 }) } catch (e) { ElMessage.error(e.message || '加载成本和利润失败') } finally { loadingCosts.value = false } }
const openSpuCreate = () => { spuDialog.editing = false; spuDialog.form = blankSpu(); spuDialog.visible = true }
const editSpu = row => { spuDialog.editing = true; spuDialog.form = { ...row }; spuDialog.visible = true }
const saveSpu = async () => { saving.value = true; try { if (spuDialog.editing) await productCenterApi.updateSpu(spuDialog.form.spu, spuDialog.form); else await productCenterApi.createSpu(spuDialog.form); spuDialog.visible = false; await loadSpus(); ElMessage.success('SPU 已保存') } catch (e) { ElMessage.error(e.message || '保存 SPU 失败') } finally { saving.value = false } }
const openSkuCreate = () => { skuDialog.editing = false; skuDialog.form = blankSku(); skuDialog.visible = true }
const editSku = row => { skuDialog.editing = true; skuDialog.form = { ...row }; skuDialog.visible = true }
const saveSku = async () => { saving.value = true; try { if (skuDialog.editing) await productCenterApi.updateSku(skuDialog.form.sku_id, skuDialog.form); else await productCenterApi.createSku(skuDialog.form); skuDialog.visible = false; await loadSkus(); ElMessage.success('SKU 已保存') } catch (e) { ElMessage.error(e.message || '保存 SKU 失败') } finally { saving.value = false } }
const showBindings = async row => { bindingDrawer.visible = true; bindingDrawer.spu = row.spu; bindingDrawer.loading = true; try { bindingDrawer.rows = await productCenterApi.listSpuSkus(row.spu) } catch (e) { ElMessage.error(e.message || '加载绑定历史失败') } finally { bindingDrawer.loading = false } }
const formatSize = row => [row.package_length_cm, row.package_width_cm, row.package_height_cm].every(v => v != null) ? `${row.package_length_cm} × ${row.package_width_cm} × ${row.package_height_cm}` : '-'
onMounted(() => { loadSpus(); loadSkus(); loadCosts() })
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
