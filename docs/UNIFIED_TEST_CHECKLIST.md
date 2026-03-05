# 统一测试清单 - 2025-12-19

## 📋 测试概述

**目的**: 验证所有已实现功能的正确性  
**测试人员**: 用户手动执行  
**预计时间**: 2-3小时  
**前置条件**: 
- 系统已启动（`python run.py`）
- 数据库已迁移
- 前端已启动（`npm run dev`）
- 至少有一个测试账号配置

---

## 🎯 测试分类

### 类别1：Phase 2.5容错机制测试（优先级最高）⭐⭐⭐

#### 测试1.1: Optional参数测试
**目标**: 验证optional步骤在元素不存在时正确跳过

**步骤**:
1. 创建测试组件（Python：`modules/platforms/test/components/optional_test.py`，或若项目仍支持 YAML 则 `config/collection_components/test/optional_test.yaml`）:
```yaml
name: test_optional
platform: test
type: navigation
steps:
  - action: navigate
    url: "https://www.example.com"
  
  - action: click
    selector: ".non-existent-popup"
    optional: true
    timeout: 1000
  
  - action: wait
    type: timeout
    duration: 1000
```

2. 使用`tools/test_component.py`测试组件
3. **预期结果**: 第2步跳过，不报错，继续执行第3步

**验证点**:
- [ ] 日志显示"Element not found, but step is optional, skipping"
- [ ] 组件执行成功
- [ ] 没有抛出异常

---

#### 测试1.2: Smart Wait自适应等待测试
**目标**: 验证4层等待策略

**步骤**:
1. 创建测试组件YAML:
```yaml
steps:
  - action: wait
    type: selector
    selector: "body"
    smart_wait: true
    timeout: 30000
```

2. 测试组件
3. **预期结果**: 快速检测到body元素（1秒内）

**验证点**:
- [ ] 日志显示"Smart wait: Element 'body' found quickly"
- [ ] 等待时间<2秒

---

#### 测试1.3: Fallback降级策略测试
**目标**: 验证primary失败后使用fallback

**步骤**:
1. 创建测试组件YAML:
```yaml
steps:
  - action: click
    selector: ".non-existent-button"
    fallback_methods:
      - selector: "body"
        description: "备用元素"
```

2. 测试组件
3. **预期结果**: Primary失败，Fallback成功

**验证点**:
- [ ] 日志显示"Primary method failed"
- [ ] 日志显示"Fallback method succeeded"
- [ ] 组件执行成功

---

#### 测试1.4: Retry重试机制测试
**目标**: 验证步骤失败后自动重试

**步骤**:
1. 创建测试组件YAML:
```yaml
steps:
  - action: click
    selector: ".slow-loading-button"
    retry:
      max_attempts: 3
      delay: 2000
      on_retry: wait
```

2. 测试组件（模拟慢加载）
3. **预期结果**: 重试后成功

**验证点**:
- [ ] 日志显示重试次数
- [ ] 最终成功或达到最大重试次数

---

### 类别2：Phase 2.1录制工具测试 ⭐⭐

#### 测试2.1: 自动登录功能测试
**目标**: 验证录制非login组件时自动执行login

**步骤**:
1. 确保已有`{platform}/login.yaml`组件
2. 运行录制工具:
```bash
python tools/record_component.py --platform shopee --component navigation --account YOUR_ACCOUNT
```

3. **预期结果**: 自动执行login组件，然后进入录制模式

**验证点**:
- [ ] 日志显示"Executing login component"
- [ ] 浏览器自动登录
- [ ] Inspector自动打开

---

#### 测试2.2: Playwright Inspector测试
**目标**: 验证Inspector正确捕获操作

**步骤**:
1. 运行录制工具
2. 在浏览器中执行2-3个操作（点击、输入）
3. 在Inspector中点击Resume
4. 检查生成的YAML文件

**预期结果**: YAML包含所有操作

**验证点**:
- [ ] Inspector窗口打开
- [ ] 操作被记录
- [ ] YAML文件包含正确的步骤

---

#### 测试2.3: Trace录制测试
**目标**: 验证Trace文件正确生成

**步骤**:
1. 运行录制工具（默认启用trace）
2. 执行一些操作
3. 完成录制
4. 检查`temp/traces/`目录

**预期结果**: Trace文件存在且可用

**验证点**:
- [ ] Trace文件生成（.zip格式）
- [ ] 日志显示trace保存路径
- [ ] 可以使用`playwright show-trace`查看

---

### 类别3：Phase 4.1.6 Cron预设测试 ⭐

#### 测试3.1: Cron验证API测试
**目标**: 验证Cron表达式验证功能

**步骤**:
1. 打开前端界面
2. 创建/编辑采集配置
3. 输入Cron表达式: `0 6,12,18,22 * * *`
4. 点击验证

**预期结果**: 显示"日度实时（每天4次：6点/12点/18点/22点）"

**验证点**:
- [ ] 验证成功
- [ ] 显示人类可读描述
- [ ] 无效表达式显示错误

---

#### 测试3.2: Cron预设测试
**目标**: 验证预设选项正确

**步骤**:
1. 打开前端调度配置
2. 查看预设选项列表
3. 选择"日度实时"预设

**预期结果**: 自动填充`0 6,12,18,22 * * *`

**验证点**:
- [ ] 预设列表包含：daily_realtime, weekly_summary, monthly_summary
- [ ] 选择预设后自动填充Cron表达式
- [ ] 显示正确的描述

---

### 类别4：Phase 1.5.6 截图API测试 ⭐

#### 测试4.1: 任务截图API测试
**目标**: 验证截图API正确返回图片

**步骤**:
1. 创建一个任务并触发验证码
2. 记录任务ID
3. 访问: `http://localhost:8000/api/collection/tasks/{task_id}/screenshot`

**预期结果**: 浏览器显示截图图片

**验证点**:
- [ ] API返回200状态码
- [ ] 返回PNG图片
- [ ] 图片可以正常显示

---

### 类别5：Shopee组件录制测试（需要实际账号）⚠️

#### 测试5.1: 录制Shopee服务导出组件
**步骤**:
1. 运行录制工具:
```bash
python tools/record_component.py --platform shopee --component services_export --account YOUR_ACCOUNT
```

2. 在浏览器中执行导出操作
3. 完成录制

**验证点**:
- [ ] 自动登录成功
- [ ] 操作被正确录制
- [ ] YAML文件生成

---

#### 测试5.2: 录制Shopee流量导出组件
**步骤**: 同上，组件名改为`analytics_export`

**验证点**: 同上

---

#### 测试5.3: 录制Shopee财务导出组件
**步骤**: 同上，组件名改为`finance_export`

**验证点**: 同上

---

#### 测试5.4: 录制Shopee库存导出组件
**步骤**: 同上，组件名改为`inventory_export`

**验证点**: 同上

---

### 类别6：前端功能验证测试（需要完整系统）⚠️

#### 测试6.1: 手动触发采集
**步骤**:
1. 打开前端界面
2. 选择一个配置
3. 点击"立即采集"按钮
4. 观察任务状态

**验证点**:
- [ ] 任务创建成功
- [ ] 状态实时更新
- [ ] WebSocket推送正常
- [ ] 任务完成后显示结果

---

#### 测试6.2: 任务取消功能
**步骤**:
1. 创建一个长时间任务
2. 任务运行中点击"取消"
3. 观察任务状态

**验证点**:
- [ ] 取消按钮可用
- [ ] 任务状态变为"cancelled"
- [ ] 浏览器正确关闭

---

#### 测试6.3: 定时调度功能
**步骤**:
1. 创建配置并设置Cron表达式
2. 启用调度
3. 等待触发时间

**验证点**:
- [ ] 调度任务创建成功
- [ ] 到达时间后自动触发
- [ ] 任务正常执行

---

#### 测试6.4: 配置名自动生成
**步骤**:
1. 创建新配置
2. 选择平台和数据域
3. 观察配置名

**验证点**:
- [ ] 自动生成格式：`{platform}-{domains}-v{n}`
- [ ] 版本号自动递增

---

#### 测试6.5: 快速配置功能
**步骤**:
1. 使用快速配置向导
2. 选择日度/周度/月度
3. 一键创建

**验证点**:
- [ ] 3步完成配置创建
- [ ] Cron表达式自动设置
- [ ] 配置立即可用

---

### 类别7：回归测试（确保旧功能不受影响）⚠️

#### 测试7.1: CLI录制向导
**步骤**:
1. 运行: `python tools/record_component.py --help`
2. 验证所有参数可用

**验证点**:
- [ ] 帮助信息正确
- [ ] 所有参数都有说明
- [ ] 向导模式仍可用

---

#### 测试7.2: 现有数据同步功能
**步骤**:
1. 上传一个Excel文件
2. 执行数据同步
3. 检查数据库

**验证点**:
- [ ] 文件上传成功
- [ ] 数据正确导入
- [ ] 字段映射正常

---

#### 测试7.3: 文件注册流程
**步骤**:
1. 执行一次采集
2. 检查`catalog_files`表
3. 验证文件元数据

**验证点**:
- [ ] 文件自动注册
- [ ] 元数据完整
- [ ] 文件路径正确

---

#### 测试7.4: 反检测机制
**步骤**:
1. 执行采集任务
2. 观察浏览器行为
3. 检查是否被检测

**验证点**:
- [ ] 浏览器不显示"自动化控制"提示
- [ ] 网站正常访问
- [ ] 没有被封禁

---

## 📊 测试统计

### 按优先级统计

| 优先级 | 测试数 | 预计时间 |
|--------|--------|----------|
| ⭐⭐⭐ (P0) | 4个 | 30分钟 |
| ⭐⭐ (P1) | 3个 | 30分钟 |
| ⭐ (P2) | 2个 | 15分钟 |
| ⚠️ (需要环境) | 14个 | 1-2小时 |
| **总计** | **23个** | **2-3小时** |

### 按类别统计

| 类别 | 测试数 | 状态 |
|------|--------|------|
| Phase 2.5 容错机制 | 4个 | 优先测试 |
| Phase 2.1 录制工具 | 3个 | 优先测试 |
| Phase 4.1.6 Cron | 2个 | 优先测试 |
| Phase 1.5.6 截图 | 1个 | 优先测试 |
| Shopee组件录制 | 4个 | 需要账号 |
| 前端功能验证 | 5个 | 需要完整系统 |
| 回归测试 | 4个 | 确保兼容性 |

---

## 🎯 测试执行建议

### 第一轮：核心功能测试（30分钟）
1. ✅ Phase 2.5 容错机制（4个测试）
2. ✅ Phase 4.1.6 Cron预设（2个测试）
3. ✅ Phase 1.5.6 截图API（1个测试）

**目标**: 验证新实现的核心功能

### 第二轮：录制工具测试（30分钟）
1. ✅ Phase 2.1 录制工具（3个测试）

**目标**: 验证录制工具重构效果

### 第三轮：组件录制测试（1小时）
1. ⚠️ Shopee组件录制（4个测试）

**前置条件**: 需要Shopee测试账号

### 第四轮：前端和回归测试（1小时）
1. ⚠️ 前端功能验证（5个测试）
2. ⚠️ 回归测试（4个测试）

**前置条件**: 需要完整系统运行

---

## 📝 测试报告模板

### 测试执行记录

| 测试ID | 测试名称 | 状态 | 备注 |
|--------|----------|------|------|
| 1.1 | Optional参数测试 | ⬜ 未测试 |  |
| 1.2 | Smart Wait测试 | ⬜ 未测试 |  |
| 1.3 | Fallback测试 | ⬜ 未测试 |  |
| 1.4 | Retry测试 | ⬜ 未测试 |  |
| 2.1 | 自动登录测试 | ⬜ 未测试 |  |
| 2.2 | Inspector测试 | ⬜ 未测试 |  |
| 2.3 | Trace录制测试 | ⬜ 未测试 |  |
| 3.1 | Cron验证测试 | ⬜ 未测试 |  |
| 3.2 | Cron预设测试 | ⬜ 未测试 |  |
| 4.1 | 截图API测试 | ⬜ 未测试 |  |
| ... | ... | ... | ... |

### 问题记录

| 问题ID | 描述 | 严重程度 | 状态 |
|--------|------|----------|------|
| - | - | - | - |

---

## 🔧 测试工具和命令

### 启动系统
```bash
# 后端
python run.py

# 前端
cd frontend
npm run dev
```

### 录制工具
```bash
# 基础录制
python tools/record_component.py --platform shopee --component login --account YOUR_ACCOUNT

# 跳过登录
python tools/record_component.py --platform shopee --component orders_export --skip-login

# 不使用Inspector
python tools/record_component.py --platform shopee --component login --no-inspector
```

### 组件测试
```bash
python tools/test_component.py --platform shopee --component login
```

### 查看Trace
```bash
playwright show-trace temp/traces/shopee_login_20251219_120000.zip
```

---

## 📞 支持

**遇到问题？**
1. 检查日志文件: `logs/`
2. 查看错误截图: `temp/screenshots/`
3. 查看Trace文件: `temp/traces/`
4. 参考文档: `docs/guides/`

**报告问题时请提供**:
- 测试步骤
- 预期结果 vs 实际结果
- 日志截图
- Trace文件（如果有）

---

**测试清单创建日期**: 2025-12-19  
**版本**: v1.0  
**状态**: ✅ 准备就绪

