<template>
  <div class="account-management erp-page-container erp-page--admin">
    <PageHeader
      title="账号管理"
      subtitle="统一管理主账号ID、店铺账号ID、平台店铺ID、店铺别名与店铺数据域能力。"
      family="admin"
    />

    <!-- 统计卡片 -->
    <el-alert
      v-if="accountsStore.unmatchedShopAliases.length > 0"
      type="warning"
      :closable="false"
      class="erp-mb-lg"
      show-icon
    >
      <template #title>
        仍有 {{ accountsStore.unmatchedShopAliases.length }} 个未匹配店铺别名，认领到店铺账号ID后即可参与业务概览归属
      </template>
      <div class="unmatched-aliases">
        <div
          v-for="item in accountsStore.unmatchedShopAliases.slice(0, 8)"
          :key="`${item.platform}-${item.site}-${item.store_label_raw}`"
          class="unmatched-alias-item"
        >
          <span class="unmatched-alias-name">{{ item.platform }} / {{ item.site || '未标注站点' }} / {{ item.store_label_raw }}</span>
          <span class="unmatched-alias-meta">订单 {{ item.order_count }}，金额 {{ Number(item.paid_amount || 0).toFixed(2) }}</span>
        </div>
      </div>
    </el-alert>

    <el-row :gutter="20" class="stats-row">
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic title="总店铺账号数" :value="accountsStore.stats.total">
            <template #suffix>
              <span class="stat-unit">个</span>
            </template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic title="启用店铺账号" :value="accountsStore.stats.active">
            <template #suffix>
              <span class="stat-unit">个</span>
            </template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic title="停用店铺账号" :value="accountsStore.stats.inactive">
            <template #suffix>
              <span class="stat-unit">个</span>
            </template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic title="支持平台" :value="accountsStore.stats.platforms">
            <template #suffix>
              <span class="stat-unit">个</span>
            </template>
          </el-statistic>
        </el-card>
      </el-col>
    </el-row>

    <!-- 操作工具栏 -->
    <el-card class="toolbar-card">
      <el-row :gutter="10" class="erp-mb-md">
        <!-- 筛选 -->
        <el-col :span="4">
          <el-select v-model="filters.platform" placeholder="平台筛选" clearable @change="handleFilterChange">
            <el-option v-for="platform in platformOptions" :key="platform" :label="platform" :value="platform" />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-select v-model="filters.enabled" placeholder="状态筛选" clearable @change="handleFilterChange">
            <el-option label="活跃" :value="true" />
            <el-option label="禁用" :value="false" />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-switch
            v-model="filters.include_disabled"
            inline-prompt
            active-text="显示历史记录"
            inactive-text="隐藏历史记录"
            @change="handleFilterChange"
          />
        </el-col>
        <el-col :span="4">
          <el-select v-model="filters.shop_type" placeholder="店铺类型" clearable @change="handleFilterChange">
            <el-option label="本地店" value="local" />
            <el-option label="全球店" value="global" />
          </el-select>
        </el-col>
        <el-col :span="6">
          <el-input 
            v-model="filters.search" 
            placeholder="搜索店铺名、店铺账号ID或主账号ID"
            clearable
            @input="handleSearchChange"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </el-col>
      </el-row>

      <!-- 操作按钮 -->
      <el-row :gutter="10">
        <el-col :span="24">
          <el-button type="primary" @click="showCreateDialog = true">
            <el-icon><Plus /></el-icon>
            添加店铺账号
          </el-button>
          <el-button @click="showBatchDialog = true">
            <el-icon><Files /></el-icon>
            批量添加店铺账号
          </el-button>
          <el-button @click="handleRefresh" :loading="accountsStore.loading">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </el-col>
      </el-row>
      <el-row :gutter="10" class="erp-mt-md">
        <el-col :span="8">
          <el-select
            v-model="selectedMainAccountId"
            placeholder="选择主账号后探测当前店铺"
            clearable
            class="erp-w-full"
          >
            <el-option
              v-for="mainAccount in accountsStore.mainAccounts"
              :key="`${mainAccount.platform}-${mainAccount.main_account_id}`"
              :label="`${mainAccount.platform} / ${mainAccount.main_account_name || mainAccount.username || mainAccount.main_account_id} / ${mainAccount.main_account_id}`"
              :value="mainAccount.main_account_id"
            />
          </el-select>
        </el-col>
        <el-col :span="8">
          <el-button
            type="warning"
            @click="handleDiscoverCurrentShop"
            :loading="accountsStore.discoveryRunning"
            :disabled="!selectedMainAccountId"
          >
            探测当前店铺
          </el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- 账号列表 -->
    <div class="account-management-workspace">
      <el-card class="table-card navigator-card">
        <template #header>
          <div class="workspace-card-header">
            <div>
              <div class="workspace-card-title">主账号导航</div>
              <div class="workspace-card-subtitle">按平台查看主账号，并切换到当前工作区</div>
            </div>
            <el-tag type="info" effect="plain">{{ groupedMainAccounts.length }} 个平台分组</el-tag>
          </div>
        </template>

        <div v-if="groupedMainAccounts.length" class="account-management-navigator">
          <section
            v-for="platformGroup in groupedMainAccounts"
            :key="platformGroup.platform"
            class="navigator-platform-group"
          >
            <div class="navigator-platform-heading">
              <span>{{ platformGroup.platform }}</span>
              <el-tag size="small" effect="plain">{{ platformGroup.mainAccounts.length }} 个主账号</el-tag>
            </div>

            <button
              v-for="mainAccount in platformGroup.mainAccounts"
              :key="mainAccount.key"
              type="button"
              class="navigator-main-account"
              :class="{ 'is-active': selectedMainAccountGroupKey === mainAccount.key }"
              @click="selectMainAccountGroup(mainAccount.key)"
            >
              <div class="navigator-main-account__top">
                <span class="navigator-main-account__name">{{ mainAccount.mainAccountName }}</span>
                <span class="navigator-main-account__count">{{ mainAccount.shopCount }} 店</span>
              </div>
              <div class="navigator-main-account__meta">{{ mainAccount.mainAccountId }}</div>
              <div class="navigator-main-account__stats">
                <span>启用 {{ mainAccount.activeShopCount }}</span>
                <span>停用 {{ mainAccount.inactiveShopCount }}</span>
                <span v-if="mainAccount.missingShopIdCount > 0">缺少店铺ID {{ mainAccount.missingShopIdCount }}</span>
              </div>
            </button>
          </section>
        </div>

        <el-empty
          v-else
          description="暂时没有符合条件的主账号或店铺账号"
        />
      </el-card>

      <div class="account-management-detail">
        <el-card
          v-if="selectedMainAccountSnapshot"
          class="table-card current-main-account-summary"
        >
          <div class="current-main-account-summary__header">
            <div>
              <div class="workspace-card-title">
                {{ selectedMainAccountSnapshot.mainAccountName || selectedMainAccountSnapshot.mainAccountId }}
              </div>
              <div class="workspace-card-subtitle">
                {{ selectedMainAccountSnapshot.platform }} / {{ selectedMainAccountSnapshot.mainAccountId }}
                <span v-if="selectedMainAccountSnapshot.loginUsername">
                  / {{ selectedMainAccountSnapshot.loginUsername }}
                </span>
              </div>
            </div>

            <div class="current-main-account-summary__actions">
              <el-button type="primary" @click="showCreateDialog = true">
                <el-icon><Plus /></el-icon>
                添加店铺账号
              </el-button>
              <el-button @click="showBatchDialog = true">
                <el-icon><Files /></el-icon>
                批量添加
              </el-button>
              <el-button type="warning" @click="handleDiscoverSelectedMainAccount" :loading="accountsStore.discoveryRunning">
                探测当前店铺
              </el-button>
            </div>
          </div>

          <div class="current-main-account-summary__stats">
            <div class="summary-stat-card">
              <span class="summary-stat-card__label">店铺总数</span>
              <strong>{{ selectedMainAccountSnapshot.shopCount }}</strong>
            </div>
            <div class="summary-stat-card">
              <span class="summary-stat-card__label">启用店铺</span>
              <strong>{{ selectedMainAccountSnapshot.activeShopCount }}</strong>
            </div>
            <div class="summary-stat-card">
              <span class="summary-stat-card__label">停用店铺</span>
              <strong>{{ selectedMainAccountSnapshot.inactiveShopCount }}</strong>
            </div>
            <div class="summary-stat-card">
              <span class="summary-stat-card__label">缺少平台店铺ID</span>
              <strong>{{ selectedMainAccountSnapshot.missingShopIdCount }}</strong>
            </div>
          </div>
        </el-card>

        <el-card
          v-if="selectedMainAccountSnapshot"
          class="table-card current-main-account-shops"
        >
          <template #header>
            <div class="workspace-card-header">
              <div>
                <div class="workspace-card-title">当前主账号店铺列表</div>
                <div class="workspace-card-subtitle">仅显示当前主账号下的店铺账号，保留高密度编辑能力</div>
              </div>
              <el-tag effect="plain">{{ selectedMainAccountShops.length }} 个店铺账号</el-tag>
            </div>
          </template>

          <el-table
            :data="selectedMainAccountShops"
            v-loading="accountsStore.loading"
            class="erp-w-full"
            height="540"
          >
            <el-table-column prop="store_name" label="店铺名称" min-width="220" show-overflow-tooltip />
            <el-table-column prop="account_id" label="店铺账号ID" min-width="180" show-overflow-tooltip />
            <el-table-column prop="account_alias" label="店铺别名" min-width="160" show-overflow-tooltip>
              <template #default="{ row }">
                <span v-if="row.account_alias">{{ row.account_alias }}</span>
                <span v-else class="erp-text-muted">-</span>
              </template>
            </el-table-column>
            <el-table-column prop="shop_id" label="平台店铺ID" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">
                <span v-if="row.shop_id">{{ row.shop_id }}</span>
                <span v-else class="erp-text-muted">-</span>
              </template>
            </el-table-column>
            <el-table-column label="店铺类型" width="100">
              <template #default="{ row }">
                <el-tag v-if="row.shop_type === 'local'" type="success" size="small">本地店</el-tag>
                <el-tag v-else-if="row.shop_type === 'global'" type="warning" size="small">全球店</el-tag>
                <el-tag v-else type="info" size="small">未设置</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="shop_region" label="区域" width="100" />
            <el-table-column label="店铺数据域能力" min-width="220">
              <template #default="{ row }">
                <el-tooltip :content="getCapabilitiesText(row.capabilities)" placement="top">
                  <div class="capabilities-tags">
                    <el-tag
                      v-for="(enabled, domain) in row.capabilities"
                      :key="domain"
                      :type="enabled ? 'success' : 'info'"
                      size="small"
                      class="capability-tag"
                    >
                      {{ domainLabels[domain] || domain }}
                    </el-tag>
                  </div>
                </el-tooltip>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-switch
                  v-model="row.enabled"
                  @change="handleToggleEnabled(row)"
                  :loading="row._updating"
                />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="150" fixed="right">
              <template #default="{ row }">
                <el-button size="small" @click="handleEdit(row)">编辑</el-button>
                <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card v-else class="table-card current-main-account-empty">
          <el-empty description="暂时没有符合条件的主账号或店铺账号" />
        </el-card>
      </div>
    </div>

    <el-card v-if="false" class="table-card">
      <el-table 
        :data="accountsStore.accounts" 
        v-loading="accountsStore.loading"
        class="erp-w-full"
        height="500"
      >
        <el-table-column prop="platform" label="平台" width="100" />
        <el-table-column label="主账号名称" width="180" show-overflow-tooltip>
          <template #default="{ row }">
            {{ getMainAccountDisplayName(row) }}
          </template>
        </el-table-column>
        <el-table-column prop="parent_account" label="主账号ID" width="180" show-overflow-tooltip />
        <el-table-column prop="account_id" label="店铺账号ID" width="180" show-overflow-tooltip />
        <el-table-column prop="account_alias" label="店铺别名" width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.account_alias">{{ row.account_alias }}</span>
            <span v-else class="erp-text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="store_name" label="店铺名称" width="200" show-overflow-tooltip />
        
        <!-- ⭐ v4.18.1新增：店铺ID列 -->
        <el-table-column prop="shop_id" label="平台店铺ID" width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.shop_id">{{ row.shop_id }}</span>
            <span v-else class="erp-text-muted">-</span>
          </template>
        </el-table-column>
        
        <el-table-column label="店铺类型" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.shop_type === 'local'" type="success" size="small">本地店</el-tag>
            <el-tag v-else-if="row.shop_type === 'global'" type="warning" size="small">全球店</el-tag>
            <el-tag v-else type="info" size="small">未设置</el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="shop_region" label="店铺区域" width="100" />
        
        <el-table-column label="店铺数据域能力" width="200">
          <template #default="{ row }">
            <el-tooltip :content="getCapabilitiesText(row.capabilities)" placement="top">
              <div class="capabilities-tags">
                <el-tag 
                  v-for="(enabled, domain) in row.capabilities" 
                  :key="domain"
                  :type="enabled ? 'success' : 'info'"
                  size="small"
                  class="capability-tag"
                >
                  {{ domainLabels[domain] || domain }}
                </el-tag>
              </div>
            </el-tooltip>
          </template>
        </el-table-column>
        
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-switch 
              v-model="row.enabled" 
              @change="handleToggleEnabled(row)"
              :loading="row._updating"
            />
          </template>
        </el-table-column>
        
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="handleEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 创建/编辑对话框 -->
    <el-dialog 
      v-model="showCreateDialog" 
      :title="editingAccount ? '编辑店铺账号' : '添加店铺账号'"
      width="800px"
      :close-on-click-modal="false"
    >
      <el-form :model="accountForm" label-width="120px" :rules="formRules" ref="accountFormRef">
        <el-tabs v-model="activeTab">
          <!-- 基本信息 -->
          <el-tab-pane label="基本信息" name="basic">
            <el-form-item label="平台" prop="platform">
              <el-select v-model="accountForm.platform" placeholder="选择平台">
                <el-option label="Shopee" value="shopee" />
                <el-option label="TikTok" value="tiktok" />
                <el-option label="Amazon" value="amazon" />
                <el-option label="妙手ERP" value="miaoshou" />
              </el-select>
            </el-form-item>
            
            <el-form-item label="店铺账号ID" prop="account_id">
              <el-input v-model="accountForm.account_id" placeholder="唯一标识，如：shopee_sg_local_001" />
              <div class="form-tip">店铺级业务唯一标识，创建后不可修改</div>
            </el-form-item>
            
            <el-form-item label="店铺别名">
              <el-input v-model="accountForm.account_alias" placeholder="用于关联导出数据中的自定义名称（如：miaoshou ERP的订单数据）" />
              <div class="form-tip">可选，作为主别名写入店铺别名映射，后续用于原始数据归属</div>
            </el-form-item>
            
            <el-form-item label="店铺名称" prop="store_name">
              <el-input v-model="accountForm.store_name" placeholder="如：HongXi Singapore Local" />
            </el-form-item>
            
            <el-form-item label="主账号ID">
              <el-input v-model="accountForm.parent_account" placeholder="多店铺共用时填写，如：hongxikeji:main" />
              <div class="form-tip">用于共享登录身份、持久会话和浏览器 profile</div>
            </el-form-item>
            
            <el-form-item label="主账号名称">
              <el-input v-model="accountForm.main_account_name" placeholder="如：Shopee 新加坡主体" />
              <div class="form-tip">用于页面显示和人工识别，不影响系统内部主账号ID</div>
            </el-form-item>
            
            <el-form-item label="店铺类型">
              <el-radio-group v-model="accountForm.shop_type" @change="handleShopTypeChange">
                <el-radio label="local">本地店铺</el-radio>
                <el-radio label="global">全球店铺</el-radio>
              </el-radio-group>
            </el-form-item>
            
            <el-form-item label="店铺区域">
              <el-input v-model="accountForm.shop_region" placeholder="如：SG, MY, GLOBAL" />
              <div class="form-tip">新加坡: SG, 马来西亚: MY, 全球: GLOBAL</div>
            </el-form-item>
            
            <!-- ⭐ v4.18.1新增：店铺ID字段 -->
            <el-form-item label="平台店铺ID">
              <el-input v-model="accountForm.shop_id" placeholder="用于关联数据同步中的shop_id" />
              <div class="form-tip">优先由系统在首次登录 / 切店 / 采集成功后自动回填，无法识别时再人工补录</div>
            </el-form-item>
          </el-tab-pane>
          
          <!-- 登录信息 -->
          <el-tab-pane label="主账号登录信息" name="login">
            <el-form-item label="登录用户名" prop="username">
              <el-input v-model="accountForm.username" placeholder="登录用户名" />
            </el-form-item>
            
            <el-form-item label="密码" prop="password">
              <el-input 
                v-model="accountForm.password" 
                type="password" 
                placeholder="登录密码（加密存储）"
                show-password 
              />
              <div class="form-tip">密码将被加密存储，更新时留空表示不修改</div>
            </el-form-item>
            
            <el-form-item label="标准登录入口">
              <el-input v-model="accountForm.login_url" placeholder="系统自动生成" disabled />
            </el-form-item>
            
            <el-alert type="info" :closable="false">
              Only main-account login fields are persisted here. Legacy contact and profile fields have been retired.
            </el-alert>
          </el-tab-pane>
          
          <!-- 能力配置 -->
          <el-tab-pane label="店铺数据域能力" name="capabilities">
            <div class="capabilities-grid">
              <el-checkbox v-model="accountForm.capabilities.orders">
                <div class="capability-item">
                  <el-icon><ShoppingCart /></el-icon>
                  <span>订单数据</span>
                </div>
              </el-checkbox>
              <el-checkbox v-model="accountForm.capabilities.products">
                <div class="capability-item">
                  <el-icon><Box /></el-icon>
                  <span>商品数据</span>
                </div>
              </el-checkbox>
              <el-checkbox v-model="accountForm.capabilities.services">
                <div class="capability-item">
                  <el-icon><Service /></el-icon>
                  <span>客服数据</span>
                </div>
              </el-checkbox>
              <el-checkbox v-model="accountForm.capabilities.analytics">
                <div class="capability-item">
                  <el-icon><TrendCharts /></el-icon>
                  <span>流量数据</span>
                </div>
              </el-checkbox>
              <el-checkbox v-model="accountForm.capabilities.finance">
                <div class="capability-item">
                  <el-icon><Money /></el-icon>
                  <span>财务数据</span>
                </div>
              </el-checkbox>
              <el-checkbox v-model="accountForm.capabilities.inventory">
                <div class="capability-item">
                  <el-icon><Grid /></el-icon>
                  <span>库存数据</span>
                </div>
              </el-checkbox>
            </div>
            
            <el-alert 
              title="提示" 
              type="info" 
              :closable="false"
              class="erp-mt-lg"
            >
              根据店铺类型自动配置：
              <ul>
                <li>本地店铺：通常支持所有数据域</li>
                <li>全球店铺：通常不支持客服数据</li>
              </ul>
            </el-alert>
          </el-tab-pane>
        </el-tabs>
      </el-form>
      
      <template #footer>
        <el-button @click="handleCancelEdit">取消</el-button>
        <el-button type="primary" @click="handleSaveAccount" :loading="accountsStore.loading">保存</el-button>
      </template>
    </el-dialog>

    <!-- 批量添加店铺对话框 -->
    <el-dialog 
      v-model="showBatchDialog" 
      title="批量添加店铺账号"
      width="700px"
      :close-on-click-modal="false"
    >
      <el-form :model="batchForm" label-width="120px">
        <el-form-item label="主账号ID" required>
          <el-input v-model="batchForm.parent_account" placeholder="如：hongxikeji:main" />
        </el-form-item>
        
        <el-form-item label="平台" required>
          <el-select v-model="batchForm.platform">
            <el-option label="Shopee" value="shopee" />
            <el-option label="TikTok" value="tiktok" />
          </el-select>
        </el-form-item>
        
        <el-form-item label="用户名" required>
          <el-input v-model="batchForm.username" placeholder="共用的登录用户名" />
        </el-form-item>
        
        <el-form-item label="密码" required>
          <el-input v-model="batchForm.password" type="password" placeholder="共用的登录密码" show-password />
        </el-form-item>
        
        <el-form-item label="店铺列表">
          <el-table :data="batchForm.shops" class="erp-w-full">
            <el-table-column label="店铺名称">
              <template #default="{ row }">
                <el-input v-model="row.store_name" placeholder="店铺名称" size="small" />
              </template>
            </el-table-column>
            <el-table-column label="店铺别名" width="150">
              <template #default="{ row }">
                <el-input v-model="row.account_alias" placeholder="可选" size="small" />
              </template>
            </el-table-column>
            <el-table-column label="类型" width="120">
              <template #default="{ row }">
                <el-select v-model="row.shop_type" size="small">
                  <el-option label="本地" value="local" />
                  <el-option label="全球" value="global" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="区域" width="100">
              <template #default="{ row }">
                <el-input v-model="row.shop_region" size="small" placeholder="SG/MY" />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="80">
              <template #default="{ $index }">
                <el-button size="small" type="danger" @click="removeShop($index)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-button @click="addShop" class="erp-mt-sm" size="small">
            <el-icon><Plus /></el-icon>
            添加店铺
          </el-button>
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="showBatchDialog = false">取消</el-button>
        <el-button type="primary" @click="handleBatchCreate" :loading="accountsStore.loading">批量创建</el-button>
      </template>
    </el-dialog>
    <el-dialog
      v-model="showDiscoveryDialog"
      title="当前店铺探测结果"
      width="720px"
      :close-on-click-modal="false"
    >
      <el-alert
        v-if="accountsStore.currentDiscoveryError"
        type="error"
        :title="accountsStore.currentDiscoveryError"
        :closable="false"
        show-icon
        class="erp-mb-md"
      />
      <template v-if="accountsStore.currentDiscoveryResult">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="主账号ID">{{ accountsStore.currentDiscoveryResult.main_account_id }}</el-descriptions-item>
          <el-descriptions-item label="平台">{{ accountsStore.currentDiscoveryResult.platform }}</el-descriptions-item>
          <el-descriptions-item label="匹配状态">{{ accountsStore.currentDiscoveryResult.match?.status || '-' }}</el-descriptions-item>
          <el-descriptions-item label="店铺名">{{ accountsStore.currentDiscoveryResult.discovery?.detected_store_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="平台店铺ID">{{ accountsStore.currentDiscoveryResult.discovery?.detected_platform_shop_id || '-' }}</el-descriptions-item>
          <el-descriptions-item label="区域">{{ accountsStore.currentDiscoveryResult.discovery?.detected_region || '-' }}</el-descriptions-item>
          <el-descriptions-item label="URL">{{ accountsStore.currentDiscoveryResult.discovery?.current_url || '-' }}</el-descriptions-item>
        </el-descriptions>
        <div class="erp-mt-lg" v-if="accountsStore.currentDiscoveryResult.match?.status === 'no_match'">
          <el-button
            type="primary"
            @click="handleCreateShopAccountFromDiscovery"
            :loading="accountsStore.discoveryRunning"
          >
            基于探测结果创建店铺账号
          </el-button>
        </div>
      </template>
      <template #footer>
        <el-button @click="showDiscoveryDialog = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, watch } from 'vue'
import { useAccountsStore } from '@/stores/accounts'
import { ElMessageBox, ElMessage } from 'element-plus'
import { 
  Search, Plus, Download, Refresh, Files,
  ShoppingCart, Box, Service, TrendCharts, Money, Grid
} from '@element-plus/icons-vue'
import PageHeader from '@/components/common/PageHeader.vue'
import {
  buildAccountManagementGroups,
  buildMainAccountSnapshot,
  findMainAccountGroup,
  resolveSelectedMainAccountKey,
} from '@/utils/accountManagementView'

const accountsStore = useAccountsStore()

// 数据域标签映射
const domainLabels = {
  orders: '订单',
  products: '商品',
  services: '客服',
  analytics: '流量',
  finance: '财务',
  inventory: '库存'
}

// 筛选条件
const filters = reactive({
  platform: null,
  enabled: null,
  include_disabled: false,
  shop_type: null,
  search: ''
})

// 平台选项
const platformOptions = computed(() => accountsStore.platformList)

// 对话框状态
const showCreateDialog = ref(false)
const showBatchDialog = ref(false)
const showDiscoveryDialog = ref(false)
const activeTab = ref('basic')
const editingAccount = ref(null)
const selectedMainAccountId = ref('')
const selectedMainAccountGroupKey = ref('')

// 表单引用
const accountFormRef = ref(null)

// 账号表单
const accountForm = reactive({
  account_id: '',
  parent_account: '',
  main_account_name: '',
  platform: 'shopee',
  account_alias: '',
  store_name: '',
  shop_type: 'local',
  shop_region: '',
  shop_id: '',  // ⭐ v4.18.1新增
  username: '',
  password: '',
  login_url: '',
  capabilities: {
    orders: true,
    products: true,
    services: true,
    analytics: true,
    finance: true,
    inventory: true
  },
  enabled: true,
  notes: ''
})

// 表单验证规则
// 表单验证规则（动态：编辑时密码可选，创建时必填）
const formRules = computed(() => ({
  account_id: [{ required: true, message: '请输入账号ID', trigger: 'blur' }],
  parent_account: [{ required: true, message: '请输入主账号ID', trigger: 'blur' }],
  platform: [{ required: true, message: '请选择平台', trigger: 'change' }],
  store_name: [{ required: true, message: '请输入店铺名称', trigger: 'blur' }],
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: editingAccount.value 
    ? [] // 编辑时：密码可选（留空表示不修改）
    : [{ required: true, message: '请输入密码', trigger: 'blur' }] // 创建时：密码必填
}))

// 批量表单
const batchForm = reactive({
  parent_account: '',
  main_account_name: '',
  platform: 'shopee',
  username: '',
  password: '',
  shops: [
    { store_name: '', shop_type: 'local', shop_region: 'SG' }
  ]
})

const groupedMainAccounts = computed(() => {
  return buildAccountManagementGroups({
    accounts: accountsStore.accounts || [],
    mainAccounts: accountsStore.mainAccounts || [],
  })
})

const selectedMainAccountGroup = computed(() => {
  return findMainAccountGroup(groupedMainAccounts.value, selectedMainAccountGroupKey.value)
})

const selectedMainAccountSnapshot = computed(() => {
  return buildMainAccountSnapshot(selectedMainAccountGroup.value)
})

const selectedMainAccountShops = computed(() => {
  return selectedMainAccountSnapshot.value?.shops || []
})

watch(
  groupedMainAccounts,
  (groups) => {
    selectedMainAccountGroupKey.value = resolveSelectedMainAccountKey(
      groups,
      selectedMainAccountGroupKey.value
    )
  },
  { immediate: true }
)

// ==================== 方法 ====================

/**
 * 初始化
 * ⭐ v4.19.0修复：首次加载显示loading，后续支持后台刷新
 */
onMounted(async () => {
  // 首次加载显示loading
  await accountsStore.loadAccounts({}, true)
  await accountsStore.loadStats(false) // 统计数据后台加载，不显示loading
  await accountsStore.loadUnmatchedShopAliases()
})

/**
 * 筛选变更
 */
function handleFilterChange() {
  accountsStore.setFilters(filters)
  accountsStore.loadAccounts()
}

/**
 * 搜索变更（防抖）
 */
let searchTimeout = null
function handleSearchChange() {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    handleFilterChange()
  }, 500)
}

/**
 * 刷新
 * ⭐ v4.19.0修复：刷新时显示loading
 */
async function handleRefresh() {
  await accountsStore.loadAccounts({}, true)
  await accountsStore.loadStats(false) // 统计数据后台加载，不显示loading
  ElMessage.success('刷新成功')
}

function resolveMainAccountRecord(mainAccountId) {
  return (accountsStore.mainAccounts || []).find((item) => item.main_account_id === mainAccountId) || null
}

function getMainAccountDisplayName(account) {
  const mainAccount = resolveMainAccountRecord(account.parent_account)
  return (
    mainAccount?.main_account_name
    || mainAccount?.username
    || account.parent_account
    || '-'
  )
}

function selectMainAccountGroup(key) {
  selectedMainAccountGroupKey.value = key
}

async function handleDiscoverSelectedMainAccount() {
  if (!selectedMainAccountSnapshot.value) {
    ElMessage.warning('请先选择主账号')
    return
  }

  selectedMainAccountId.value = selectedMainAccountSnapshot.value.mainAccountId
  await handleDiscoverCurrentShop()
}

async function handleDiscoverCurrentShop() {
  if (!selectedMainAccountId.value) {
    ElMessage.warning('请先选择主账号')
    return
  }

  try {
    await accountsStore.runCurrentShopDiscovery(selectedMainAccountId.value, {
      mode: 'current_only',
      reuse_session: true,
      capture_evidence: true
    })
  } catch (error) {
    console.error('店铺探测失败:', error)
  } finally {
    showDiscoveryDialog.value = true
  }
}

async function handleCreateShopAccountFromDiscovery() {
  const result = accountsStore.currentDiscoveryResult
  if (!result) return

  const discovery = (accountsStore.pendingPlatformShopDiscoveries || []).find((item) => {
    return item.main_account_id === result.main_account_id
      && item.detected_platform_shop_id === result.discovery?.detected_platform_shop_id
  })

  if (!discovery?.id) {
    ElMessage.warning('当前探测结果未找到可创建的 discovery 记录')
    return
  }

  const storeName = result.discovery?.detected_store_name || 'discovered_shop'
  const region = String(result.discovery?.detected_region || 'unknown').toLowerCase()
  const shopAccountId = `${result.platform}_${region}_${String(storeName).replace(/\s+/g, '_').toLowerCase()}`

  try {
    await accountsStore.createShopAccountFromDiscovery(discovery.id, {
      shop_account_id: shopAccountId,
      store_name: storeName,
      shop_region: result.discovery?.detected_region || null,
      shop_type: 'local',
      notes: 'created from current shop discovery'
    })
    ElMessage.success('已基于探测结果创建店铺账号')
    showDiscoveryDialog.value = false
  } catch (error) {
    console.error('基于探测结果创建店铺账号失败:', error)
  }
}

/**
 * 导入
 */
/**
 * 编辑账号
 */
function handleEdit(account) {
  editingAccount.value = account
  const mainAccount = resolveMainAccountRecord(account.parent_account)
  Object.assign(accountForm, {
    account_id: account.account_id,
    parent_account: account.parent_account || '',
    main_account_name: mainAccount?.main_account_name || '',
    platform: account.platform,
    account_alias: account.account_alias || '',
    store_name: account.store_name,
    shop_type: account.shop_type || 'local',
    shop_region: account.shop_region || '',
    shop_id: account.shop_id || '',  // ⭐ v4.18.1新增
    username: mainAccount?.username || account.username || '',
    password: '', // 不显示密码
    login_url: mainAccount?.login_url || account.login_url || '',
    capabilities: { ...account.capabilities },
    enabled: account.enabled,
    notes: account.notes || ''
  })
  showCreateDialog.value = true
}

/**
 * 保存账号
 */
async function handleSaveAccount() {
  try {
    await accountFormRef.value.validate()
    
    const data = { ...accountForm }
    
    if (editingAccount.value) {
      // 更新（如果密码为空，不发送）
      if (!data.password) {
        delete data.password
      }
      await accountsStore.updateAccount(editingAccount.value.account_id, data)
    } else {
      // 创建
      await accountsStore.createAccount(data)
    }
    
    handleCancelEdit()
  } catch (error) {
    console.error('保存失败:', error)
  }
}

/**
 * 取消编辑
 */
function handleCancelEdit() {
  showCreateDialog.value = false
  editingAccount.value = null
  resetForm()
}

/**
 * 重置表单
 */
function resetForm() {
  Object.assign(accountForm, {
    account_id: '',
    parent_account: '',
    main_account_name: '',
    platform: 'shopee',
    account_alias: '',
    store_name: '',
    shop_type: 'local',
    shop_region: '',
    shop_id: '',  // ⭐ v4.18.1新增
    username: '',
    password: '',
    login_url: '',
    capabilities: {
      orders: true,
      products: true,
      services: true,
      analytics: true,
      finance: true,
      inventory: true
    },
    enabled: true,
    notes: ''
  })
  activeTab.value = 'basic'
}

/**
 * 店铺类型变更
 */
function handleShopTypeChange(value) {
  // 全球店不支持客服数据
  if (value === 'global') {
    accountForm.capabilities.services = false
  } else {
    accountForm.capabilities.services = true
  }
}

/**
 * 删除账号
 */
async function handleDelete(account) {
  try {
    await ElMessageBox.confirm(
      `确定要删除账号 "${account.store_name}" 吗？此操作不可恢复。`,
      '确认删除',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    await accountsStore.deleteAccount(account.account_id)
  } catch (error) {
    // 用户取消
  }
}

/**
 * 切换启用状态
 */
async function handleToggleEnabled(account) {
  account._updating = true
  try {
    await accountsStore.updateAccount(account.account_id, {
      enabled: account.enabled
    })
  } catch (error) {
    // 回滚
    account.enabled = !account.enabled
  } finally {
    account._updating = false
  }
}

/**
 * 添加店铺
 */
function addShop() {
  batchForm.shops.push({
    store_name: '',
    account_alias: '',
    shop_type: 'local',
    shop_region: ''
  })
}

/**
 * 删除店铺
 */
function removeShop(index) {
  batchForm.shops.splice(index, 1)
}

/**
 * 批量创建
 */
async function handleBatchCreate() {
  if (!batchForm.parent_account || !batchForm.username || !batchForm.password) {
    ElMessage.warning('请填写必填项')
    return
  }
  
  if (batchForm.shops.length === 0) {
    ElMessage.warning('请至少添加一个店铺')
    return
  }
  
  try {
    await accountsStore.batchCreate(batchForm)
    showBatchDialog.value = false
    // 重置表单
    Object.assign(batchForm, {
      parent_account: '',
      main_account_name: '',
      platform: 'shopee',
      username: '',
      password: '',
      shops: [{ store_name: '', shop_type: 'local', shop_region: 'SG' }]
    })
  } catch (error) {
    console.error('批量创建失败:', error)
  }
}

/**
 * 获取能力配置文本
 */
function getCapabilitiesText(capabilities) {
  const enabled = Object.entries(capabilities)
    .filter(([, value]) => value)
    .map(([key]) => domainLabels[key] || key)
  return `支持：${enabled.join('、')}`
}
</script>

<style scoped>
.account-management {
  min-height: calc(100vh - var(--header-height));
}

.page-description {
  color: #909399;
  margin-bottom: 20px;
}

.stats-row {
  margin-bottom: 20px;
}

.stat-unit {
  color: #909399;
  font-size: 14px;
  margin-left: 5px;
}

.toolbar-card,
.table-card {
  margin-bottom: 20px;
}

.account-management-workspace {
  display: grid;
  grid-template-columns: minmax(280px, 340px) minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}

.account-management-detail {
  min-width: 0;
}

.workspace-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.workspace-card-title {
  font-size: 16px;
  font-weight: 700;
  color: #303133;
}

.workspace-card-subtitle {
  margin-top: 4px;
  font-size: 13px;
  color: #909399;
}

.account-management-navigator {
  display: flex;
  flex-direction: column;
  gap: 18px;
  max-height: 920px;
  overflow-y: auto;
}

.navigator-platform-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.navigator-platform-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
  font-weight: 700;
  color: #606266;
}

.navigator-main-account {
  width: 100%;
  border: 1px solid #e4e7ed;
  border-radius: 12px;
  background: #fff;
  padding: 14px 14px 12px;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.navigator-main-account:hover {
  border-color: #c6e2ff;
  box-shadow: 0 8px 20px rgba(31, 35, 41, 0.08);
  transform: translateY(-1px);
}

.navigator-main-account.is-active {
  border-color: #409eff;
  background: linear-gradient(180deg, #f5f9ff 0%, #ffffff 100%);
  box-shadow: 0 10px 26px rgba(64, 158, 255, 0.14);
}

.navigator-main-account__top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.navigator-main-account__name {
  font-size: 14px;
  font-weight: 700;
  color: #303133;
}

.navigator-main-account__count {
  font-size: 12px;
  color: #606266;
  white-space: nowrap;
}

.navigator-main-account__meta {
  margin-top: 6px;
  font-size: 12px;
  color: #909399;
  word-break: break-all;
}

.navigator-main-account__stats {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  font-size: 12px;
  color: #606266;
}

.current-main-account-summary__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.current-main-account-summary__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 10px;
}

.current-main-account-summary__stats {
  margin-top: 18px;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.summary-stat-card {
  border: 1px solid #ebeef5;
  border-radius: 12px;
  background: #fafafa;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.summary-stat-card__label {
  font-size: 12px;
  color: #909399;
}

.summary-stat-card strong {
  font-size: 22px;
  line-height: 1;
  color: #303133;
}

.current-main-account-empty :deep(.el-empty) {
  padding: 48px 0;
}

.unmatched-aliases {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.unmatched-alias-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
}

.unmatched-alias-name {
  font-weight: 600;
}

.unmatched-alias-meta {
  color: #909399;
}

.capabilities-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.capability-tag {
  margin: 2px 0;
}

.form-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 5px;
}

.capabilities-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 15px;
}

.capability-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.capability-item .el-icon {
  font-size: 18px;
}

@media (max-width: 1280px) {
  .account-management-workspace {
    grid-template-columns: 1fr;
  }

  .account-management-navigator {
    max-height: none;
  }
}

@media (max-width: 900px) {
  .current-main-account-summary__header {
    flex-direction: column;
  }

  .current-main-account-summary__actions {
    justify-content: flex-start;
  }

  .current-main-account-summary__stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
