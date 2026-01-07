# 🏪 多平台店铺管理系统使用指南

> 文档索引（推荐入口）: docs/INDEX.md

## 📖 系统概述

多平台店铺管理系统是跨境电商 ERP 的核心组件，专门为管理多个电商平台的多个店铺账号而设计。系统支持 Shopee、妙手 ERP、Amazon、Lazada 等主流平台，为每个店铺提供独立的数据存储、采集管理和健康度监控。

### 🎯 核心优势

- **店铺级数据隔离**: 每个店铺的数据完全独立存储
- **多账号批量管理**: 支持同时管理多个平台的多个账号
- **健康度监控**: 实时监控每个店铺的数据采集健康状况
- **云端环境优化**: 专门针对 2 核 3M 带宽云端环境优化
- **直观管理界面**: 现代化 Web 界面，操作简单直观

## 🚀 快速开始

### 1. 系统启动

#### 方式一：使用快速启动脚本（推荐）

```bash
python start_store_management.py
```

#### 方式二：直接启动 Streamlit

```bash
streamlit run frontend_streamlit/store_management.py
```

### 2. 访问管理界面

浏览器打开：`http://localhost:8501`

## 📋 功能模块详解

### 1. 总览仪表板

总览页面提供系统的整体状况：

- **全局统计**: 显示总账号数、总店铺数、健康店铺数、采集中账号数
- **平台分布图表**: 可视化展示各平台的账号分布情况
- **店铺健康度分布**: 饼图显示健康、良好、警告、危险店铺的分布
- **最近采集活动**: 列表显示最近的采集记录和状态

### 2. 店铺管理

#### 2.1 添加新账号

1. 选择目标平台（Shopee、妙手 ERP 等）
2. 点击"➕ 添加新账号"展开表单
3. 填写必填信息：

   - **店铺名称**: 用于识别和数据隔离的唯一标识
   - **用户名**: 平台登录用户名
   - **密码**: 平台登录密码
   - **登录 URL**: 平台登录页面地址

4. 选择可选配置：
   - **地区**: 选择店铺所在地区
   - **货币**: 选择主要交易货币
   - **代理设置**: 如需要代理访问
   - **备注**: 账号相关说明

#### 2.2 账号列表管理

账号列表显示每个平台的所有账号信息：

- **账号 ID**: 系统自动生成的唯一标识
- **店铺名称**: 用户定义的店铺名称
- **用户名**: 登录用户名
- **状态**: 当前账号状态（空闲/采集中/成功/失败）
- **健康度**: 0-100 分的健康度评分
- **成功率**: 历史采集成功率
- **总采集次数**: 累计采集次数
- **最后采集**: 最近一次采集时间

#### 2.3 批量操作

- **🚀 批量采集**: 对所有空闲账号启动采集任务
- **⏸️ 暂停采集**: 暂停正在进行的采集任务
- **🔄 重置状态**: 重置账号状态为空闲
- **🗑️ 删除账号**: 删除选中的账号（谨慎操作）

### 3. 采集任务管理

#### 3.1 任务调度策略

系统根据以下原则调度采集任务：

1. **资源限制**: 根据云端配置限制并发数量
2. **健康度优先**: 优先调度健康度高的店铺
3. **状态检查**: 只调度状态为"空闲"的账号
4. **错误恢复**: 自动重试失败的任务

#### 3.2 任务状态管理

- **scheduled**: 已调度，等待执行
- **running**: 正在执行中
- **completed**: 执行完成
- **failed**: 执行失败
- **retry**: 重试中

### 4. 健康监控

#### 4.1 健康度评分体系

健康度评分（0-100 分）基于以下因素计算：

- **成功率权重 40%**: 历史采集成功率
- **数据质量权重 30%**: 采集数据的完整性和准确性
- **时效性权重 20%**: 最近 24 小时内的采集活动
- **错误率权重 10%**: 24 小时内的错误次数

#### 4.2 健康度等级

- **优秀 (90-100 分)**: 绿色，运行状况良好
- **良好 (70-89 分)**: 蓝色，运行正常
- **警告 (50-69 分)**: 黄色，需要关注
- **危险 (0-49 分)**: 红色，需要立即处理

#### 4.3 监控指标

- **采集成功率**: 最近采集任务的成功比例
- **平均采集时长**: 单次采集任务的平均耗时
- **数据质量评分**: 采集数据的质量评估
- **24 小时错误数**: 最近 24 小时的错误统计

### 5. 系统设置

#### 5.1 云端环境配置

系统针对 2 核 3M 带宽的云端环境进行了专门优化：

- **CPU 限制**: 最大使用 70%的 CPU 资源
- **内存限制**: 最大使用 75%的内存资源
- **网络限制**: 最大使用 60%的带宽资源
- **并发限制**: 最多 1 个并发采集器

#### 5.2 性能优化建议

系统会根据当前配置提供性能优化建议：

- ✅ 启用无头浏览器模式节省内存
- ✅ 限制最大并发采集器为 1 个
- ✅ 启用数据压缩减少存储占用
- ✅ 自动清理临时文件释放磁盘空间
- ⚠️ 建议升级到 4 核 8G 配置以提升性能

## 📁 数据存储结构

### 目录结构

```
temp/outputs/
├── shopee/
│   ├── MyStore_SG/          # 店铺专属目录
│   │   ├── downloads/       # 下载的数据文件（或直接落盘到 temp/outputs/shopee/.../products/<粒度>/）
│   │   ├── collection_record_20250114_143022.json  # 采集记录
│   │   └── ...
│   └── MyStore_MY/          # 另一个店铺
│       └── ...
├── miaoshou/
│   └── xihong/              # 妙手ERP店铺
│       └── ...
└── ...

temp/media/screenshots/
├── shopee/
│   ├── MyStore_SG/          # 店铺专属截图
│   └── MyStore_MY/
└── ...

temp/sessions/
├── shopee/
│   ├── MyStore_SG/          # 店铺专属会话
│   └── MyStore_MY/
└── ...

temp/logs/
├── shopee/
│   ├── MyStore_SG/          # 店铺专属日志
│   └── MyStore_MY/
└── ...
```

### 采集记录格式

每次采集完成后，系统会生成详细的采集记录：

```json
{
  "account_info": {
    "account_id": "shopee_001",
    "store_name": "MyStore_SG",
    "username": "user@example.com",
    "login_url": "https://seller.shopee.sg"
  },
  "collection_info": {
    "start_time": "2025-01-14T14:30:22",
    "completion_time": "2025-01-14T14:45:18",
    "duration_seconds": 896.5,
    "success": true
  },
  "data_summary": {
    "collected_data_count": 1250,
    "download_success": true,
    "data_types": ["orders", "products", "analytics"]
  },
  "file_paths": {
    "base_path": "temp/outputs/shopee/MyStore_SG",
    "downloads_path": "temp/outputs/shopee/MyStore_SG/downloads",
    "screenshots_path": "temp/media/screenshots/shopee/MyStore_SG"
  }
}
```

## 🔧 高级配置

### 1. 云端资源配置

编辑 `config/collectors/cloud_resource_config.yaml` 文件：

```yaml
# 系统资源管理
resource_management:
  max_cpu_usage_percent: 70.0
  cpu_warning_threshold: 60.0
  max_memory_usage_percent: 75.0
  memory_warning_threshold: 65.0

# 采集任务管理
collection_management:
  max_concurrent_collectors: 1
  max_concurrent_tasks: 2
  collection_mode: "resource_safe"

# 浏览器资源优化
browser_optimization:
  headless_mode: true
  disable_images: true
  max_browser_instances: 1
  slow_mo_milliseconds: 2000
```

### 2. 平台特定配置

每个平台可以有独立的配置文件：

- `config/platform_accounts/shopee_accounts.json`
- `config/platform_accounts/miaoshou_accounts.json`
- `config/platform_accounts/amazon_accounts.json`
- `config/platform_accounts/lazada_accounts.json`

### 3. 自定义采集器

如需添加新平台支持，可以：

1. 继承 `BaseCollector` 类
2. 实现平台特定的登录和采集逻辑
3. 注册到 `PlatformAccountManager`

```python
from core.platform_account_manager import PlatformAccountManager

# 注册新平台
manager = PlatformAccountManager("new_platform")
manager.register_collector("new_platform", NewPlatformCollector)
```

## 📊 数据分析和报告

### 1. 店铺健康度报告

系统自动生成店铺健康度报告，包括：

- 健康度趋势图
- 采集成功率变化
- 数据质量评估
- 异常事件记录

### 2. 平台对比分析

- 各平台采集效率对比
- 平台稳定性分析
- 资源使用情况对比
- 成本效益分析

### 3. 性能监控报告

- 系统资源使用趋势
- 采集任务执行时间分析
- 错误类型统计
- 优化建议

## 🚨 故障排除

### 常见问题

#### 1. 采集器启动失败

**症状**: 点击批量采集后无响应或报错

**解决方案**:

1. 检查账号配置是否完整
2. 验证 login_url 是否正确
3. 确认网络连接正常
4. 查看系统资源使用情况

#### 2. 登录验证失败

**症状**: 采集器显示登录失败

**解决方案**:

1. 确认用户名密码正确
2. 检查是否需要邮箱验证
3. 验证代理设置（如使用）
4. 查看平台是否有新的验证机制

#### 3. 数据采集不完整

**症状**: 采集完成但数据量异常少

**解决方案**:

1. 检查平台页面结构是否变化
2. 确认账号权限是否充足
3. 验证数据筛选条件
4. 查看采集日志中的错误信息

#### 4. 系统资源不足

**症状**: 采集过程中系统卡顿或崩溃

**解决方案**:

1. 降低并发采集器数量
2. 启用资源安全模式
3. 清理临时文件释放空间
4. 考虑升级服务器配置

### 日志查看

系统日志位置：

- 应用日志: `temp/logs/[platform]/[store_name]/`
- 系统日志: 控制台输出
- 错误日志: 自动记录在采集记录中

### 性能调优

1. **内存优化**:

   - 启用无头浏览器模式
   - 减少并发任务数量
   - 定期清理临时文件

2. **网络优化**:

   - 使用 CDN 加速（如可用）
   - 优化网络超时设置
   - 启用连接池

3. **存储优化**:
   - 启用数据压缩
   - 定期归档历史数据
   - 使用 SSD 存储

## 📞 技术支持

### 获取帮助

1. **文档资源**:

   - [项目 README](../README.md)
   - [开发路线图](../DEVELOPMENT_ROADMAP.md)
   - [项目状态](../PROJECT_STATUS.md)

2. **问题反馈**:

   - GitHub Issues
   - 项目讨论区
   - 技术支持邮箱

3. **社区支持**:
   - 用户交流群
   - 技术论坛
   - 在线文档

### 更新和维护

- 定期检查系统更新
- 关注平台 API 变化
- 备份重要配置和数据
- 监控系统运行状态

---

**最后更新**: 2025-01-14
**文档版本**: 1.0.0
**适用系统版本**: v2.0.0+
