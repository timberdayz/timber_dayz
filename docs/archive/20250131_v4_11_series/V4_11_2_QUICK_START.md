# v4.11.2 C类数据计算功能快速开始指南

**版本**: v4.11.2  
**日期**: 2025-11-15

## 🚀 快速开始

### 1. 安装依赖

```bash
# 安装APScheduler（定时任务依赖）
pip install apscheduler>=3.10.0

# 或安装所有依赖
pip install -r requirements.txt
```

### 2. 执行数据库迁移

```bash
# 应用索引和物化视图优化
alembic upgrade head
```

**迁移内容**：
- 13个性能优化索引
- 2个物化视图（mv_shop_daily_performance, mv_shop_health_summary）

### 3. 启动服务

```bash
# 启动后端服务（会自动启动定时任务）
python run.py
```

### 4. 验证功能

```bash
# 运行测试脚本
python scripts/test_c_class_data_calculation.py
```

## 📋 功能清单

### C类数据计算API端点

#### 1. 销售战役达成率计算
```bash
POST /api/sales-campaigns/{campaign_id}/calculate
```

#### 2. 目标达成率计算
```bash
POST /api/target-management/{target_id}/calculate
```

#### 3. 店铺健康度评分计算
```bash
POST /api/store-analytics/health-scores/calculate?platform_code=shopee&shop_id=shop_1
```

#### 4. 店铺健康度历史趋势
```bash
GET /api/store-analytics/health-scores/{shop_id}/history?start_date=2025-11-01&end_date=2025-11-15
```

#### 5. 店铺预警查询
```bash
GET /api/store-analytics/alerts?platform_code=shopee&is_resolved=false
```

#### 6. 店铺预警解决
```bash
POST /api/store-analytics/alerts/{alert_id}/resolve
```

#### 7. 店铺预警统计
```bash
GET /api/store-analytics/alerts/stats
```

#### 8. 店铺赛马排名（含环比）
```bash
GET /api/business-overview/shop-racing?granularity=daily&date=2025-11-15
```

#### 9. 经营指标查询（从sales_targets读取目标）
```bash
GET /api/business-overview/operational-metrics?date=2025-11-15
```

## ⏰ 定时任务

系统会自动执行以下定时任务：

1. **达成率计算**（每天凌晨2:00）
   - 计算所有销售战役的达成率
   - 计算所有目标的达成率

2. **健康度评分计算**（每天凌晨2:00）
   - 计算所有店铺的健康度评分
   - 更新shop_health_scores表

3. **预警检查**（每小时）
   - 检查店铺预警规则
   - 生成shop_alerts记录

4. **排名计算**（每天凌晨3:00）
   - 计算滞销清理排名
   - 更新clearance_rankings表

## 📊 数据流程

```
A类数据（用户配置）
  ↓
B类数据（Excel采集）
  ↓
C类数据（系统自动计算）
  ├─ 达成率（销售战役/目标管理）
  ├─ 健康度评分（GMV/转化/库存/服务）
  ├─ 排名（店铺赛马/滞销清理）
  └─ 预警（健康度/转化率/库存周转）
  ↓
前端展示
```

## 🔍 健康度评分计算说明

### 评分规则
- **GMV得分**（0-30分）：基于GMV排名和增长率
- **转化得分**（0-25分）：基于转化率排名
- **库存得分**（0-25分）：基于库存周转率
- **服务得分**（0-20分）：基于客户满意度

### 计算公式

**库存周转率**：
```
库存周转天数 = 可用库存 / (近30天日均销量)
库存周转率（年化）= 365 / 库存周转天数
```

**客户满意度**：
```
客户满意度 = AVG(rating) WHERE rating > 0 AND rating IS NOT NULL
```

## 📈 性能优化

### 索引优化
- fact_orders表：3个索引（日期范围、状态筛选、店铺统计）
- fact_product_metrics表：4个索引（数据域、粒度、库存周转、客户满意度）
- shop_health_scores表：2个索引（日期粒度、排名）
- clearance_rankings表：2个索引（排名、金额）
- sales_campaigns/sales_targets表：2个索引（日期范围）

### 物化视图
- **mv_shop_daily_performance**：店铺日度表现（90天历史）
- **mv_shop_health_summary**：店铺健康度汇总（90天历史）

## 🛠️ 故障排查

### 定时任务未启动
1. 检查APScheduler是否安装：`pip list | grep apscheduler`
2. 检查日志：查看是否有"APScheduler未安装"警告
3. 手动安装：`pip install apscheduler>=3.10.0`

### 数据库迁移失败
1. 检查数据库连接
2. 检查迁移脚本的down_revision是否正确
3. 查看Alembic版本历史：`alembic history`

### API响应慢
1. 检查索引是否创建：`\d+ fact_orders`（PostgreSQL）
2. 检查物化视图是否创建：`\d+ mv_shop_daily_performance`
3. 手动刷新物化视图：`REFRESH MATERIALIZED VIEW CONCURRENTLY mv_shop_daily_performance;`

## 📝 注意事项

1. **定时任务依赖**：
   - APScheduler必须安装才能启动定时任务
   - 如果未安装，C类数据需要手动计算

2. **数据库迁移**：
   - 索引创建可能需要一些时间（取决于数据量）
   - 建议在低峰期执行迁移
   - 物化视图创建后需要手动刷新一次

3. **性能影响**：
   - 新增索引会略微影响写入性能
   - 但查询性能将显著提升（预计提升60-90%）

## 🔗 相关文档

- [API契约文档](../API_CONTRACT.md) - 完整的API接口说明
- [CHANGELOG](../CHANGELOG.md) - 版本变更记录
- [工作总结](./V4_11_2_C_CLASS_DATA_CALCULATION_SUMMARY.md) - 详细的工作总结

