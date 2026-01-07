# 深链接采集架构设计文档

> 文档索引（推荐入口）: docs/INDEX.md

## 🎯 架构概述

本文档描述了跨境电商 ERP 系统中"深链接直达 + 参数化采集"的架构设计，旨在替代传统的"海量录制脚本"模式，实现高效、可维护的数据采集流程。

## 🔄 架构演进

### 传统模式（已淘汰）

```
每个账号 × 每个店铺 × 每种数据类型 = 大量录制脚本
问题：维护困难、重复录制、脆弱性高
```

### 新架构（当前）

```
1个账号登录脚本 + 4个参数化采集器 = 完整采集能力
优势：可复用、易维护、快速直达
```

## 🏗️ 核心组件

### 1. Platform Adapters（平台适配器）

**文件**: `modules/utils/platform_adapters.py`

**功能**:

- 🔗 深链接构造：`build_deep_link(data_type, shop_id, **kwargs)`
- 📊 导出配置：`get_export_config(data_type, shop_id, **kwargs)`
- 🎯 页面选择器：`get_page_selectors(data_type)`
- 🔐 权限验证：`validate_shop_access(page, shop_id)`

**支持平台**:

- ✅ Shopee 卖家端（已实现）
- 🔄 Amazon Seller Central（预留）
- 🔄 妙手 ERP（预留）

### 2. Flow Orchestrator（流程编排器）

**文件**: `modules/utils/flow_orchestrator.py`

**功能**:

- 🎬 统一入口：`run(context_factory, account, data_type, shop_id, **kwargs)`
- 🔄 模式切换：深链接模式 vs 传统录制模式
- 🏥 健康检查：集成账号健康检测
- 📥 智能导出：API 优先，点击兜底

**执行流程**:

```
1. 执行登录脚本
2. 账号健康检查
3. 深链接直达目标页面
4. 验证店铺访问权限
5. 执行数据导出（API/点击）
6. 保存文件到规范路径
```

### 3. Recording Registry（录制索引）

**文件**: `modules/utils/recording_registry.py`

**功能**:

- 📁 文件索引：自动扫描现有录制脚本
- 🏷️ 版本管理：支持"最新版"和"稳定版"标记
- 🔍 智能检索：按账号+数据类型快速定位脚本
- 📊 兼容性：向后兼容所有历史录制文件

### 4. Collection Template Generator（模板生成器）

**文件**: `modules/utils/collection_template_generator.py`

**功能**:

- 📝 模板生成：为不同数据类型生成标准化采集脚本
- 🔧 参数化：支持 shop_id、日期范围等参数
- 🎯 统一接口：所有模板提供`run(page, account, **kwargs)`入口

## 📊 数据类型映射

### Shopee 平台

| 数据类型  | 深链接路由                     | 导出按钮            | 文件格式 |
| --------- | ------------------------------ | ------------------- | -------- |
| products  | `/datacenter/product/overview` | `text=导出数据`     | CSV      |
| orders    | `/portal/order/list`           | `text=导出订单`     | XLSX     |
| analytics | `/datacenter/traffic/overview` | `text=导出报告`     | CSV      |
| finance   | `/portal/finance/revenue`      | `text=导出财务数据` | XLSX     |

### URL 构造规则

```python
base_url = "https://seller.shopee.cn"
deep_link = f"{base_url}{route}?cnsc_shop_id={shop_id}"

# 示例
# 商品数据: https://seller.shopee.cn/datacenter/product/overview?cnsc_shop_id=1407964586
# 订单数据: https://seller.shopee.cn/portal/order/list?cnsc_shop_id=1407964586
```

## 🔄 使用流程

### 开发阶段

1. **录制登录脚本**（每个账号 1 次）

   ```bash
   选择平台 -> 选择账号 -> 自动登录流程修正
   ```

2. **生成采集模板**（每种数据类型 1 次）

   ```python
   from modules.utils.collection_template_generator import generate_collection_template

   script_path = generate_collection_template(
       platform="shopee",
       data_type=RecordingType.PRODUCTS,
       account_name="shopee新加坡3C店",
       shop_id="1407964586"
   )
   ```

3. **API 端点录制**（可选，提高效率）
   ```bash
   使用Playwright Inspector录制一次"点击导出"
   观察Network面板，确定真实API端点
   更新platform_adapters.py中的导出配置
   ```

### 生产阶段

```python
from modules.utils.flow_orchestrator import FlowOrchestrator, RecordingType

# 创建编排器
orchestrator = FlowOrchestrator("shopee")

# 执行采集
success = orchestrator.run(
    playwright_context_factory=make_context,
    account=account_config,
    data_type=RecordingType.PRODUCTS,
    shop_id="1407964586",
    date_range="last_30_days"
)
```

## 📁 文件组织规范

### 录制脚本

```
temp/recordings/shopee/
├── {account}_login_auto_{timestamp}.py                     # 登录脚本
├── shopee_{account}_{data_type}_complete_{timestamp}.py    # 完整流程（登录 + 采集 + 时间 + 导出）
├── {account}_collection_products_{timestamp}.py            # 商品采集（历史兼容）
├── {account}_collection_orders_{timestamp}.py              # 订单采集（历史兼容）
├── {account}_collection_analytics_{timestamp}.py           # 分析采集（历史兼容）
└── {account}_collection_finance_{timestamp}.py             # 财务采集（历史兼容）
```

### 输出文件

```
temp/outputs/shopee/{shop_id}/{data_type}/
├── 20250829_143022_products_1407964586.csv
├── 20250829_143155_orders_1407964586.xlsx
└── ...
```

### 索引文件

```
data/recordings/registry.json                    # 录制脚本索引
data/account_health_logs.json                   # 健康检查日志
data/disabled_accounts.json                     # 禁用账号列表
```

## 🔧 配置管理

### 平台适配器配置

```python
# modules/utils/platform_adapters.py
DEEP_LINK_ROUTES = {
    RecordingType.PRODUCTS: "/datacenter/product/overview",
    RecordingType.ORDERS: "/portal/order/list",
    # ...
}

PAGE_SELECTORS = {
    RecordingType.PRODUCTS: {
        "export_button": "text=导出数据",
        "data_table": "[data-testid='product-table']",
        # ...
    }
}
```

### 导出 API 配置

```python
def get_export_config(self, data_type, shop_id, **kwargs):
    return ExportConfig(
        method="GET",
        endpoint=f"{self.BASE_URL}/api/datacenter/product/export",
        params={"shop_id": shop_id, "type": "overview"},
        headers={"Accept": "application/json"},
        file_extension="csv"
    )
```

## 🚨 错误处理与健康检查

### 账号健康检查

- **权限验证**: 检测"您没有权限查看这个页面"
- **店铺匹配**: 验证 URL 中的 shop_id 是否正确
- **页面状态**: 确认页面正常加载且包含预期内容

### 异常处理策略

- **权限不足**: 立即停止，标记账号为禁用
- **网络超时**: 重试 3 次，失败后记录日志
- **API 失败**: 自动降级到点击导出模式
- **文件保存失败**: 重试保存，记录详细错误信息

## 📈 性能优化

### 深链接优势

- ⚡ **速度提升**: 跳过繁琐的页面导航，直达目标页面
- 🎯 **精确定位**: 基于 URL 参数精确定位店铺和数据类型
- 🔄 **可复用性**: 一套脚本适用于所有店铺

### API 导出优势

- 🚀 **效率提升**: 直接调用导出接口，避免 UI 交互
- 📊 **数据完整性**: 减少 UI 变更导致的采集失败
- 🔧 **可维护性**: API 接口相对稳定，维护成本低

## 🔮 扩展计划

### 短期目标（1-2 周）

- [ ] 完善 Shopee 平台的 4 种数据类型采集
- [ ] 集成到数据采集中心 UI
- [ ] 添加批量采集功能

### 中期目标（1 个月）

- [ ] 支持 Amazon Seller Central 平台
- [ ] 添加数据采集调度功能
- [ ] 实现采集结果统计和报告

### 长期目标（3 个月）

- [ ] 支持妙手 ERP 平台
- [ ] 添加 AI 智能采集优化
- [ ] 实现跨平台数据整合分析

## 🤝 开发协作

### 代码贡献流程

1. 基于最新代码创建功能分支
2. 实现新功能并添加相应测试
3. 更新相关文档
4. 提交 PR 并通过代码审查

### 平台适配器扩展

1. 继承`PlatformAdapter`基类
2. 实现所有抽象方法
3. 添加到`PLATFORM_ADAPTERS`注册表
4. 编写平台特定的测试用例

### 新数据类型添加

1. 在`RecordingType`枚举中添加新类型
2. 更新所有平台适配器的映射配置
3. 生成对应的采集模板
4. 更新文档和测试

---

**文档版本**: v1.0.0
**最后更新**: 2025-08-29
**维护者**: 跨境电商 ERP 开发团队
