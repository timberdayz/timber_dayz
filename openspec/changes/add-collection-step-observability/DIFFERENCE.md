# 与 add-hybrid-collection-api-playwright 的区别

本文档说明 **add-collection-step-observability**（采集步骤可观测 + 组件契约统一）与 **add-hybrid-collection-api-playwright**（混合采集：API / Playwright 可选）在范围、目标与交付物上的差异。

## 对比表

| 维度 | add-hybrid-collection-api-playwright | add-collection-step-observability |
|------|--------------------------------------|-----------------------------------|
| **目标** | 按店铺选择「API 或 Playwright」；已授权 API 的店铺用官方 API 采数 | 让「哪一步失败」在界面可见；统一组件 run() 为 async，便于排错与维护 |
| **改动重心** | 配置（collection_method）、执行分流、Shopee/TikTok API 采集器、落盘与 catalog 登记 | 步骤级日志（CollectionTaskLog）、进度持久化（status_callback 写 DB）、任务详情步骤时间线 UI、基类与各平台 run() 改为 async |
| **不做什么** | 不改可观测、不改组件 run 契约 | 不新增 API 采集、不实现 API/Playwright 分流 |
| **依赖** | 与可观测提案无强依赖 | 与 hybrid 无强依赖，可先做或后做、可并行 |

## 简要说明

- **Hybrid 提案**：解决「用什么方式采」（API vs 浏览器），以及 API 采集的落盘与 catalog 登记。
- **可观测提案**：解决「执行过程可见」（步骤级日志、进度持久化、任务详情步骤时间线）和「组件契约统一」（run 统一为 async），不涉及 API/Playwright 选择逻辑。

两者可独立推进；若同时落地，建议先做可观测再接入 hybrid 分流，便于在 API 与 Playwright 两条路径下都能看到步骤时间线。
