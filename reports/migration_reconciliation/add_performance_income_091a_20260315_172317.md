# 0.9.1a 迁移对账归档报告

- 生成时间: 2026-03-15 17:23:17
- 范围: sales_targets/performance_scores/shop_health_scores/shop_alerts

## 1. 迁移前快照可用性

| 表 | public中是否存在 |
|---|---|
| `sales_targets` | 否 |
| `performance_scores` | 否 |
| `shop_health_scores` | 否 |
| `shop_alerts` | 否 |

说明：若 public 旧表均不存在，表示迁移后状态正确；但无法在当前环境直接复原“迁移前”行数，需结合执行迁移前导出的备份文件做严格前后对账。

## 2. 迁移后对账（行数/空值率/抽样）

### a_class.sales_targets

- 行数: `3`
- 关键字段空值率:
  - `id`: `0.0`
- 抽样（最多 20 条）:

```json
[
  {
    "id": 3
  },
  {
    "id": 2
  },
  {
    "id": 1
  }
]
```

### c_class.performance_scores

- 行数: `0`
- 关键字段空值率:
  - `id`: `0.0`
  - `platform_code`: `0.0`
  - `shop_id`: `0.0`
  - `period`: `0.0`
  - `total_score`: `0.0`
  - `rank`: `0.0`
- 抽样（最多 20 条）:

```json
[]
```

### c_class.shop_health_scores

- 行数: `0`
- 关键字段空值率:
  - `id`: `0.0`
  - `platform_code`: `0.0`
  - `shop_id`: `0.0`
  - `health_score`: `0.0`
- 抽样（最多 20 条）:

```json
[]
```

### c_class.shop_alerts

- 行数: `0`
- 关键字段空值率:
  - `id`: `0.0`
  - `platform_code`: `0.0`
  - `shop_id`: `0.0`
  - `alert_level`: `0.0`
  - `created_at`: `0.0`
- 抽样（最多 20 条）:

```json
[]
```
