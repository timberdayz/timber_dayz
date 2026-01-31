# Design: 业务概览全局日期同步

## Context

业务概览页面有 6 组日期相关控件，各自独立。用户希望有一个主控日期，多数模块跟随，同时允许单模块手动覆盖（类似目标管理的百分比锁定）。

## Goals / Non-Goals

- **Goals**：全局日期驱动模块、手动覆盖、一键恢复跟随
- **Non-Goals**：不改后端 API、不改 SQL 时间约定、不改各模块 API 参数格式

## Decisions

### 1. 全局日期结构

```ts
globalGranularity: 'daily' | 'weekly' | 'monthly'
globalDate: string | Date  // 根据粒度：YYYY-MM-DD | Date(周) | YYYY-MM
```

### 2. 模块同步映射

| 模块 | 跟随时参数来源 |
|------|----------------|
| 数据对比 | granularity=globalGranularity, date=全局日期转换后的 YYYY-MM-DD |
| 店铺赛马 | 同上 |
| 流量排名 | 同上 |
| 经营指标 | month=映射单日：日→所选日；周→该周周一；月→YYYY-MM-01 |
| 核心 KPI | month=全局月的 YYYY-MM-01（仅当全局为月时） |
| 清仓排名 | clearanceMonth/clearanceWeek 从全局派生 |

### 3. 锁定与恢复

- `useGlobalDate: { comparison: true, shopRacing: true, trafficRanking: true, operational: true, kpi: false, clearance: false }`
- 默认跟随：comparison, shopRacing, trafficRanking, operational
- 可选：kpi, clearance（后续可扩展为默认跟随）

### 4. 时间约定（与现有一致）

- 周 = 周一～周日（`date_trunc('week')`）
- 月 = 1日～月末
- 使用 value-format 与本地日期拼接，避免 toISOString UTC 偏差

## Risks / Trade-offs

- **风险**：全局变更触发多次 API 调用，可能短暂卡顿  
- **缓解**：并行请求，loading 状态聚合
