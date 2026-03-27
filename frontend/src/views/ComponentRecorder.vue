<template>
  <div class="component-recorder">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1>组件录制工具</h1>
      <p class="subtitle">可视化录制和编辑数据采集组件。保存后生成的是草稿版本，不会直接进入正式采集。</p>
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
              placeholder="将根据平台和类型自动生成，保存前可修改（如 export 建议填 orders_export）"
              :disabled="!hasRecordedData"
            >
              <template #append>
                <el-tooltip
                  content="录制后可编辑；export 建议填写如 orders_export 以匹配执行器"
                  placement="top"
                >
                  <el-icon><InfoFilled /></el-icon>
                </el-tooltip>
              </template>
            </el-input>
          </el-form-item>
          <el-form-item
            v-if="recorderForm.componentType === 'login' && hasRecordedData"
            label="登录成功条件"
          >
            <el-input
              v-model="successCriteriaUrlContains"
              placeholder="URL 包含（如 /dashboard 或 home），保存时写入组件内校验"
              clearable
            />
            <div style="font-size: 12px; color: #909399; margin-top: 4px">
              可选。填写后保存时会在组件内加入「登录后 URL 须包含该片段」的校验
            </div>
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

        </div>

        <!-- 录制说明 -->
        <el-alert
          v-if="recorderRuntimeState === 'failed_before_recording'"
          type="error"
          title="录制前检查未通过"
          :closable="false"
          style="margin-top: 20px"
        >
          <p>{{ recorderRuntimeStatus.error_message || "登录门禁未通过，未进入录制阶段" }}</p>
          <p>请先完成自动登录或处理登录异常后，再重新开始录制。</p>
        </el-alert>

        <el-alert
          v-else-if="!isRecording"
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
          <p>6. 保存后请前往版本管理页测试并提升为稳定版，只有稳定版可用于正式采集</p>
        </el-alert>

        <el-alert
          v-else-if="recorderRuntimeState !== 'inspector_recording'"
          type="warning"
          title="录制前检查中"
          :closable="false"
          style="margin-top: 20px"
        >
          <p>{{ recorderRuntimeStatusText }}</p>
          <p>在通过 login gate 之前，系统不会打开真正的录制流程。</p>
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

      <!-- 右侧：步骤编辑与 Python 代码左右分栏 -->
      <div class="steps-and-python-row">
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
            class="batch-actions steps-toolbar"
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
              @click="batchMarkAs('captcha_graphical')"
            >
              图形验证码
            </el-button>
            <el-button
              size="small"
              :disabled="selectedStepIndices.length === 0"
              @click="batchMarkAs('captcha_otp')"
            >
              短信/OTP验证码
            </el-button>
            <el-button
              size="small"
              :disabled="selectedStepIndices.length === 0"
              @click="batchMarkAs('captcha')"
            >
              验证码（兼容）
            </el-button>
            <el-button
              size="small"
              :disabled="selectedStepIndices.length === 0"
              @click="batchMarkAs('navigation')"
            >
              标记为导航
            </el-button>
            <el-button
              size="small"
              :disabled="selectedStepIndices.length === 0"
              @click="batchMarkAs('popup')"
            >
              标记为弹窗/通知栏
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
            <el-divider direction="vertical" />
            <el-select
              v-model="segmentValidationSignal"
              size="small"
              style="width: 180px"
              :disabled="selectedStepIndices.length === 0"
            >
              <el-option label="自动判断信号" value="auto" />
              <el-option label="login_ready" value="login_ready" />
              <el-option label="navigation_ready" value="navigation_ready" />
              <el-option label="date_picker_ready" value="date_picker_ready" />
              <el-option label="filters_ready" value="filters_ready" />
              <el-option label="export_complete" value="export_complete" />
            </el-select>
            <el-button
              size="small"
              type="primary"
              :loading="segmentValidationLoading"
              :disabled="selectedStepIndices.length === 0"
              @click="validateSelectedSegment"
            >
              校验当前段
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
                  'step-captcha-graphical': element.step_group === 'captcha_graphical',
                  'step-captcha-otp': element.step_group === 'captcha_otp',
                  'step-captcha': element.step_group === 'captcha',
                  'step-navigation': element.step_group === 'navigation',
                  'step-popup': element.step_group === 'popup',
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
                  <el-tag
                    v-if="element.step_group === 'captcha_graphical'"
                    size="small"
                    type="warning"
                    style="margin-left: 4px"
                  >
                    图形验证码
                  </el-tag>
                  <el-tag
                    v-if="element.step_group === 'captcha_otp'"
                    size="small"
                    type="warning"
                    style="margin-left: 4px"
                  >
                    短信/OTP
                  </el-tag>
                  <el-tag
                    v-if="element.step_group === 'captcha'"
                    size="small"
                    type="info"
                    style="margin-left: 4px"
                  >
                    验证码
                  </el-tag>
                  <el-tag
                    v-if="element.step_group === 'navigation'"
                    size="small"
                    type="primary"
                    style="margin-left: 4px"
                  >
                    导航
                  </el-tag>
                  <el-tag
                    v-if="element.step_group === 'popup'"
                    size="small"
                    type="info"
                    style="margin-left: 4px"
                  >
                    弹窗
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
                        :rows="1"
                        class="step-selector-input"
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
                        <el-option label="图形验证码" value="captcha_graphical" />
                        <el-option label="短信/OTP验证码" value="captcha_otp" />
                        <el-option label="验证码（兼容）" value="captcha" />
                        <el-option label="导航" value="navigation" />
                        <el-option label="弹窗/通知栏" value="popup" />
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
                      <div
                        v-if="element.step_group === 'captcha_graphical'"
                        style="font-size: 12px; color: #909399; margin-top: 4px"
                      >
                        图形验证码：需截图给用户看后输入；与采集验证码类型 graphical_captcha 一致
                      </div>
                      <div
                        v-if="element.step_group === 'captcha_otp'"
                        style="font-size: 12px; color: #909399; margin-top: 4px"
                      >
                        短信/OTP验证码：用户查收短信或邮件后输入，无需截图；与 verification_type=otp 一致
                      </div>
                      <div
                        v-if="element.step_group === 'captcha'"
                        style="font-size: 12px; color: #909399; margin-top: 4px"
                      >
                        验证码（兼容）：未区分子类型时按图形验证码处理；建议改用「图形验证码」或「短信/OTP验证码」
                      </div>
                      <div
                        v-if="element.step_group === 'navigation'"
                        style="font-size: 12px; color: #409eff; margin-top: 4px"
                      >
                        此步骤为导航/页面跳转，生成器会补充等待与抗干扰钩子
                      </div>
                      <div
                        v-if="element.step_group === 'popup'"
                        style="font-size: 12px; color: #909399; margin-top: 4px"
                      >
                        此步骤为弹窗/通知栏关闭，将生成可选关闭逻辑
                      </div>
                    </el-form-item>
                  </el-form>
                </div>
              </div>
            </template>
          </draggable>

          <el-alert
            v-if="segmentValidationResult"
            :title="
              segmentValidationResult.passed
                ? '当前段校验通过'
                : '当前段校验未通过'
            "
            :type="segmentValidationResult.passed ? 'success' : 'error'"
            :closable="false"
            show-icon
            style="margin-top: 16px"
          >
            <p>
              信号: {{ segmentValidationResult.resolved_signal || "未解析" }}
            </p>
            <p>
              范围: 步骤 {{ segmentValidationResult.step_start }} -
              {{ segmentValidationResult.step_end }}
            </p>
            <p v-if="segmentValidationResult.current_url">
              URL: {{ segmentValidationResult.current_url }}
            </p>
            <p v-if="segmentValidationResult.failure_step_id">
              失败步骤: {{ segmentValidationResult.failure_step_id }}
            </p>
            <p v-if="segmentValidationResult.error_message">
              错误: {{ segmentValidationResult.error_message }}
            </p>
            <div
              v-if="segmentValidationResult.screenshot_url"
              style="margin-top: 12px"
            >
              <img
                :src="segmentValidationResult.screenshot_url"
                alt="片段校验截图"
                style="
                  max-width: 100%;
                  max-height: 220px;
                  border: 1px solid #dcdfe6;
                  border-radius: 4px;
                "
              />
            </div>
            <p
              v-for="(suggestion, idx) in segmentValidationResult.suggestions || []"
              :key="`segment-suggestion-${idx}`"
            >
              建议: {{ suggestion }}
            </p>
          </el-alert>
        </div>

        <!-- 空状态 -->
        <el-empty v-else description="还没有录制任何步骤" :image-size="150">
          <template #image>
            <el-icon :size="80" color="#909399"><Document /></el-icon>
          </template>
        </el-empty>
      </el-card>

      <!-- Python 代码（主路径保存 .py）- 与步骤编辑左右并排 -->
      <el-card class="python-panel" shadow="hover" v-show="hasRecordedData && !isDiscoveryMode">
        <template #header>
          <div class="card-header">
            <span class="card-title">Python 代码</span>
            <el-button
              size="small"
              :disabled="!hasSteps"
              @click="regeneratePython"
            >
              重新生成
            </el-button>
          </div>
        </template>
        <el-alert
          v-if="hasSteps && !pythonCode"
          type="warning"
          :closable="false"
          show-icon
          style="margin-bottom: 12px"
        >
          未生成代码，请点击「重新生成」或检查步骤后重试。
        </el-alert>
        <el-input
          v-model="pythonCode"
          type="textarea"
          :autosize="{ minRows: 12, maxRows: 40 }"
          placeholder="停止录制后将在此显示生成的 Python 代码，可编辑后保存为 .py"
          class="python-textarea"
        />
        <!-- 8.6 lint 分 error/warning 展示，带修复建议 -->
        <div v-if="lintErrors.length > 0 || lintWarnings.length > 0" class="lint-panel" style="margin-top: 12px">
          <div v-if="lintErrors.length > 0" class="lint-errors">
            <div class="lint-title">规范错误（需修复后才能保存）</div>
            <ul>
              <li v-for="(item, idx) in lintErrors" :key="'e-' + idx" class="lint-item lint-error">
                <span class="lint-type">{{ lintErrorLabel(item.type) }}</span>
                {{ item.message }}
              </li>
            </ul>
          </div>
          <div v-if="lintWarnings.length > 0" class="lint-warnings">
            <div class="lint-title">规范建议（可继续保存）</div>
            <ul>
              <li v-for="(item, idx) in lintWarnings" :key="'w-' + idx" class="lint-item lint-warning">
                <span class="lint-type">{{ lintWarningLabel(item.type) }}</span>
                {{ item.message }}
              </li>
            </ul>
          </div>
        </div>
      </el-card>
      </div>
    </div>

    <!-- 测试对话框已迁移至组件版本管理页，此处不再提供「测试组件」入口 -->
    <VerificationResumeDialog
      :visible="Boolean(verificationRequired)"
      :verification-type="verificationRequired?.verificationType || recorderRuntimeStatus.verification_type || ''"
      :screenshot-url="verificationRequired?.screenshotUrl || ''"
      :message="recorderRuntimeStatus.verification_message || ''"
      :expires-at="recorderRuntimeStatus.verification_expires_at || ''"
      :submitting="verificationSubmitting"
      title="录制前登录需要验证码"
      subtitle="当前流程尚未进入正式录制，请在此处完成验证码回填后继续。"
      submit-text="提交并继续"
      cancel-text="取消录制"
      @submit="submitRecorderVerification"
      @cancel="stopRecording"
    />
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
import VerificationResumeDialog from "@/components/verification/VerificationResumeDialog.vue";

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
const recorderRuntimeStatus = ref({
  state: "idle",
  gate_stage: null,
  ready_to_record: false,
  error_message: null,
  verification_type: null,
  verification_screenshot: null,
  verification_id: null,
  verification_message: null,
  verification_expires_at: null,
  verification_attempt_count: 0,
});
const verificationRequired = ref(null);
const verificationSubmitting = ref(false);
const recordedSteps = ref([]);
const accounts = ref([]);
const accountsLoading = ref(false); // ⭐ Phase 9完善：账号加载状态

// 步骤→Python：生成的 Python 代码（主路径保存 .py）
const pythonCode = ref("");

// 登录字段与代码质量提示
const loginFieldSuggestions = ref([]);
const lintErrors = ref([]);
const lintWarnings = ref([]);
// 8.6 lint 类型到简短标签（错误）
const lintErrorLabel = (type) => {
  const map = {
    syntax_error: "[语法]",
    wait_for_timeout_usage: "[固定等待]",
    fixed_sleep_usage: "[固定sleep]",
    count_is_visible_pattern: "[单次检测]",
    swallow_exception_pattern: "[吞错]",
    first_nth_usage: "[.first/.nth]",
  };
  return map[type] || `[${type}]`;
};
// 8.6 lint 类型到简短标签（警告，当前后端已无 warning 项，预留）
const lintWarningLabel = (type) => (type ? `[${type}]` : "");
// 登录成功条件（保存时写入组件）
const successCriteriaUrlContains = ref("");

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
const segmentValidationSignal = ref("auto");
const segmentValidationLoading = ref(false);
const segmentValidationResult = ref(null);

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

const getSelectedSegmentPayload = () => {
  const indices = [...selectedStepIndices.value].sort((a, b) => a - b);
  if (!indices.length) return null;

  for (let i = 1; i < indices.length; i += 1) {
    if (indices[i] !== indices[i - 1] + 1) {
      return { error: "只能校验连续步骤，请重新选择连续区间。" };
    }
  }

  const stepStart = indices[0] + 1;
  const stepEnd = indices[indices.length - 1] + 1;
  const steps = indices.map((index, offset) => {
    const step = recordedSteps.value[index];
    return {
      ...step,
      id: stepStart + offset,
    };
  });

  return { stepStart, stepEnd, steps };
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

const validateSelectedSegment = async () => {
  const payload = getSelectedSegmentPayload();
  if (!payload) {
    ElMessage.warning("请先选择要校验的步骤");
    return;
  }
  if (payload.error) {
    ElMessage.warning(payload.error);
    return;
  }

  segmentValidationLoading.value = true;
  segmentValidationResult.value = null;
  try {
    const response = resolveApiPayload(await api.post("/collection/recorder/validate-segment", {
      platform: recorderForm.value.platform,
      component_type: recorderForm.value.componentType,
      account_id: recorderForm.value.accountId,
      data_domain: recorderForm.value.dataDomain || null,
      sub_domain: recorderForm.value.subDomain || null,
      expected_signal: segmentValidationSignal.value,
      step_start: payload.stepStart,
      step_end: payload.stepEnd,
      steps: payload.steps,
    }));

    if (!response) {
      throw new Error("校验失败");
    }

    segmentValidationResult.value = response || null;
    ElMessage.success("当前段校验已完成");
  } catch (error) {
    const message =
      error.response?.data?.detail ||
      error.response?.data?.error_message ||
      error.message ||
      "校验失败";
    segmentValidationResult.value = {
      passed: false,
      resolved_signal: segmentValidationSignal.value,
      step_start: payload.stepStart,
      step_end: payload.stepEnd,
      validated_steps: payload.steps.length,
      error_message: message,
      suggestions: [],
    };
    ElMessage.error(message);
  } finally {
    segmentValidationLoading.value = false;
  }
};

const recordingStatus = computed(() => {
  if (recorderRuntimeStatus.value.state === "failed_before_recording") {
    return { text: "门禁失败", type: "danger" };
  } else if (recorderRuntimeStatus.value.state === "login_verification_pending") {
    return { text: "等待验证码", type: "warning" };
  } else if (recorderRuntimeStatus.value.state === "inspector_recording") {
    return { text: "录制中", type: "success" };
  } else if (
    isRecording.value &&
    recorderRuntimeStatus.value.state &&
    recorderRuntimeStatus.value.state !== "idle"
  ) {
    return { text: "检查中", type: "warning" };
  } else if (hasSteps.value) {
    return { text: "已完成", type: "info" };
  } else {
    return { text: "未开始", type: "info" };
  }
});

const recorderRuntimeState = computed(
  () => recorderRuntimeStatus.value.state || "idle"
);

const recorderRuntimeStatusText = computed(() => {
  const state = recorderRuntimeStatus.value.state;
  if (state === "starting") return "录制子进程已启动，正在准备浏览器上下文。";
  if (state === "login_checking") return "正在检查当前账号是否已满足登录门禁。";
  if (state === "login_verification_pending")
    return "登录过程需要验证码，提交后系统会继续完成登录门禁。";
  if (state === "login_ready") return "登录门禁已通过，正在进入录制界面。";
  if (state === "inspector_recording") return "浏览器已进入 Inspector 录制状态。";
  if (state === "failed_before_recording") {
    return recorderRuntimeStatus.value.error_message || "录制前检查失败。";
  }
  return "正在准备录制。";
});

const isOtpVerification = computed(() => {
  const verificationType =
    verificationRequired.value?.verificationType ||
    recorderRuntimeStatus.value.verification_type ||
    "";
  return ["otp", "sms", "email_code"].includes(
    String(verificationType).toLowerCase()
  );
});

const resolveApiPayload = (response) => {
  if (response && typeof response === "object" && "success" in response) {
    return response.data ?? response;
  }
  return response;
};

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

// YAML 相关逻辑已废弃，采集组件统一使用 Python 代码作为主输出

// 方法
const startRecording = async () => {
  try {
    isRecording.value = true;
    segmentValidationResult.value = null;
    recorderRuntimeStatus.value = {
      state: "starting",
      gate_stage: "login_gate",
      ready_to_record: false,
      error_message: null,
      verification_type: null,
      verification_screenshot: null,
    };
    verificationRequired.value = null;
    ElMessage.info("录制流程已启动，正在进行录制前检查...");

    const response = resolveApiPayload(await api.post("/collection/recorder/start", {
      platform: recorderForm.value.platform,
      component_type: recorderForm.value.componentType,
      account_id: recorderForm.value.accountId,
    }));

    if (response) {
      recorderRuntimeStatus.value = {
        ...recorderRuntimeStatus.value,
        ...response,
      };

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
    segmentValidationResult.value = null;

    const response = resolveApiPayload(await api.post("/collection/recorder/stop"));

    if (response) {
      isRecording.value = false;

      // Phase 11: 根据模式处理不同的响应
      if (response.mode === "discovery") {
        // 发现模式
        recordingMode.value = "discovery";
        openAction.value = response.open_action;
        availableOptions.value = response.available_options || [];
        defaultOption.value = response.default_option || "";
        recordedSteps.value = []; // 清空步骤
        pythonCode.value = "";

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

        if (response.platform) recorderForm.value.platform = response.platform;
        if (response.component_type)
          recorderForm.value.componentType = response.component_type;

        if (response.steps && response.steps.length > 0) {
          recordedSteps.value = response.steps;
          pythonCode.value = response.python_code || "";

          // 登录字段建议与代码质量提示
          loginFieldSuggestions.value =
            response.login_field_suggestions || [];
          lintErrors.value = response.lint_errors || [];
          lintWarnings.value = response.lint_warnings || [];

          if (lintErrors.value.length > 0) {
            ElMessage.error(
              "生成的代码存在规范错误，请根据下方提示修复后再保存。"
            );
          } else if (!pythonCode.value) {
            ElMessage.warning(
              "未生成代码，请检查步骤或使用「重新生成」按钮"
            );
          } else {
            ElMessage.success(
              `录制完成，共记录 ${response.steps.length} 个步骤`
            );
            if (loginFieldSuggestions.value?.length) {
              ElMessage.info(
                `已根据录制内容为登录字段应用账号变量（共 ${
                  loginFieldSuggestions.value.length
                } 处），可在下方代码中查看。`
              );
            }
            if (lintWarnings.value?.length) {
              ElMessage.warning(
                `生成的代码存在 ${lintWarnings.value.length} 条规范建议，可根据提示逐步优化。`
              );
            }
          }
        } else {
          recordedSteps.value = [];
          pythonCode.value = "";
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
      const statusResponse = resolveApiPayload(await api.get("/collection/recorder/status"));
      if (statusResponse) {
        recorderRuntimeStatus.value = {
          ...recorderRuntimeStatus.value,
          ...statusResponse,
        };
        if (statusResponse.state === "login_verification_pending") {
          const base = (import.meta.env.VITE_API_BASE_URL || "/api").replace(
            /\/$/,
            ""
          );
          verificationRequired.value = {
            verificationType:
              statusResponse.verification_type || "graphical_captcha",
            screenshotUrl: `${base}/collection/recorder/verification-screenshot?ts=${Date.now()}`,
          };
        } else if (statusResponse.state !== "failed_before_recording") {
          verificationRequired.value = null;
        }
        if (statusResponse.state === "failed_before_recording") {
          isRecording.value = false;
          stopPollingSteps();
          ElMessage.error(
            statusResponse.error_message || "录制前检查失败，未进入录制阶段"
          );
          return;
        }
      }

      const response = resolveApiPayload(await api.get("/collection/recorder/steps"));

      if (response) {
        recordedSteps.value = response.steps || [];
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

const submitRecorderVerification = async (submittedValue) => {
  const verificationValue = String(submittedValue || "").trim();
  if (!verificationValue) return;
  verificationSubmitting.value = true;
  try {
    const payload = isOtpVerification.value
      ? { otp: verificationValue }
      : { captcha_code: verificationValue };
    await api.post("/collection/recorder/resume", payload);
    ElMessage.success("验证码已提交，录制前检查将继续执行");
    verificationRequired.value = null;
    recorderRuntimeStatus.value = {
      ...recorderRuntimeStatus.value,
      state: "login_checking",
      error_message: null,
    };
  } catch (error) {
    ElMessage.error(
      error.response?.data?.detail || error.message || "验证码提交失败"
    );
  } finally {
    verificationSubmitting.value = false;
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

const regeneratePython = async () => {
  if (!recordedSteps.value.length) {
    ElMessage.warning("暂无步骤，无法重新生成");
    return;
  }
  try {
    const genPayload = {
      platform: recorderForm.value.platform,
      component_type: recorderForm.value.componentType,
      component_name: recorderForm.value.componentName,
      steps: recordedSteps.value,
    };
    // 8.7 与 save 请求体一致：export 时传 data_domain/sub_domain，避免子域语义漂移
    if (recorderForm.value.componentType === "export") {
      if (recorderForm.value.dataDomain) genPayload.data_domain = recorderForm.value.dataDomain;
      if (recorderForm.value.dataDomain === "services" && recorderForm.value.subDomain) {
        genPayload.sub_domain = recorderForm.value.subDomain;
      }
    }
    const res = resolveApiPayload(await api.post("/collection/recorder/generate-python", genPayload));
    if (res?.python_code) {
      pythonCode.value = res.python_code;
      loginFieldSuggestions.value = res.login_field_suggestions || [];
      lintErrors.value = res.lint_errors || [];
      lintWarnings.value = res.lint_warnings || [];

      if (lintErrors.value.length > 0) {
        ElMessage.error(
          "生成的代码存在规范错误，请根据下方提示修复后再保存。"
        );
      } else {
        ElMessage.success("已重新生成 Python 代码");
        if (lintWarnings.value?.length) {
          ElMessage.warning(
            `生成的代码存在 ${lintWarnings.value.length} 条规范建议，可根据提示逐步优化。`
          );
        }
      }
    } else {
      ElMessage.warning("重新生成失败");
    }
  } catch (e) {
    console.error("重新生成 Python 失败:", e);
    ElMessage.error("重新生成失败: " + (e.message || "未知错误"));
  }
};

const saveComponent = async () => {
  try {
    if (!pythonCode.value || !pythonCode.value.trim()) {
      ElMessage.warning("当前只支持保存 Python 组件，请先生成或编辑 Python 代码");
      return;
    }
    if (recorderForm.value.componentType === "export" && !recorderForm.value.dataDomain) {
      ElMessage.warning("导出组件必须选择数据域");
      return;
    }

    const payload = {
      platform: recorderForm.value.platform,
      component_type: recorderForm.value.componentType,
    };
    if (recorderForm.value.componentType === "export") {
      payload.data_domain = recorderForm.value.dataDomain;
      if (recorderForm.value.dataDomain === "services" && recorderForm.value.subDomain) {
        payload.sub_domain = recorderForm.value.subDomain;
      }
    }
    payload.python_code = pythonCode.value.trim();
    if (
      recorderForm.value.componentType === "login" &&
      successCriteriaUrlContains.value &&
      successCriteriaUrlContains.value.trim()
    ) {
      payload.success_criteria = {
        url_contains: successCriteriaUrlContains.value.trim(),
      };
    }

    const response = resolveApiPayload(await api.post("/collection/recorder/save", payload));

    if (response) {
      const versionInfo = response.version_info;

      // 显示版本信息
      ElMessage.success({
        message: `${response.message} (v${versionInfo.version})`,
        duration: 3000,
      });

      // 询问是否前往组件版本管理并测试
      ElMessageBox.confirm(
        `组件已成功保存并注册为版本 v${versionInfo.version}。是否前往组件版本管理页并执行测试？`,
        "保存成功",
        {
          confirmButtonText: "前往版本管理并测试",
          cancelButtonText: "继续录制",
          type: "success",
        }
      )
        .then(() => {
          window.open("/component-versions", "_blank");
        })
        .catch(() => {
          // 用户选择继续录制，不做任何操作
        });
    }
  } catch (error) {
    console.error("保存组件失败:", error);
    const msg = error?.response?.data?.message || error?.message || "保存失败";
    ElMessage.error("保存组件失败: " + msg);
    // 7.3.2：服务端因 lint 阻断时，展示错误详情以便用户修复
    const payload = error?.response?.data?.data;
    if (payload?.lint_errors?.length) {
      lintErrors.value = payload.lint_errors;
      lintWarnings.value = payload.lint_warnings || [];
    }
  }
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
  grid-template-columns: 350px 1fr;
  gap: 20px;
}

/* 步骤编辑与 Python 代码左右分栏，合理分配宽度 */
.steps-and-python-row {
  display: flex;
  gap: 16px;
  min-width: 0;
  flex: 1;
  height: calc(100vh - 180px);
}

.recorder-panel,
.editor-panel,
.python-panel {
  height: calc(100vh - 180px);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.editor-panel {
  flex: 1 1 42%;
  min-width: 280px;
  max-width: 100%;
}

.python-panel {
  flex: 1;
  min-width: 0;
  margin-top: 0;
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

.steps-toolbar {
  position: sticky;
  top: 0;
  z-index: 5;
}

.step-item {
  background: #f5f7fa;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 8px;
  transition: all 0.3s;
}

.step-item:hover {
  border-color: #409eff;
  box-shadow: 0 2px 12px rgba(64, 158, 255, 0.15);
}

.step-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  padding-bottom: 8px;
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
  font-size: 13px;
  font-weight: 600;
  color: #606266;
}

.step-selector-input :deep(textarea) {
  min-height: 32px;
}

.step-content {
  padding-top: 8px;
}

.python-panel :deep(.el-card__body) {
  min-height: 0;
  overflow: auto;
}

.python-textarea {
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

.step-navigation {
  border-left: 4px solid #409eff !important;
  background: #ecf5ff !important;
}

.step-popup {
  border-left: 4px solid #909399 !important;
  background: #f4f4f5 !important;
}

.batch-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

/* 8.6 lint 错误/建议面板 */
.lint-panel {
  font-size: 13px;
  border-radius: 6px;
  padding: 10px 12px;
  background: #fdf6ec;
  border: 1px solid #faecd8;
}
.lint-panel .lint-errors {
  margin-bottom: 8px;
}
.lint-panel .lint-errors:last-child,
.lint-panel .lint-warnings:last-child {
  margin-bottom: 0;
}
.lint-title {
  font-weight: 600;
  margin-bottom: 6px;
  color: #303133;
}
.lint-errors .lint-title {
  color: #f56c6c;
}
.lint-warnings .lint-title {
  color: #e6a23c;
}
.lint-panel ul {
  margin: 0;
  padding-left: 18px;
}
.lint-item {
  margin-bottom: 4px;
  line-height: 1.5;
}
.lint-item.lint-error {
  color: #c45656;
}
.lint-item.lint-warning {
  color: #b88230;
}
.lint-type {
  font-weight: 600;
  margin-right: 6px;
}
</style>
