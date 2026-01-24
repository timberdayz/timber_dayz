<template>
  <div class="component-recorder">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1>组件录制工具</h1>
      <p class="subtitle">可视化录制和编辑数据采集组件</p>
    </div>

    <!-- 主要内容区域 -->
    <div class="recorder-content">
      <!-- 左侧：录制控制 -->
      <el-card class="recorder-panel" shadow="hover">
        <template #header>
          <div class="card-header">
            <span class="card-title">录制控制</span>
            <el-tag :type="recordingStatus.type">{{
              recordingStatus.text
            }}</el-tag>
          </div>
        </template>

        <!-- 平台和组件选择 -->
        <el-form :model="recorderForm" label-width="100px" size="default">
          <el-form-item label="平台">
            <el-select v-model="recorderForm.platform" placeholder="选择平台">
              <el-option label="Shopee" value="shopee" />
              <el-option label="TikTok Shop" value="tiktok" />
              <el-option label="妙手ERP" value="miaoshou" />
              <el-option label="Amazon" value="amazon" />
            </el-select>
          </el-form-item>

          <el-form-item label="组件类型">
            <el-select
              v-model="recorderForm.componentType"
              placeholder="选择类型"
            >
              <el-option label="登录 (login)" value="login" />
              <el-option label="店铺切换 (shop_switch)" value="shop_switch" />
              <el-option label="导航 (navigation)" value="navigation" />
              <el-option label="导出 (export)" value="export" />
              <el-option label="日期选择 (date_picker)" value="date_picker" />
              <el-option label="筛选器 (filters)" value="filters" />
            </el-select>
          </el-form-item>

          <!-- 数据域选择（仅当组件类型为 export 时显示） -->
          <el-form-item
            v-if="recorderForm.componentType === 'export'"
            label="数据域"
          >
            <el-select
              v-model="recorderForm.dataDomain"
              placeholder="选择数据域"
              @change="onDataDomainChange"
            >
              <el-option label="订单 (orders)" value="orders" />
              <el-option label="产品 (products)" value="products" />
              <el-option label="流量分析 (analytics)" value="analytics" />
              <el-option label="财务 (finance)" value="finance" />
              <el-option label="服务 (services)" value="services" />
              <el-option label="库存 (inventory)" value="inventory" />
            </el-select>
            <div style="font-size: 12px; color: #909399; margin-top: 4px">
              不同数据域会生成不同的导出组件
            </div>
          </el-form-item>

          <!-- 服务子域选择（仅当 export + services 时显示） -->
          <el-form-item
            v-if="
              recorderForm.componentType === 'export' &&
              recorderForm.dataDomain === 'services'
            "
            label="服务子域"
          >
            <el-select
              v-model="recorderForm.subDomain"
              placeholder="选择子域（可选）"
              clearable
            >
              <el-option label="智能客服 (ai_assistant)" value="ai_assistant" />
              <el-option label="人工客服 (agent)" value="agent" />
            </el-select>
            <div style="font-size: 12px; color: #909399; margin-top: 4px">
              如果不选择子域，将录制通用的服务导出组件
            </div>
          </el-form-item>

          <!-- 示例数据域选择（仅当组件类型为 navigation 时显示） -->
          <el-form-item
            v-if="recorderForm.componentType === 'navigation'"
            label="示例数据域"
          >
            <el-select
              v-model="recorderForm.exampleDataDomain"
              placeholder="选择示例数据域（用于录制演示）"
              clearable
            >
              <el-option label="订单 (orders)" value="orders" />
              <el-option label="产品 (products)" value="products" />
              <el-option label="流量分析 (analytics)" value="analytics" />
              <el-option label="财务 (finance)" value="finance" />
              <el-option label="服务 (services)" value="services" />
              <el-option label="库存 (inventory)" value="inventory" />
            </el-select>
            <div style="font-size: 12px; color: #909399; margin-top: 4px">
              选择示例数据域用于录制演示。组件本身是通用的，运行时会根据参数动态导航。
            </div>
          </el-form-item>

          <el-form-item label="组件名称">
            <el-input
              v-model="recorderForm.componentName"
              placeholder="将根据平台和类型自动生成"
              :disabled="true"
            >
              <template #append>
                <el-tooltip
                  content="组件名称由平台和类型自动生成"
                  placement="top"
                >
                  <el-icon><InfoFilled /></el-icon>
                </el-tooltip>
              </template>
            </el-input>
          </el-form-item>

          <el-form-item label="测试账号">
            <el-select
              v-model="recorderForm.accountId"
              placeholder="选择测试账号"
              filterable
              :loading="accountsLoading"
              :disabled="!recorderForm.platform"
            >
              <el-option
                v-for="account in filteredAccounts"
                :key="account.id"
                :label="`${account.name || account.account_id} (${
                  account.shop_name || ''
                })`"
                :value="account.account_id"
              >
                <div
                  style="
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                  "
                >
                  <span style="font-weight: 500">{{
                    account.name || account.account_id
                  }}</span>
                  <span
                    style="color: #8492a6; font-size: 12px; margin-left: 8px"
                  >
                    {{ account.shop_name }}
                  </span>
                </div>
              </el-option>
              <template
                v-if="filteredAccounts.length === 0 && !accountsLoading"
              >
                <el-option disabled value="">
                  <span style="color: #909399">
                    {{
                      recorderForm.platform
                        ? "该平台暂无可用账号"
                        : "请先选择平台"
                    }}
                  </span>
                </el-option>
              </template>
            </el-select>
          </el-form-item>
        </el-form>

        <!-- 录制按钮 -->
        <div class="recorder-actions">
          <el-button
            type="primary"
            size="large"
            :icon="RecordIcon"
            :loading="isRecording"
            :disabled="!canStartRecording"
            @click="startRecording"
          >
            {{ isRecording ? "录制中..." : "开始录制" }}
          </el-button>

          <el-button
            v-if="isRecording"
            type="danger"
            size="large"
            :icon="StopIcon"
            @click="stopRecording"
          >
            停止录制
          </el-button>

          <el-button
            v-if="hasSteps"
            size="large"
            :icon="PlayIcon"
            @click="testComponent"
          >
            测试组件
          </el-button>
        </div>

        <!-- 录制说明 -->
        <el-alert
          v-if="!isRecording"
          type="info"
          title="录制说明"
          :closable="false"
          style="margin-top: 20px"
        >
          <p>1. 选择平台、组件类型和测试账号</p>
          <p>2. 点击"开始录制"打开浏览器窗口</p>
          <p>3. 在浏览器中执行操作，系统会自动记录步骤</p>
          <p>4. 完成后点击"停止录制"</p>
          <p>5. 在右侧编辑和完善组件配置</p>
        </el-alert>

        <el-alert
          v-else
          type="warning"
          title="正在录制"
          :closable="false"
          style="margin-top: 20px"
        >
          <p>浏览器窗口已打开，请在浏览器中执行操作</p>
          <p>当前已录制 {{ recordedSteps.length }} 个步骤</p>
          <p>完成后点击"停止录制"按钮</p>
        </el-alert>
      </el-card>

      <!-- 右侧：步骤/选项编辑器 -->
      <el-card class="editor-panel" shadow="hover">
        <template #header>
          <div class="card-header">
            <span class="card-title">
              {{ isDiscoveryMode ? "选项编辑" : "步骤编辑" }}
              <el-tag
                v-if="isDiscoveryMode"
                size="small"
                type="warning"
                style="margin-left: 8px"
              >
                发现模式
              </el-tag>
            </span>
            <div>
              <el-button
                v-if="!isDiscoveryMode"
                size="small"
                :icon="PlusIcon"
                @click="addStep"
              >
                添加步骤
              </el-button>
              <el-button
                v-if="isDiscoveryMode"
                size="small"
                :icon="PlusIcon"
                @click="addOption"
              >
                添加选项
              </el-button>
              <el-button
                size="small"
                :icon="SaveIcon"
                type="primary"
                :disabled="!hasRecordedData"
                @click="saveComponent"
              >
                保存组件
              </el-button>
            </div>
          </div>
        </template>

        <!-- Phase 11: 发现模式选项列表 -->
        <div v-if="isDiscoveryMode" class="discovery-editor">
          <!-- 打开动作 -->
          <div class="open-action-section">
            <h4 style="margin: 0 0 12px 0; color: #606266">
              <el-icon><VideoPlay /></el-icon> 打开动作
            </h4>
            <el-form
              v-if="openAction"
              :model="openAction"
              size="small"
              label-width="80px"
            >
              <el-form-item label="选择器">
                <el-input
                  :value="getOpenActionSelector()"
                  placeholder="点击日期控件的选择器"
                  readonly
                />
              </el-form-item>
              <el-form-item label="描述">
                <el-input
                  v-model="openAction.description"
                  placeholder="打开日期选择器"
                />
              </el-form-item>
            </el-form>
            <el-empty v-else description="未录制打开动作" :image-size="60" />
          </div>

          <!-- 已发现的选项 -->
          <div class="options-section" style="margin-top: 20px">
            <h4 style="margin: 0 0 12px 0; color: #606266">
              <el-icon><List /></el-icon> 已发现的选项 ({{
                availableOptions.length
              }})
            </h4>
            <div v-if="availableOptions.length > 0" class="options-list">
              <div
                v-for="(option, index) in availableOptions"
                :key="option.key"
                class="option-item"
              >
                <div class="option-header">
                  <el-tag
                    size="small"
                    :type="option.key === defaultOption ? 'success' : 'info'"
                  >
                    {{ option.key }}
                  </el-tag>
                  <span class="option-text">{{ option.text }}</span>
                  <div class="option-actions">
                    <el-button
                      v-if="option.key !== defaultOption"
                      size="small"
                      text
                      type="primary"
                      @click="setDefaultOption(option.key)"
                    >
                      设为默认
                    </el-button>
                    <el-button
                      size="small"
                      text
                      type="danger"
                      :icon="DeleteIcon"
                      @click="deleteOption(index)"
                    />
                  </div>
                </div>
              </div>
            </div>
            <el-empty v-else description="未发现任何选项" :image-size="80">
              <template #description>
                <p>请在录制时点击各个日期/筛选选项</p>
              </template>
            </el-empty>
          </div>

          <!-- 默认选项选择 -->
          <div
            v-if="availableOptions.length > 0"
            class="default-option-section"
            style="margin-top: 20px"
          >
            <el-form size="small" label-width="80px">
              <el-form-item label="默认选项">
                <el-select v-model="defaultOption" placeholder="选择默认选项">
                  <el-option
                    v-for="opt in availableOptions"
                    :key="opt.key"
                    :label="opt.text"
                    :value="opt.key"
                  />
                </el-select>
              </el-form-item>
            </el-form>
          </div>

          <!-- Phase 12: 测试配置区域 -->
          <div class="test-config-section" style="margin-top: 20px">
            <h4 style="margin: 0 0 12px 0; color: #606266">
              <el-icon><Setting /></el-icon> 测试配置
            </h4>
            <el-form size="small" label-width="100px">
              <el-form-item label="测试方式">
                <el-radio-group v-model="testConfig.type">
                  <el-radio :value="'url'" :label="'url'">使用URL导航</el-radio>
                  <el-radio :value="'data_domain'" :label="'data_domain'"
                    >使用数据域导航</el-radio
                  >
                </el-radio-group>
              </el-form-item>

              <el-form-item
                v-if="testConfig.type === 'url'"
                label="测试页面URL"
              >
                <el-input
                  v-model="testConfig.testUrl"
                  placeholder="如: {{account.login_url}}/portal/sale/order"
                >
                  <template #prepend>URL</template>
                </el-input>
                <div style="font-size: 12px; color: #909399; margin-top: 4px">
                  支持变量: {{ account.login_url }}
                </div>
              </el-form-item>

              <el-form-item
                v-if="testConfig.type === 'data_domain'"
                label="测试数据域"
              >
                <el-select
                  v-model="testConfig.testDataDomain"
                  placeholder="选择数据域"
                >
                  <el-option label="订单 (orders)" value="orders" />
                  <el-option label="产品 (products)" value="products" />
                  <el-option label="流量分析 (analytics)" value="analytics" />
                  <el-option label="财务 (finance)" value="finance" />
                  <el-option label="服务 (services)" value="services" />
                  <el-option label="库存 (inventory)" value="inventory" />
                </el-select>
                <div style="font-size: 12px; color: #909399; margin-top: 4px">
                  测试时将调用 navigation 组件导航到该数据域
                </div>
              </el-form-item>
            </el-form>
          </div>
        </div>

        <!-- 步骤模式：步骤列表 -->
        <div v-else-if="hasSteps" class="steps-list">
          <!-- Phase 12.3: 批量标记工具栏 -->
          <div
            class="batch-actions"
            style="
              margin-bottom: 12px;
              padding: 10px;
              background: #f5f7fa;
              border-radius: 6px;
            "
          >
            <el-checkbox
              v-model="selectAllSteps"
              :indeterminate="isIndeterminate"
              @change="handleSelectAll"
              style="margin-right: 12px"
            >
              全选
            </el-checkbox>
            <el-button
              size="small"
              :disabled="selectedStepIndices.length === 0"
              @click="batchMarkAs('date_picker')"
            >
              标记为日期组件
            </el-button>
            <el-button
              size="small"
              :disabled="selectedStepIndices.length === 0"
              @click="batchMarkAs('filters')"
            >
              标记为筛选器
            </el-button>
            <el-button
              size="small"
              :disabled="selectedStepIndices.length === 0"
              @click="batchMarkAs('normal')"
            >
              取消标记
            </el-button>
            <el-divider direction="vertical" />
            <el-button
              size="small"
              type="success"
              :disabled="selectedStepIndices.length === 0"
              @click="batchSetOptionalSelected(true)"
            >
              设为可选
            </el-button>
            <el-button
              size="small"
              :disabled="selectedStepIndices.length === 0"
              @click="batchSetOptionalSelected(false)"
            >
              设为必选
            </el-button>
            <el-button
              size="small"
              type="danger"
              :disabled="selectedStepIndices.length === 0"
              @click="batchDeleteSelected"
            >
              批量删除
            </el-button>
            <span
              v-if="selectedStepIndices.length > 0"
              style="margin-left: 12px; color: #909399; font-size: 12px"
            >
              已选择 {{ selectedStepIndices.length }} 个步骤
            </span>
          </div>

          <draggable
            v-model="recordedSteps"
            item-key="id"
            handle=".drag-handle"
          >
            <template #item="{ element, index }">
              <div
                class="step-item"
                :class="{
                  'step-date-picker': element.step_group === 'date_picker',
                  'step-filters': element.step_group === 'filters',
                }"
              >
                <div class="step-header">
                  <el-checkbox
                    v-model="element.selected"
                    @change="updateSelectedIndices"
                    style="margin-right: 8px"
                  />
                  <el-icon class="drag-handle"><Rank /></el-icon>
                  <span class="step-number">步骤 {{ index + 1 }}</span>
                  <el-tag size="small">{{ element.action }}</el-tag>
                  <el-tag
                    v-if="element.step_group === 'date_picker'"
                    size="small"
                    type="warning"
                    style="margin-left: 4px"
                  >
                    日期
                  </el-tag>
                  <el-tag
                    v-if="element.step_group === 'filters'"
                    size="small"
                    type="success"
                    style="margin-left: 4px"
                  >
                    筛选
                  </el-tag>
                  <el-button
                    size="small"
                    type="danger"
                    text
                    :icon="DeleteIcon"
                    @click="deleteStep(index)"
                  />
                </div>

                <div class="step-content">
                  <el-form :model="element" size="small" label-width="80px">
                    <el-form-item label="动作">
                      <el-select v-model="element.action">
                        <el-option label="navigate - 导航" value="navigate" />
                        <el-option label="click - 点击" value="click" />
                        <el-option label="fill - 输入" value="fill" />
                        <el-option label="wait - 等待" value="wait" />
                        <el-option
                          label="get_text - 获取文本"
                          value="get_text"
                        />
                        <el-option
                          label="custom_js - 自定义JS"
                          value="custom_js"
                        />
                      </el-select>
                    </el-form-item>

                    <el-form-item
                      v-if="element.action === 'navigate'"
                      label="URL"
                    >
                      <el-input
                        v-model="element.url"
                        placeholder="https://..."
                      />
                    </el-form-item>

                    <el-form-item
                      v-if="
                        ['click', 'fill', 'wait', 'get_text'].includes(
                          element.action
                        )
                      "
                      label="选择器"
                    >
                      <el-input
                        v-model="element.selector"
                        placeholder="CSS选择器（wait步骤可留空）"
                        type="textarea"
                        :rows="2"
                      />
                    </el-form-item>

                    <!-- 新增：wait步骤的duration字段 -->
                    <el-form-item
                      v-if="element.action === 'wait'"
                      label="等待时长"
                    >
                      <el-input-number
                        v-model="element.duration"
                        :min="0"
                        :max="60000"
                        :step="1000"
                        placeholder="毫秒（留空则等待元素）"
                        style="width: 100%"
                      />
                      <div
                        style="font-size: 12px; color: #909399; margin-top: 4px"
                      >
                        单位：毫秒 (ms)。留空则等待选择器元素出现。例如：3000 =
                        3秒
                      </div>
                    </el-form-item>

                    <el-form-item v-if="element.action === 'fill'" label="值">
                      <el-input v-model="element.value" placeholder="输入值" />
                    </el-form-item>

                    <el-form-item label="注释">
                      <el-input
                        v-model="element.comment"
                        placeholder="步骤说明"
                      />
                    </el-form-item>

                    <el-form-item label="可选">
                      <el-switch v-model="element.optional" />
                    </el-form-item>

                    <!-- Phase 12.3: 步骤标记 -->
                    <el-form-item label="步骤标记">
                      <el-select
                        v-model="element.step_group"
                        placeholder="普通步骤"
                      >
                        <el-option label="普通步骤" value="normal" />
                        <el-option label="日期组件" value="date_picker" />
                        <el-option label="筛选器" value="filters" />
                      </el-select>
                      <div
                        v-if="element.step_group === 'date_picker'"
                        style="font-size: 12px; color: #e6a23c; margin-top: 4px"
                      >
                        此步骤将转换为调用日期选择器组件
                      </div>
                      <div
                        v-if="element.step_group === 'filters'"
                        style="font-size: 12px; color: #67c23a; margin-top: 4px"
                      >
                        此步骤将转换为调用筛选器组件
                      </div>
                    </el-form-item>
                  </el-form>
                </div>
              </div>
            </template>
          </draggable>
        </div>

        <!-- 空状态 -->
        <el-empty v-else description="还没有录制任何步骤" :image-size="150">
          <template #image>
            <el-icon :size="80" color="#909399"><Document /></el-icon>
          </template>
        </el-empty>
      </el-card>

      <!-- YAML预览 -->
      <el-card class="yaml-panel" shadow="hover">
        <template #header>
          <div class="card-header">
            <span class="card-title">YAML预览</span>
            <el-button size="small" :icon="CopyIcon" @click="copyYaml">
              复制
            </el-button>
          </div>
        </template>

        <el-input
          v-model="yamlContent"
          type="textarea"
          :rows="25"
          readonly
          class="yaml-textarea"
        />
      </el-card>
    </div>

    <!-- 测试对话框 -->
    <el-dialog
      v-model="testDialogVisible"
      title="组件测试"
      width="900px"
      :close-on-click-modal="false"
    >
      <!-- 测试配置 -->
      <div
        class="test-header"
        style="
          margin-bottom: 20px;
          padding: 15px;
          background: #f5f7fa;
          border-radius: 4px;
        "
      >
        <div
          style="
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
          "
        >
          <div>
            <span style="font-weight: 600; margin-right: 10px">组件:</span>
            <el-tag>{{ recorderForm.platform }}</el-tag>
            <el-tag type="warning" style="margin-left: 8px">{{
              recorderForm.componentType
            }}</el-tag>
          </div>
          <div>
            <el-tag type="info">{{ recordedSteps.length }} 个步骤</el-tag>
          </div>
        </div>

        <div style="display: flex; align-items: center; gap: 10px">
          <span style="font-weight: 600">测试账号:</span>
          <el-select
            v-model="testAccountId"
            size="small"
            style="width: 300px"
            :disabled="testing"
          >
            <el-option
              v-for="account in filteredAccounts"
              :key="account.account_id"
              :label="`${account.name || account.account_id} (${
                account.shop_name || ''
              })`"
              :value="account.account_id"
            />
          </el-select>

          <el-button
            type="primary"
            size="small"
            :loading="testing"
            :disabled="!testAccountId"
            @click="startTest"
          >
            {{ testing ? "测试中..." : "开始测试" }}
          </el-button>
        </div>

        <!-- Phase 12.3: 组件调用参数选择 -->
        <div
          v-if="hasDatePickerSteps || hasFiltersSteps"
          style="
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px dashed #dcdfe6;
          "
        >
          <span style="font-weight: 600; color: #606266">组件参数设置:</span>
          <div
            style="margin-top: 10px; display: flex; gap: 20px; flex-wrap: wrap"
          >
            <div v-if="hasDatePickerSteps" style="flex: 1; min-width: 200px">
              <span style="color: #e6a23c; margin-right: 8px">[日期组件]</span>
              <el-select
                v-model="testParams.date_range"
                size="small"
                placeholder="选择日期范围"
                style="width: 180px"
              >
                <el-option label="今天" value="today" />
                <el-option label="昨天" value="yesterday" />
                <el-option label="最近7天" value="last_7_days" />
                <el-option label="最近30天" value="last_30_days" />
                <el-option label="本月" value="this_month" />
                <el-option label="上月" value="last_month" />
              </el-select>
            </div>
            <div v-if="hasFiltersSteps" style="flex: 1; min-width: 200px">
              <span style="color: #67c23a; margin-right: 8px">[筛选器]</span>
              <el-input
                v-model="testParams.filter_value"
                size="small"
                placeholder="筛选值（如: completed）"
                style="width: 180px"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- 测试提示 -->
      <el-alert
        v-if="!testResult && !testing"
        type="info"
        :closable="false"
        style="margin-bottom: 20px"
      >
        <template #title>
          <div>
            <p style="margin: 0 0 8px 0">📌 测试说明：</p>
            <p style="margin: 0; font-size: 13px">
              1. 点击"开始测试"将打开浏览器窗口（有头模式）
            </p>
            <p style="margin: 0; font-size: 13px">
              2. 您可以观察每个步骤的执行过程
            </p>
            <p style="margin: 0; font-size: 13px">
              3. 测试完成后会显示详细结果和失败截图
            </p>
          </div>
        </template>
      </el-alert>

      <el-alert
        v-if="testing"
        type="warning"
        :closable="false"
        style="margin-bottom: 20px"
      >
        <template #title>
          <div style="display: flex; align-items: center; gap: 8px">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span>浏览器窗口已打开，正在执行测试...</span>
          </div>
        </template>
      </el-alert>

      <!-- 测试结果 -->
      <div v-if="testResult" class="test-results">
        <!-- 总体结果 -->
        <div style="display: flex; gap: 20px; margin-bottom: 20px">
          <el-statistic
            title="总耗时"
            :value="testResult.duration_ms"
            suffix="ms"
          />
          <el-statistic
            title="成功率"
            :value="testResult.success_rate"
            suffix="%"
            :value-style="{
              color: testResult.success_rate >= 90 ? '#67c23a' : '#f56c6c',
            }"
          />
          <el-statistic
            title="成功步骤"
            :value="testResult.steps_passed"
            :suffix="`/ ${testResult.steps_total}`"
          />
        </div>

        <!-- 步骤执行列表 -->
        <el-timeline>
          <el-timeline-item
            v-for="(step, index) in testStepResults"
            :key="index"
            :type="getStepStatusType(step.status)"
            :icon="getStepStatusIcon(step.status)"
          >
            <div class="step-result">
              <div
                class="step-header"
                style="
                  display: flex;
                  justify-content: space-between;
                  align-items: center;
                  margin-bottom: 8px;
                "
              >
                <div>
                  <el-tag :type="getStepStatusType(step.status)" size="small">
                    步骤 {{ index + 1 }}: {{ step.action }}
                  </el-tag>
                </div>
                <span style="color: #909399; font-size: 12px"
                  >{{ step.duration_ms }}ms</span
                >
              </div>

              <!-- 失败详情 -->
              <div v-if="step.status === 'failed'" class="step-error">
                <el-alert
                  type="error"
                  :closable="false"
                  style="margin-bottom: 10px"
                >
                  <template #title>
                    <div>
                      <p style="margin: 0 0 5px 0; font-weight: 600">
                        错误信息:
                      </p>
                      <p style="margin: 0; font-size: 13px">{{ step.error }}</p>
                      <p
                        style="
                          margin: 8px 0 0 0;
                          font-size: 12px;
                          color: #e6a23c;
                        "
                      >
                        💡 {{ getFixSuggestion(step) }}
                      </p>
                    </div>
                  </template>
                </el-alert>

                <!-- 失败截图 -->
                <el-image
                  v-if="step.screenshot_base64"
                  :src="`data:image/png;base64,${step.screenshot_base64}`"
                  :preview-src-list="[
                    `data:image/png;base64,${step.screenshot_base64}`,
                  ]"
                  fit="contain"
                  style="
                    max-width: 400px;
                    cursor: pointer;
                    border: 1px solid #dcdfe6;
                    border-radius: 4px;
                  "
                  :preview-teleported="true"
                >
                  <template #error>
                    <div
                      style="padding: 20px; text-align: center; color: #909399"
                    >
                      截图加载失败
                    </div>
                  </template>
                </el-image>

                <!-- 操作按钮 -->
                <div style="margin-top: 10px">
                  <el-button size="small" @click="editStep(index)">
                    🔧 修改此步骤
                  </el-button>
                </div>
              </div>
            </div>
          </el-timeline-item>
        </el-timeline>
      </div>

      <template #footer>
        <div style="display: flex; justify-content: space-between">
          <el-button @click="testDialogVisible = false">关闭</el-button>
          <el-button
            v-if="testResult"
            type="primary"
            @click="retryTest"
            :loading="testing"
          >
            🔄 重新测试
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  VideoPlay as RecordIcon,
  VideoPlay,
  VideoPause as StopIcon,
  CaretRight as PlayIcon,
  Plus as PlusIcon,
  Delete as DeleteIcon,
  Document,
  Rank,
  DocumentCopy as CopyIcon,
  FolderOpened as SaveIcon,
  InfoFilled,
  Loading,
  CircleCheck,
  CircleClose,
  Clock,
  List,
  Setting,
} from "@element-plus/icons-vue";
import draggable from "vuedraggable";
import api from "@/api";
import accountsApi from "@/api/accounts"; // ⭐ Phase 9完善：导入账号管理API

// 响应式数据
const recorderForm = ref({
  platform: "",
  componentType: "",
  componentName: "",
  accountId: "",
  dataDomain: "", // 数据域（仅export组件）
  subDomain: "", // 服务子域（仅services数据域）
  exampleDataDomain: "", // 示例数据域（仅navigation组件）
});

const isRecording = ref(false);
const recordedSteps = ref([]);
const accounts = ref([]);
const accountsLoading = ref(false); // ⭐ Phase 9完善：账号加载状态

// Phase 11: 发现模式数据
const recordingMode = ref("steps"); // 'steps' 或 'discovery'
const openAction = ref(null); // 发现模式的打开动作
const availableOptions = ref([]); // 发现模式的可用选项
const defaultOption = ref(""); // 默认选项 key

// Phase 12: 测试配置
const testConfig = ref({
  type: "url", // 'url' 或 'data_domain'
  testUrl: "", // 测试页面URL
  testDataDomain: "", // 测试数据域
});

// 计算属性
const canStartRecording = computed(() => {
  const baseCheck =
    recorderForm.value.platform &&
    recorderForm.value.componentType &&
    recorderForm.value.accountId;

  // 导出组件必须选择数据域
  if (recorderForm.value.componentType === "export") {
    return baseCheck && recorderForm.value.dataDomain;
  }

  return baseCheck;
});

const hasSteps = computed(() => recordedSteps.value.length > 0);

// Phase 11: 发现模式相关计算属性
const isDiscoveryMode = computed(() => recordingMode.value === "discovery");
const hasDiscoveryData = computed(
  () => openAction.value !== null || availableOptions.value.length > 0
);
const hasRecordedData = computed(() =>
  isDiscoveryMode.value ? hasDiscoveryData.value : hasSteps.value
);

// 判断组件类型是否使用发现模式
const isDiscoveryComponentType = computed(() => {
  return ["date_picker", "filters"].includes(recorderForm.value.componentType);
});

// Phase 12.3: 批量选择和标记相关
const selectAllSteps = ref(false);

const selectedStepIndices = computed(() => {
  return recordedSteps.value
    .map((step, index) => (step.selected ? index : -1))
    .filter((index) => index !== -1);
});

const isIndeterminate = computed(() => {
  const selectedCount = selectedStepIndices.value.length;
  return selectedCount > 0 && selectedCount < recordedSteps.value.length;
});

const handleSelectAll = (val) => {
  recordedSteps.value.forEach((step) => {
    step.selected = val;
  });
};

const updateSelectedIndices = () => {
  const allSelected = recordedSteps.value.every((step) => step.selected);
  const noneSelected = recordedSteps.value.every((step) => !step.selected);
  selectAllSteps.value = allSelected;
};

const batchMarkAs = (groupType) => {
  recordedSteps.value.forEach((step) => {
    if (step.selected) {
      step.step_group = groupType === "normal" ? undefined : groupType;
    }
  });
  // 取消选择
  recordedSteps.value.forEach((step) => {
    step.selected = false;
  });
  selectAllSteps.value = false;
};

// Phase 12.4: 批量设为可选/必选
const batchSetOptionalSelected = (optional) => {
  let count = 0;
  recordedSteps.value.forEach((step) => {
    if (step.selected) {
      step.optional = optional;
      count++;
    }
  });
  ElMessage.success(`已设置 ${count} 个步骤为${optional ? "可选" : "必选"}`);
  // 取消选择
  recordedSteps.value.forEach((step) => {
    step.selected = false;
  });
  selectAllSteps.value = false;
};

// Phase 12.4: 批量删除
const batchDeleteSelected = () => {
  const selectedCount = selectedStepIndices.value.length;
  if (selectedCount === 0) {
    ElMessage.warning("请先选择要删除的步骤");
    return;
  }

  ElMessageBox.confirm(
    `确定要删除选中的 ${selectedCount} 个步骤吗？`,
    "确认删除",
    {
      confirmButtonText: "删除",
      cancelButtonText: "取消",
      type: "warning",
    }
  )
    .then(() => {
      // 从后向前删除，避免索引错位
      const sortedIndices = [...selectedStepIndices.value].sort(
        (a, b) => b - a
      );
      sortedIndices.forEach((index) => {
        recordedSteps.value.splice(index, 1);
      });
      ElMessage.success(`已删除 ${selectedCount} 个步骤`);
      selectAllSteps.value = false;
    })
    .catch(() => {
      // 用户取消
    });
};

const recordingStatus = computed(() => {
  if (isRecording.value) {
    return { text: "录制中", type: "success" };
  } else if (hasSteps.value) {
    return { text: "已完成", type: "info" };
  } else {
    return { text: "未开始", type: "info" };
  }
});

// ⭐ Phase 9完善：筛选已启用的账号
const filteredAccounts = computed(() => {
  const filtered = accounts.value.filter((account) => {
    // 平台筛选（大小写不敏感）
    const matchesPlatform =
      !recorderForm.value.platform ||
      (account.platform &&
        account.platform.toLowerCase() ===
          recorderForm.value.platform.toLowerCase());
    // 只显示启用的账号
    const isEnabled = account.enabled !== false;
    return matchesPlatform && isEnabled;
  });

  return filtered;
});

// ⭐ Phase 5: 自动生成组件名称（支持数据域和子域）
watch(
  () => [
    recorderForm.value.platform,
    recorderForm.value.componentType,
    recorderForm.value.dataDomain,
    recorderForm.value.subDomain,
  ],
  ([platform, componentType, dataDomain, subDomain]) => {
    if (platform && componentType) {
      if (componentType === "export" && dataDomain) {
        // 导出组件名称：{platform}_{dataDomain}_export 或 {platform}_{dataDomain}_{subDomain}_export
        if (subDomain) {
          recorderForm.value.componentName = `${platform}_${dataDomain}_${subDomain}_export`;
        } else {
          recorderForm.value.componentName = `${platform}_${dataDomain}_export`;
        }
      } else {
        // 其他组件名称：{platform}_{componentType}
        recorderForm.value.componentName = `${platform}_${componentType}`;
      }
    }
  },
  { immediate: true }
);

// 数据域变化时清空子域
const onDataDomainChange = () => {
  recorderForm.value.subDomain = "";
};

// 组件类型变化时清空相关字段
watch(
  () => recorderForm.value.componentType,
  () => {
    recorderForm.value.dataDomain = "";
    recorderForm.value.subDomain = "";
    recorderForm.value.exampleDataDomain = "";
  }
);

// ⭐ Phase 9完善：监听平台变化，自动刷新账号列表
watch(
  () => recorderForm.value.platform,
  (newPlatform) => {
    if (newPlatform) {
      // 清空已选账号
      recorderForm.value.accountId = "";
      // 重新加载该平台的账号
      loadAccounts();
    } else {
      accounts.value = [];
    }
  }
);

// YAML字符串转义函数（Phase 12.4: 修复注释字段的特殊字符问题）
const escapeYamlString = (str) => {
  if (!str) return "''";

  // 转义特殊字符
  const escaped = String(str)
    .replace(/\\/g, "\\\\")
    .replace(/"/g, '\\"')
    .replace(/\n/g, "\\n");

  // 如果包含特殊字符，使用引号包裹
  if (/[:#@`|>'"\[\]{},%&*?!<>]/.test(str) || str.includes("'")) {
    return `"${escaped}"`;
  }

  // 如果是纯数字或布尔值，也用引号包裹避免类型解析问题
  if (/^(true|false|null|[0-9]+\.?[0-9]*)$/i.test(str.trim())) {
    return `'${str}'`;
  }

  return `'${str}'`;
};

// 生成YAML内容
const yamlContent = computed(() => {
  // Phase 11: 根据模式判断是否有数据
  if (!hasRecordedData.value) {
    return isDiscoveryMode.value
      ? "# 还没有录制任何选项"
      : "# 还没有录制任何步骤";
  }

  const componentName = recorderForm.value.componentName || "unnamed_component";
  const platform = recorderForm.value.platform;
  const componentType = recorderForm.value.componentType;
  const dataDomain = recorderForm.value.dataDomain;
  const subDomain = recorderForm.value.subDomain;
  const exampleDataDomain = recorderForm.value.exampleDataDomain;

  let yaml = `# ${platform.toUpperCase()} ${componentType} 组件\n`;
  yaml += `# 生成时间: ${new Date().toLocaleString("zh-CN")}\n`;
  yaml += `# Phase 11: UI化组件录制工具生成（支持发现模式）\n\n`;
  yaml += `name: ${componentName}\n`;
  yaml += `platform: ${platform}\n`;
  yaml += `type: ${componentType}\n`;
  yaml += `version: 1.0.0\n`;

  // 导出组件添加数据域和子域字段
  if (componentType === "export" && dataDomain) {
    yaml += `data_domain: ${dataDomain}\n`;
    if (subDomain) {
      yaml += `sub_domain: ${subDomain}\n`;
    }
  }

  // 根据组件类型生成不同的描述
  if (componentType === "export" && dataDomain) {
    const domainLabel = subDomain ? `${dataDomain}/${subDomain}` : dataDomain;
    yaml += `description: "${platform} ${domainLabel} 导出组件（UI录制工具生成）"\n\n`;
  } else {
    yaml += `description: "${platform} ${componentType} 组件（UI录制工具生成）"\n\n`;
  }

  // Phase 11: 发现模式（date_picker, filters）
  if (isDiscoveryMode.value) {
    // Phase 12: 测试配置
    yaml += `# 测试配置（用于组件测试时导航到目标页面）\n`;
    yaml += `test_config:\n`;
    if (testConfig.value.type === "url" && testConfig.value.testUrl) {
      yaml += `  test_url: '${testConfig.value.testUrl}'\n`;
    } else if (
      testConfig.value.type === "data_domain" &&
      testConfig.value.testDataDomain
    ) {
      yaml += `  test_data_domain: '${testConfig.value.testDataDomain}'\n`;
    } else {
      yaml += `  test_url: '{{account.login_url}}/TODO_填写测试页面路径'\n`;
    }
    yaml += `\n`;

    // 打开动作
    if (openAction.value) {
      yaml += `# 打开选择器的动作\n`;
      yaml += `open_action:\n`;
      yaml += `  action: click\n`;
      if (openAction.value.selectors && openAction.value.selectors.length > 0) {
        yaml += `  selectors:\n`;
        openAction.value.selectors.forEach((sel) => {
          yaml += `    - type: ${sel.type}\n`;
          yaml += `      value: '${sel.value}'\n`;
          if (sel.priority) yaml += `      priority: ${sel.priority}\n`;
        });
      }
      yaml += `  comment: '${
        openAction.value.description || "打开选择器"
      }'\n\n`;
    }

    // 可用选项
    yaml += `# 可用选项列表\n`;
    yaml += `available_options:\n`;
    availableOptions.value.forEach((opt) => {
      yaml += `  - key: ${opt.key}\n`;
      yaml += `    text: '${opt.text}'\n`;
      if (opt.selectors && opt.selectors.length > 0) {
        yaml += `    selectors:\n`;
        opt.selectors.forEach((sel) => {
          yaml += `      - type: ${sel.type}\n`;
          yaml += `        value: '${sel.value}'\n`;
          if (sel.priority) yaml += `        priority: ${sel.priority}\n`;
        });
      }
      yaml += `\n`;
    });

    // 默认选项
    if (defaultOption.value) {
      yaml += `default_option: ${defaultOption.value}\n\n`;
    }

    // 参数定义
    yaml += `# 运行时参数\n`;
    yaml += `params:\n`;
    if (componentType === "date_picker") {
      yaml += `  date_range:\n`;
      yaml += `    type: enum\n`;
      yaml += `    values: [${availableOptions.value
        .map((o) => o.key)
        .join(", ")}]\n`;
      yaml += `    default: ${defaultOption.value || "last_7_days"}\n`;
    } else {
      yaml += `  filter_value:\n`;
      yaml += `    type: enum\n`;
      yaml += `    values: [${availableOptions.value
        .map((o) => o.key)
        .join(", ")}]\n`;
      yaml += `    default: ${
        defaultOption.value || availableOptions.value[0]?.key || "all"
      }\n`;
    }

    return yaml;
  }

  // Navigation 组件添加数据域URL映射注释
  if (componentType === "navigation") {
    yaml += `# 数据域URL映射（运行时根据 params.data_domain 参数动态选择）\n`;
    yaml += `data_domain_urls:\n`;
    yaml += `  orders: '/portal/sale/order'\n`;
    yaml += `  products: '/portal/product/list'\n`;
    yaml += `  analytics: '/portal/datacenter/traffic'\n`;
    yaml += `  finance: '/portal/income/bill'\n`;
    yaml += `  services: '/portal/chat'\n`;
    yaml += `  inventory: '/portal/stock'\n`;
    yaml += `\n`;
    if (exampleDataDomain) {
      yaml += `# 录制时使用的示例数据域: ${exampleDataDomain}\n`;
    }
    yaml += `\n`;
  }

  yaml += `steps:\n`;

  // Phase 12.3: 处理步骤标记，将标记的步骤转换为 component_call
  let currentGroup = null;
  let groupSteps = [];

  const flushGroup = () => {
    if (currentGroup && groupSteps.length > 0) {
      // 输出 component_call
      yaml += `  # 以下步骤已标记为 ${
        currentGroup === "date_picker" ? "日期组件" : "筛选器"
      }，建议替换为 component_call\n`;
      yaml += `  - action: component_call\n`;
      yaml += `    component: '${platform}/${currentGroup}'\n`;
      yaml += `    params:\n`;
      if (currentGroup === "date_picker") {
        yaml += `      date_range: '{{params.date_range}}'\n`;
      } else {
        yaml += `      filter_value: '{{params.filter_value}}'\n`;
      }
      yaml += `    comment: '调用${
        currentGroup === "date_picker" ? "日期选择器" : "筛选器"
      }组件'\n`;
      yaml += `    # 原始录制步骤（供参考）:\n`;
      groupSteps.forEach((step, i) => {
        yaml += `    #   步骤${i + 1}: ${step.action} - ${
          step.selector || step.url || ""
        }\n`;
      });
      yaml += `\n`;
      groupSteps = [];
    }
  };

  recordedSteps.value.forEach((step) => {
    const stepGroup = step.step_group || "normal";

    if (stepGroup !== "normal") {
      // 标记的步骤
      if (currentGroup !== stepGroup) {
        flushGroup();
        currentGroup = stepGroup;
      }
      groupSteps.push(step);
    } else {
      // 普通步骤
      flushGroup();
      currentGroup = null;

      yaml += `  - action: ${step.action}\n`;
      if (step.url) yaml += `    url: ${escapeYamlString(step.url)}\n`;
      if (step.selector)
        yaml += `    selector: ${escapeYamlString(step.selector)}\n`;
      if (step.value) yaml += `    value: ${escapeYamlString(step.value)}\n`;
      if (step.duration !== undefined && step.duration !== null)
        yaml += `    duration: ${step.duration}\n`;
      if (step.comment)
        yaml += `    comment: ${escapeYamlString(step.comment)}\n`;
      if (step.optional) yaml += `    optional: true\n`;
      yaml += `\n`;

      // Phase 12.4: 自动检测导出按钮点击，添加 wait_for_download 步骤
      const isExportClick =
        step.action === "click" &&
        ((step.comment &&
          (step.comment.toLowerCase().includes("导出") ||
            step.comment.toLowerCase().includes("export"))) ||
          (step.selector &&
            (step.selector.toLowerCase().includes("export") ||
              step.selector.includes("导出"))));

      if (isExportClick) {
        // 检查下一步是否已经是 wait_for_download
        const currentIndex = recordedSteps.value.indexOf(step);
        const nextStep = recordedSteps.value[currentIndex + 1];

        if (!nextStep || nextStep.action !== "wait_for_download") {
          yaml += `  # Phase 12.4: 自动添加的下载等待步骤（可删除或调整超时时间）\n`;
          yaml += `  - action: wait_for_download\n`;
          yaml += `    timeout: 180000\n`;
          yaml += `    comment: '等待文件下载（自动添加）'\n`;
          yaml += `\n`;
        }
      }
    }
  });

  // 处理最后一组
  flushGroup();

  yaml += `success_criteria:\n`;
  yaml += `  - type: url_contains\n`;
  yaml += `    value: 'TODO: 填写成功URL特征'\n`;
  yaml += `    optional: false\n`;
  yaml += `    comment: '请填写成功判定条件'\n\n`;

  yaml += `error_handlers:\n`;
  yaml += `  - selector: '.error-message'\n`;
  yaml += `    action: fail_task\n`;
  yaml += `    message: 'TODO: 填写错误处理'\n`;

  return yaml;
});

// 方法
const startRecording = async () => {
  try {
    isRecording.value = true;
    ElMessage.info("正在打开浏览器窗口...");

    const response = await api.post("/collection/recorder/start", {
      platform: recorderForm.value.platform,
      component_type: recorderForm.value.componentType,
      account_id: recorderForm.value.accountId,
    });

    if (response.success) {
      ElMessage.success("录制已开始，请在浏览器中执行操作");

      // 开始轮询录制状态
      startPollingSteps();
    }
  } catch (error) {
    console.error("启动录制失败:", error);
    ElMessage.error("启动录制失败: " + error.message);
    isRecording.value = false;
  }
};

const stopRecording = async () => {
  try {
    ElMessage.info("正在停止录制，请稍等...");

    const response = await api.post("/collection/recorder/stop");

    if (response.success) {
      isRecording.value = false;

      // Phase 11: 根据模式处理不同的响应
      if (response.mode === "discovery") {
        // 发现模式
        recordingMode.value = "discovery";
        openAction.value = response.open_action;
        availableOptions.value = response.available_options || [];
        defaultOption.value = response.default_option || "";
        recordedSteps.value = []; // 清空步骤

        // Phase 12.2: 自动填充测试配置（从录制结果中获取）
        if (response.test_config && response.test_config.test_url) {
          testConfig.value.type = "url";
          testConfig.value.testUrl = response.test_config.test_url;
          console.log(
            "[ComponentRecorder] Auto-filled test_url:",
            response.test_config.test_url
          );
        } else if (
          response.test_config &&
          response.test_config.test_data_domain
        ) {
          testConfig.value.type = "data_domain";
          testConfig.value.testDataDomain =
            response.test_config.test_data_domain;
        }

        if (availableOptions.value.length > 0) {
          ElMessage.success(
            `录制完成，共发现 ${availableOptions.value.length} 个选项`
          );
        } else {
          ElMessage.warning(
            "录制完成，但未发现任何选项。请确保点击了日期/筛选选项。"
          );
        }
      } else {
        // 步骤模式
        recordingMode.value = "steps";
        openAction.value = null;
        availableOptions.value = [];

        if (response.steps && response.steps.length > 0) {
          recordedSteps.value = response.steps;
          ElMessage.success(`录制完成，共记录 ${response.steps.length} 个步骤`);
        } else {
          ElMessage.warning(
            "录制完成，但未记录到任何步骤。请确保在Inspector中进行了操作。"
          );
        }
      }

      stopPollingSteps();
    }
  } catch (error) {
    console.error("停止录制失败:", error);
    ElMessage.error("停止录制失败: " + error.message);
  }
};

let pollingInterval = null;

const startPollingSteps = () => {
  pollingInterval = setInterval(async () => {
    try {
      const response = await api.get("/collection/recorder/steps");

      if (response.success && response.data) {
        recordedSteps.value = response.data.steps || [];
      }
    } catch (error) {
      console.error("获取录制步骤失败:", error);
    }
  }, 1000); // 每秒轮询一次
};

const stopPollingSteps = () => {
  if (pollingInterval) {
    clearInterval(pollingInterval);
    pollingInterval = null;
  }
};

const addStep = () => {
  recordedSteps.value.push({
    id: Date.now(),
    action: "click",
    selector: "",
    comment: "",
    optional: false,
  });
};

const deleteStep = (index) => {
  recordedSteps.value.splice(index, 1);
};

// Phase 11: 发现模式辅助函数
const getOpenActionSelector = () => {
  if (!openAction.value || !openAction.value.selectors) return "";
  const selectors = openAction.value.selectors;
  // 优先使用 text 类型
  for (const sel of selectors) {
    if (sel.type === "text") return sel.value;
  }
  // 其次使用 css 类型
  for (const sel of selectors) {
    if (sel.type === "css") return sel.value;
  }
  return selectors[0]?.value || "";
};

const addOption = () => {
  availableOptions.value.push({
    key: `option_${Date.now()}`,
    text: "新选项",
    selectors: [],
  });
};

const deleteOption = (index) => {
  const deletedKey = availableOptions.value[index]?.key;
  availableOptions.value.splice(index, 1);
  // 如果删除的是默认选项，重置默认选项
  if (deletedKey === defaultOption.value && availableOptions.value.length > 0) {
    defaultOption.value = availableOptions.value[0].key;
  }
};

const setDefaultOption = (key) => {
  defaultOption.value = key;
};

// 测试相关状态
const testDialogVisible = ref(false);
const testing = ref(false);
const testAccountId = ref("");
const testResult = ref(null);
const testStepResults = ref([]);

// Phase 12.3: 测试参数
const testParams = ref({
  date_range: "last_7_days",
  filter_value: "",
});

// 检查是否有标记的步骤
const hasDatePickerSteps = computed(() => {
  return recordedSteps.value.some((step) => step.step_group === "date_picker");
});

const hasFiltersSteps = computed(() => {
  return recordedSteps.value.some((step) => step.step_group === "filters");
});

const testComponent = async () => {
  // 显示测试对话框
  testDialogVisible.value = true;
  testAccountId.value = recorderForm.value.accountId; // 默认使用录制账号
  testResult.value = null;
  testStepResults.value = [];
  testing.value = false;
};

const startTest = async () => {
  try {
    testing.value = true;
    testStepResults.value = [];

    ElMessage.info({
      message: "正在打开浏览器窗口，请稍候...",
      duration: 3000,
    });

    const response = await api.post("/collection/recorder/test", {
      platform: recorderForm.value.platform,
      component_type: recorderForm.value.componentType,
      account_id: testAccountId.value,
      steps: recordedSteps.value,
    });

    // Phase 12.5: 无论成功失败都显示测试结果和步骤
    testResult.value = response.test_result;
    testStepResults.value = response.test_result?.step_results || [];

    // Phase 12.5: 如果步骤结果为空但测试失败，创建一个错误步骤用于显示
    if (testStepResults.value.length === 0 && !response.success) {
      console.warn("Test failed but no step results returned");
      testStepResults.value = [
        {
          step_id: "error",
          action: "error",
          status: "failed",
          duration_ms: 0,
          error:
            response.test_result?.error ||
            response.message ||
            "测试失败，未返回详细步骤信息。请查看后端日志。",
          screenshot_base64: null,
        },
      ];
      // 更新统计
      if (testResult.value) {
        testResult.value.steps_total = 1;
        testResult.value.steps_failed = 1;
      }
    }

    if (response.success) {
      ElMessage.success({
        message: `测试通过！成功率：${response.test_result.success_rate}%`,
        duration: 3000,
      });
    } else {
      // 测试失败时也要显示详细步骤
      // Phase 12.5: 增强错误提示信息
      if (response.test_result?.steps_failed > 0) {
        ElMessage.error({
          message: `测试失败：${response.test_result.steps_failed} 个步骤执行失败。请查看下方详情`,
          duration: 5000,
        });
      } else if (response.test_result?.error) {
        ElMessage.warning({
          message: `测试未通过：${response.test_result.error}`,
          duration: 5000,
        });
      } else {
        ElMessage.warning({
          message: `测试失败。请查看下方步骤详情`,
          duration: 5000,
        });
      }
    }
  } catch (error) {
    console.error("组件测试失败:", error);
    ElMessage.error("组件测试失败: " + error.message);
  } finally {
    testing.value = false;
  }
};

const retryTest = () => {
  startTest();
};

const editStep = (stepIndex) => {
  // 关闭测试对话框
  testDialogVisible.value = false;

  // 定位到失败的步骤（高亮显示）
  ElMessage.info(`请修改步骤 ${stepIndex + 1}`);

  // TODO: 可以添加滚动到对应步骤的功能
};

const getStepStatusType = (status) => {
  const types = {
    passed: "success",
    failed: "danger",
    running: "warning",
    pending: "info",
  };
  return types[status] || "info";
};

const getStepStatusIcon = (status) => {
  const icons = {
    passed: "CircleCheck",
    failed: "CircleClose",
    running: "Loading",
    pending: "Clock",
  };
  return icons[status] || "Clock";
};

const getFixSuggestion = (step) => {
  if (!step.error) return "";

  const error = step.error.toLowerCase();

  if (error.includes("timeout")) {
    return "建议：增加timeout值或检查网络延迟";
  } else if (error.includes("not found") || error.includes("unable to find")) {
    return "建议：检查selector是否正确，或添加等待步骤";
  } else if (error.includes("click")) {
    return "建议：元素可能被遮挡，尝试添加滚动或等待动画完成";
  } else if (error.includes("network")) {
    return "建议：检查网络连接或增加重试次数";
  } else {
    return "建议：检查步骤配置是否正确";
  }
};

const saveComponent = async () => {
  try {
    if (!recorderForm.value.componentName) {
      ElMessage.warning("请输入组件名称");
      return;
    }

    const response = await api.post("/collection/recorder/save", {
      platform: recorderForm.value.platform,
      component_type: recorderForm.value.componentType,
      component_name: recorderForm.value.componentName,
      yaml_content: yamlContent.value,
    });

    if (response.success) {
      const versionInfo = response.version_info;

      // 显示版本信息
      ElMessage.success({
        message: `${response.message} (v${versionInfo.version})`,
        duration: 3000,
      });

      // 询问是否跳转到版本管理页
      ElMessageBox.confirm(
        `组件已成功保存并注册为版本 v${versionInfo.version}，是否前往版本管理页查看？`,
        "保存成功",
        {
          confirmButtonText: "前往查看",
          cancelButtonText: "继续录制",
          type: "success",
        }
      )
        .then(() => {
          // 跳转到版本管理页
          window.open("/component-versions", "_blank");
        })
        .catch(() => {
          // 用户选择继续录制，不做任何操作
        });
    }
  } catch (error) {
    console.error("保存组件失败:", error);
    ElMessage.error("保存组件失败: " + error.message);
  }
};

const copyYaml = () => {
  navigator.clipboard.writeText(yamlContent.value);
  ElMessage.success("YAML内容已复制到剪贴板");
};

const loadAccounts = async () => {
  accountsLoading.value = true;
  try {
    // ⭐ Phase 9完善：使用新的账号管理API
    const params = {};

    // 如果已选择平台，只加载该平台的账号
    if (recorderForm.value.platform) {
      params.platform = recorderForm.value.platform;
    }

    const response = await accountsApi.listAccounts(params);

    // 新API直接返回账号数组
    accounts.value = response || [];

    console.log(
      `[ComponentRecorder] 加载了 ${accounts.value.length} 个账号（平台：${
        recorderForm.value.platform || "全部"
      }）`
    );
  } catch (error) {
    console.error("加载账号列表失败:", error);
    ElMessage.error("加载账号列表失败: " + error.message);
    accounts.value = [];
  } finally {
    accountsLoading.value = false;
  }
};

// 生命周期
onMounted(() => {
  // ⭐ Phase 9完善：初始化时不加载账号，等选择平台后再加载
  // 这样可以避免不必要的API调用
  console.log("[ComponentRecorder] 组件已挂载，等待选择平台后加载账号");
});
</script>

<style scoped>
.component-recorder {
  padding: 20px;
  background: #f5f7fa;
  min-height: calc(100vh - 60px);
}

.page-header {
  margin-bottom: 24px;
}

.page-header h1 {
  font-size: 28px;
  font-weight: 600;
  color: #303133;
  margin: 0 0 8px 0;
}

.page-header .subtitle {
  font-size: 14px;
  color: #909399;
  margin: 0;
}

.recorder-content {
  display: grid;
  grid-template-columns: 350px 1fr 400px;
  gap: 20px;
}

.recorder-panel,
.editor-panel,
.yaml-panel {
  height: calc(100vh - 180px);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.recorder-actions {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 24px;
}

.steps-list {
  flex: 1;
  overflow-y: auto;
  padding-right: 8px;
}

.step-item {
  background: #f5f7fa;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 12px;
  transition: all 0.3s;
}

.step-item:hover {
  border-color: #409eff;
  box-shadow: 0 2px 12px rgba(64, 158, 255, 0.15);
}

.step-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e4e7ed;
}

.drag-handle {
  cursor: move;
  font-size: 18px;
  color: #909399;
}

.drag-handle:hover {
  color: #409eff;
}

.step-number {
  font-weight: 600;
  color: #606266;
}

.step-content {
  padding-top: 8px;
}

.yaml-textarea {
  font-family: "Courier New", monospace;
  font-size: 13px;
  line-height: 1.6;
}

:deep(.el-textarea__inner) {
  background: #f5f7fa;
  color: #303133;
}

:deep(.el-card__body) {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* Phase 11: 发现模式样式 */
.discovery-editor {
  flex: 1;
  overflow-y: auto;
  padding-right: 8px;
}

.open-action-section {
  background: #f0f9eb;
  border: 1px solid #e1f3d8;
  border-radius: 8px;
  padding: 16px;
}

.options-section {
  background: #fdf6ec;
  border: 1px solid #faecd8;
  border-radius: 8px;
  padding: 16px;
}

.options-list {
  max-height: 400px;
  overflow-y: auto;
}

.option-item {
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 12px 16px;
  margin-bottom: 8px;
  transition: all 0.2s;
}

.option-item:hover {
  border-color: #e6a23c;
  box-shadow: 0 2px 8px rgba(230, 162, 60, 0.15);
}

.option-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.option-text {
  flex: 1;
  font-weight: 500;
  color: #303133;
}

.option-actions {
  display: flex;
  gap: 4px;
}

.default-option-section {
  background: #ecf5ff;
  border: 1px solid #d9ecff;
  border-radius: 8px;
  padding: 16px;
}

.test-config-section {
  background: #f4f4f5;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 16px;
}

/* Phase 12.3: 步骤标记样式 */
.step-date-picker {
  border-left: 4px solid #e6a23c !important;
  background: #fdf6ec !important;
}

.step-filters {
  border-left: 4px solid #67c23a !important;
  background: #f0f9eb !important;
}

.batch-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
