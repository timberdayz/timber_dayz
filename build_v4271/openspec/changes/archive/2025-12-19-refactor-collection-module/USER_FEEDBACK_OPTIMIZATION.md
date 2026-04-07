# 用户反馈优化总结

**日期**: 2025-12-11  
**反馈来源**: 实际采集模块运行测试  
**状态**: 已更新到 proposal.md 和 tasks.md

---

## 📋 问题与优化需求

### 1. 配置命名自动化 ⭐

**问题**: 配置名需要用户手动输入，容易出错且不统一

**解决方案**:
- 采用 `{platform}-{domain(s)}-v{n}` 命名规则
- 示例: `shopee-orders-v1`, `tiktok-analytics-products-v2`
- 版本号按 `平台 + 数据域组合` 自动递增
- 允许用户创建后手动修改

**前端实现**:
```javascript
function generateConfigName(platform, dataDomains, existingConfigs) {
  const domainStr = dataDomains.sort().join('-')
  const baseName = `${platform}-${domainStr}`
  
  // 查找现有版本号
  const existingVersions = existingConfigs
    .filter(c => c.name.startsWith(baseName))
    .map(c => {
      const match = c.name.match(/-v(\d+)$/)
      return match ? parseInt(match[1]) : 0
    })
  
  const nextVersion = Math.max(0, ...existingVersions) + 1
  return `${baseName}-v${nextVersion}`
}
```

---

### 2. 服务子域灵活选择 ⭐

**问题**: services 域有 agent/ai_assistant 两个子类型，但只能单选

**解决方案**:
- 改为 Checkbox 组，支持多选（数组）
- 新增"全选"快捷按钮
- 执行时按数组顺序依次采集

**数据模型变更**:
```python
# CollectionConfig / CollectionTask
sub_domains: List[str]  # 改为数组（原 sub_domain 字符串）

# 示例
sub_domains: ['agent', 'ai_assistant']
```

**前端实现**:
```vue
<el-checkbox-group v-model="form.sub_domains">
  <el-checkbox label="agent">人工客服</el-checkbox>
  <el-checkbox label="ai_assistant">智能客服</el-checkbox>
</el-checkbox-group>
<el-button size="small" @click="form.sub_domains = ['agent', 'ai_assistant']">
  全选
</el-button>
```

---

### 3. 日期选择平台对齐 ⭐

**问题**: 
- 前端有"粒度"(daily/weekly/monthly) + "日期范围"两个选项
- 但电商平台的日期控件是预设选项（无法选择周度粒度+30天）

**解决方案**:
- **移除独立的 granularity 选择器**（前端不显示，后端保留用于推断）
- 使用平台感知的日期预设

**平台日期预设**:
| 平台 | 日期预设选项 |
|------|------------|
| Shopee | 今天、昨天、最近7天、最近30天、自定义 |
| TikTok | 今天、昨天、最近7天、最近28天、自定义 |
| 妙手ERP | 今天、昨天、最近7天、最近30天、自定义 |

**前端实现**:
```javascript
const DATE_PRESETS = {
  shopee: [
    { label: '今天', value: 'today' },
    { label: '昨天', value: 'yesterday' },
    { label: '最近7天', value: 'last_7_days' },
    { label: '最近30天', value: 'last_30_days' },
    { label: '自定义', value: 'custom' },
  ],
  tiktok: [
    { label: '今天', value: 'today' },
    { label: '昨天', value: 'yesterday' },
    { label: '最近7天', value: 'last_7_days' },
    { label: '最近28天', value: 'last_28_days' },
    { label: '自定义', value: 'custom' },
  ],
  miaoshou: [
    { label: '今天', value: 'today' },
    { label: '昨天', value: 'yesterday' },
    { label: '最近7天', value: 'last_7_days' },
    { label: '最近30天', value: 'last_30_days' },
    { label: '自定义', value: 'custom' },
  ],
}

computed: {
  datePresetsForPlatform() {
    return DATE_PRESETS[form.platform] || []
  }
}
```

---

### 4. 录制工具前端化 ⭐

**问题**: 录制需要执行命令行，对管理员不够友好

**解决方案**: 前端"录制新组件"按钮

**交互流程**:
```
用户点击 → 弹窗选择参数 → 生成命令 → 一键复制 → 终端执行
```

**前端实现**:
```vue
<!-- 录制弹窗 -->
<el-dialog title="录制新组件">
  <el-form>
    <el-form-item label="平台">
      <el-select v-model="recordForm.platform">
        <el-option label="Shopee" value="shopee" />
        <el-option label="TikTok" value="tiktok" />
        <el-option label="妙手ERP" value="miaoshou" />
      </el-select>
    </el-form-item>
    
    <el-form-item label="组件类型">
      <el-select v-model="recordForm.component">
        <el-option label="登录" value="login" />
        <el-option label="订单导出" value="orders_export" />
        <!-- ... -->
      </el-select>
    </el-form-item>
    
    <el-form-item label="测试账号">
      <el-select v-model="recordForm.account">
        <!-- 从 /api/collection/accounts 获取 -->
      </el-select>
    </el-form-item>
    
    <el-form-item label="录制命令">
      <el-input v-model="generatedCommand" readonly>
        <template #append>
          <el-button @click="copyCommand">复制</el-button>
        </template>
      </el-input>
    </el-form-item>
  </el-form>
</el-dialog>

<script>
const generatedCommand = computed(() => {
  const { platform, component, account, skipLogin } = recordForm
  let cmd = `python tools/record_component.py -p ${platform} -c ${component} -a ${account}`
  if (skipLogin) cmd += ' --skip-login'
  return cmd
})
</script>
```

---

### 5. 任务创建粒度优化 ⭐

**问题**: 旧设计每个账号×数据域创建一个任务，浏览器启动开销大

**解决方案**: 一账号一任务（中粒度）

**设计**:
- 一个任务 = 一个账号 + 该配置的所有数据域
- 一次登录后循环采集所有数据域（浏览器复用）
- 部分成功机制：单个数据域失败不影响其他域

**数据库字段**:
```python
class CollectionTask:
    # 任务粒度字段
    data_domains: List[str]  # ['orders', 'products', ...]
    sub_domains: List[str]   # ['agent', 'ai_assistant']
    
    # 进度跟踪
    total_domains: int              # 总数据域数量
    completed_domains: List[str]    # ['orders', 'products']
    failed_domains: List[Dict]      # [{'domain': 'finance', 'error': '超时'}]
    current_domain: str             # 'analytics'
    
    # 状态
    status: str  # completed / partial_success / failed
```

**执行逻辑**:
```python
async def execute_task(task):
    # 1. 登录
    await execute_component('login')
    
    # 2. 循环采集所有数据域
    for domain in task.data_domains:
        try:
            await execute_component(f'{domain}_export')
            task.completed_domains.append(domain)
        except Exception as e:
            task.failed_domains.append({'domain': domain, 'error': str(e)})
            continue  # 继续下一个数据域
    
    # 3. 状态判定
    if len(task.failed_domains) == 0:
        task.status = 'completed'
    elif len(task.completed_domains) > 0:
        task.status = 'partial_success'
    else:
        task.status = 'failed'
```

**性能提升**:
- 浏览器启动次数：3账号 × 7域 = 21次 → 3次（**减少86%**）
- 登录次数：21次 → 3次
- 执行时间：估计减少 50-60%

---

### 6. 定时调度时间优化 ⭐

**需求确认**:
- **日度实时**：每天4次（06:00, 12:00, 18:00, 22:00）采集"今天"数据
- **周度汇总**：每周一 05:00 采集"最近7天"数据
- **月度汇总**：每月1号 05:00 采集"最近30天"数据

**Cron 表达式**:
```python
SCHEDULE_TEMPLATES = {
    'daily_realtime': {
        'cron': '0 6,12,18,22 * * *',  # 每天4次
        'date_range': 'today',
        'description': '日度实时监控'
    },
    'weekly': {
        'cron': '0 5 * * 1',  # 每周一 05:00
        'date_range': 'last_7_days',
        'description': '周度数据汇总'
    },
    'monthly': {
        'cron': '0 5 1 * *',  # 每月1号 05:00
        'date_range': 'last_30_days',
        'description': '月度数据汇总'
    }
}
```

**原因**:
- 日度4次：实时监控当日销售趋势
- 周度/月度早上5点：避开夜间网站维护时间

---

### 7. 快速配置功能 ⭐

**需求**: 3步向导，一键创建标准定时采集配置

**功能设计**:

#### 步骤1：选择平台
```vue
<el-radio-group v-model="quickForm.platform">
  <el-radio-button label="shopee">
    Shopee <el-tag size="small">3个账号</el-tag>
  </el-radio-button>
  <el-radio-button label="tiktok">
    TikTok <el-tag size="small">2个账号</el-tag>
  </el-radio-button>
  <el-radio-button label="miaoshou">
    妙手ERP <el-tag size="small">1个账号</el-tag>
  </el-radio-button>
</el-radio-group>
```

#### 步骤2：选择策略
```vue
<el-radio-group v-model="quickForm.strategy">
  <el-radio label="standard">标准策略（推荐）</el-radio>
  <el-radio label="custom">自定义选择</el-radio>
</el-radio-group>

<!-- 标准策略说明 -->
<el-alert v-if="quickForm.strategy === 'standard'">
  标准策略将创建以下配置：
  ✓ 日度实时监控：每天4次（06:00, 12:00, 18:00, 22:00）
  ✓ 周度数据汇总：每周一 05:00
  ✓ 月度数据汇总：每月1号 05:00
</el-alert>

<!-- 自定义选择 -->
<el-checkbox-group v-if="quickForm.strategy === 'custom'">
  <el-checkbox label="daily">日度实时监控</el-checkbox>
  <el-checkbox label="weekly">周度数据汇总</el-checkbox>
  <el-checkbox label="monthly">月度数据汇总</el-checkbox>
</el-checkbox-group>
```

#### 步骤3：确认创建
```vue
<el-table :data="previewConfigs">
  <el-table-column label="配置名称" prop="name" />
  <el-table-column label="执行频率" prop="schedule" />
  <el-table-column label="数据范围" prop="dateRange" />
</el-table>

<el-descriptions>
  <el-descriptions-item label="采集账号">
    3个活跃账号
  </el-descriptions-item>
  <el-descriptions-item label="数据域">
    6个（全部数据域）
  </el-descriptions-item>
  <el-descriptions-item label="预计任务">
    日度：3 × 4次 = 12任务/天
    周度：3任务/周
    月度：3任务/月
  </el-descriptions-item>
</el-descriptions>
```

**创建逻辑**:
```javascript
async function createQuickConfigs() {
  const templates = {
    daily: {
      name: `${platform}-all-domains-daily-realtime`,
      date_range_type: 'today',
      schedule_cron: '0 6,12,18,22 * * *',
    },
    weekly: {
      name: `${platform}-all-domains-weekly`,
      date_range_type: 'last_7_days',
      schedule_cron: '0 5 * * 1',
    },
    monthly: {
      name: `${platform}-all-domains-monthly`,
      date_range_type: 'last_30_days',
      schedule_cron: '0 5 1 * *',
    }
  }

  for (const type of ['daily', 'weekly', 'monthly']) {
    await collectionApi.createConfig({
      name: templates[type].name,
      platform: platform,
      account_ids: [],  // 空数组表示使用所有活跃账号
      data_domains: ['orders', 'products', 'services', 'analytics', 'finance', 'inventory'],
      sub_domains: ['agent', 'ai_assistant'],
      date_range_type: templates[type].date_range_type,
      schedule_enabled: true,
      schedule_cron: templates[type].schedule_cron,
    })
  }
}
```

---

## 🎯 实施优先级

| 优化点 | 优先级 | 预计工时 | 依赖 | 状态 |
|--------|--------|---------|------|------|
| 1. 配置命名自动化 | P0 | 0.5天 | 无 | 待开发 |
| 2. 日期选择平台对齐 | P0 | 1天 | 无 | 待开发 |
| 3. 服务子域多选 | P0 | 0.5天 | 数据库迁移 | 待开发 |
| 4. 任务粒度优化 | P0 | 2天 | 数据库迁移 + 执行引擎 | 待开发 |
| 5. 定时调度时间 | P1 | 0.5天 | 调度器 | 待开发 |
| 6. 快速配置功能 | P1 | 2天 | 无 | 待开发 |
| 7. 录制工具前端化 | P2 | 1天 | 无 | 待开发 |
| **8. 环境感知浏览器配置** | **P1** | **0.5天** | **无** | **待开发** ⭐ |

**总预计工时**: 8 天

**已完善功能**（无需开发）:
- ✅ 弹窗自动处理（三层机制）
- ✅ 平台导出策略差异支持（组件化）
- ✅ 文件下载识别（Playwright API）

---

## 📊 预期收益

### 用户体验提升
- ✅ **零配置入门**：快速配置功能，3步完成标准定时采集
- ✅ **命名规范统一**：自动生成配置名，避免手动输入错误
- ✅ **日期选择直观**：与平台控件一致，符合心智模型
- ✅ **灵活子域选择**：支持多选+全选，适应不同需求
- ✅ **录制工具友好**：前端生成命令一键复制，降低门槛

### 技术收益
- ✅ **性能优化**：任务粒度优化，浏览器启动减少86%，执行时间减少50-60%
- ✅ **容错增强**：部分成功机制，单域失败不影响其他域
- ✅ **维护性提升**：平台感知的日期预设，易于扩展新平台

### 运维收益
- ✅ **自动化运维**：标准定时调度，日度4次+周度+月度
- ✅ **预计任务可见**：快速配置时显示预计任务数，避免系统过载
- ✅ **实时进度监控**：显示已完成/失败的数据域，故障诊断更快

---

---

### 8. 采集过程问题确认（2025-12-11补充）⭐

基于实际运行反馈，确认以下4个核心问题的解决方案：

#### 问题8.1: 临时弹窗处理 ✅ 已完善

**现状**: 系统已实现三层弹窗处理机制

**实现细节**:
- **第1层**：通用弹窗处理器（30+选择器）
  - 位置：`modules/apps/collection_center/popup_handler.py`
  - 覆盖：关闭按钮、取消按钮、X按钮、"稍后再说"、"我知道了"等
- **第2层**：平台特定配置
  - 位置：`config/collection_components/{platform}/popup_config.yaml`
  - 内容：平台专属选择器、轮询策略
- **第3层**：组件级控制
  - 配置：组件YAML中的 `popup_handling` 配置
  - 时机：组件前后、步骤前后、错误时

**执行时机**：
- 组件执行前后自动检查（可配置）
- 每个步骤执行前后检查
- 错误时检查（可能是弹窗遮挡）

**兜底策略**：
- 点击关闭按钮
- ESC键关闭
- 支持iframe内弹窗

**结论**: 无需额外开发

#### 问题8.2: 平台导出策略差异 ✅ 已支持

**现状**: 组件化设计天然支持平台差异

**支持的策略**:
1. **直接下载**（Shopee/TikTok）
   - 点击导出 → 确认 → 立即下载
2. **生成后下载**（妙手ERP）
   - 请求生成 → 等待完成 → 刷新列表 → 选择最新 → 下载
3. **异步下载**（Amazon等）
   - 请求报告 → 后台处理 → 进入列表 → 找到最新 → 下载

**关键特性**:
- 每个平台独立的export组件YAML
- 支持复杂的多步骤流程
- 支持轮询等待（`poll_interval`）
- 支持可选步骤（`optional: true`）

**结论**: 无需额外开发

#### 问题8.3: 文件下载识别 ✅ 已可靠

**现状**: 使用Playwright Download API确保可靠性

**实现机制**:
```python
# Playwright自动监听下载事件
async with page.expect_download(timeout=timeout) as download_info:
    pass

download = await download_info.value
await download.save_as(file_path)  # 确保完整下载
```

**可靠性保证**:
- ✅ 自动等待下载开始
- ✅ 等待浏览器完成下载
- ✅ 验证文件完整性
- ✅ 移动到指定目录
- ✅ 无 .crdownload 临时文件残留

**文件流程**:
1. 临时下载：`temp/downloads/{task_id}/`
2. 标准化命名：`{platform}_{domain}_{date}_{granularity}.xlsx`
3. 移动到最终位置：`data/raw/2025/`
4. 注册到catalog_files表

**结论**: 无需额外开发

#### 问题8.4: 有头/无头模式 ⚠️ 需优化

**问题**: 当前代码多处硬编码 `headless=False`，无法根据环境切换

**需求**:
- 开发环境：有头模式（便于观察和调试）
- 生产环境：无头模式（Docker部署）
- 支持临时切换：生产环境调试时临时有头

**解决方案**: 环境变量驱动 + 调试模式覆盖

```python
# 配置类
class Settings:
    ENVIRONMENT: str = 'development'  # or 'production'
    PLAYWRIGHT_HEADLESS: bool = False  # 开发默认
    PLAYWRIGHT_SLOW_MO: int = 100
    
    @property
    def browser_config(self):
        if self.ENVIRONMENT == 'production':
            return {'headless': True, 'slow_mo': 0}
        else:
            return {'headless': self.PLAYWRIGHT_HEADLESS, 'slow_mo': self.PLAYWRIGHT_SLOW_MO}

# 执行引擎
browser = await playwright.chromium.launch(**settings.browser_config)

# 调试模式覆盖（API参数）
if task.debug_mode:
    browser_config['headless'] = False
```

**实施任务**:
- Task 1.7.1: 实现环境感知配置类
- Task 1.7.2: 执行引擎使用环境配置
- Task 1.7.3: 支持调试模式覆盖（API + 数据库字段）
- Task 1.7.4: 前端调试开关
- Task 1.7.5: 清理现有硬编码

**预计工时**: 0.5天

---

## ✅ 验证清单

### 原有优化（V29-V37）
- [ ] V29: 配置名自动生成正确（`{platform}-{domains}-v{n}`格式）
- [ ] V30: 日期选择平台对齐（移除granularity，使用平台预设）
- [ ] V31: 服务子域多选正常（agent + ai_assistant）
- [ ] V32: 快速配置功能正常（3步创建日度+周度+月度）
- [ ] V33: 录制工具前端入口正常（生成命令+复制）
- [ ] V34: 任务粒度优化正常（一账号一任务，浏览器复用）
- [ ] V35: 部分成功机制正常（单域失败不影响其他域）
- [ ] V36: 日度4次定时调度正常（06:00/12:00/18:00/22:00）
- [ ] V37: 周度/月度调度时间正确（周一05:00，月初05:00）

### 采集过程验证（V38-V42）⭐
- [x] V38: 弹窗自动处理正常（三层机制已实现）✅
- [x] V39: 平台导出策略差异支持（组件化天然支持）✅
- [x] V40: 文件下载识别可靠（Playwright Download API）✅
- [ ] V41: 环境感知浏览器配置正常（开发有头，生产无头）
- [ ] V42: 调试模式覆盖正常（前端开关→API参数→有头模式）

---

## 📝 备注

- 所有优化已同步到 `proposal.md` 和 `tasks.md`
- 数据库迁移脚本需要在实施阶段创建
- 快速配置功能可作为独立功能优先实施（不依赖其他优化）
- **问题8.1-8.3已完善，仅问题8.4需要开发**（0.5天工时）

