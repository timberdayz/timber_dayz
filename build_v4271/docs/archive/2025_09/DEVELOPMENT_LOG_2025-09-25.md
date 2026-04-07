# 📝 开发日志 · 2025-09-25

> 范围：数据采集“一键/并行执行”稳定性、妙手 ERP 订单子平台切换、输出文件清单汇总、交互防呆与规范更新。

## 今日产出

- 一键并行执行稳定性
  - 将“全局墙钟超时”改为“子进程闲置超时（默认 600 秒）”，仅在连续无输出达阈值时判定超时，避免长导出被误杀。
  - 独立监控各子进程输出时间戳，独立终止；其余平台不受牵连。
- 交互防呆（子进程）
  - 在 batch/one-click 路径下，所有 `input("按回车返回…")` 加入保护：`if not _one_click_mode: input(...)`，防止子进程卡死。
- 妙手 ERP（订单）平台切换确认修正
  - 先导航 → 再执行“平台切换确认（最多 2 轮：点击平台标签 → 深链接）” → 日期选择 → 导出。
  - 切换判定以 URL `?platform=` 为准，lowercase 匹配；统一从 `orders_config.py` 读取 deep_link_template。
- 一键导出文件清单
  - 子进程：成功导出即收集 `file_path` 到 ONE_CLICK_RESULT_JSON.files，并打印 `EXPORTED_FILE: …` 行。
  - 父进程：聚合全部平台的成功文件，打印“🗂️ 导出文件清单（全部平台）”，含绝对路径与 `file:///` 直达链接。
- 目录/路径卫生
  - 增强对“跨平台/跨域落盘（路径污染）”的防御建议与日志提示：若 URL 与执行上下文的 platform/account/shop 不一致，应立即告警并阻断跨域落盘。

## 关键代码位置

- 一键并行执行（闲置超时）：modules/apps/collection_center/app.py
- 子进程交互防呆：modules/apps/collection_center/app.py（所有 `input()` 已条件保护）
- 妙手订单平台切换确认（位置修正）：modules/apps/collection_center/app.py（导航之后、日期选择之前执行）
- 一键文件清单聚合打印：modules/apps/collection_center/app.py（父/子进程均打印）

## 复现与验证建议

1. 运行一键并行（默认 600s 闲置超时）

- 预期：
  - 控制台持续输出 `[SwitchPlatform] attempt=… expect=… current=…` 日志；
  - orders/shopee 与 orders/tiktok 均生成对应子目录与文件；
  - 结束时打印“🗂️ 导出文件清单（全部平台）”与多行 `EXPORTED_FILE:` 标记。

2. 检查 Miaoshou 输出路径

- products 数据应落在：`…/miaoshou/<account>/<shop>/products/snapshot/…`
- orders 数据应按子类型：`…/miaoshou/.../orders/shopee/daily/…` 与 `…/orders/tiktok/daily/…`
- 若仍出现“非妙手产品文件落入妙手 products/snapshot”，请将该文件名与相邻日志片段（包含 URL）贴出，以确认是否存在跨域落盘，我们将加上更强的写前校验与中断。

## 文档/规范同步

- 更新 docs/DEVELOPMENT_RULES.md：新增
  - 一键/并行执行规范（闲置超时、子进程禁止交互、结果聚合）
  - 平台切换确认顺序（导航后，日期前；URL ?platform 判定 + 深链接来源统一）
  - 输出清单与落盘校验（EXPORTED_FILE 标记、file:/// 链接、跨域写入防御）
- 更新 docs/PROJECT_STATUS.md：标注 2025-09-25 最新进展与下一步计划。

## 清理与归档（计划）

项目遵循“绝不删除，仅移动到 backups/”原则。

- 工具：modules/utils/recording_maintenance.py
- 建议先 Dry-Run 预演，再执行：

Dry-Run 预演（不改动文件，仅打印计划）

```powershell
python modules/utils/recording_maintenance.py --platform miaoshou
```

实际应用（移动到 backups/）

```powershell
python modules/utils/recording_maintenance.py --platform miaoshou --apply
```

可选：备份轮转压缩与清理（按需）

```powershell
python modules/utils/recording_maintenance.py --platform miaoshou --apply --purge-plan --rotate-days 60
```

> 说明：我们遵循用户“控制台优先，不自动写合并日志”的偏好，上述维护工具会生成最小化报告文件于 temp/logs/maintenance/ 以便追溯；如需完全避免，可仅运行 Dry-Run 并将计划复制保存到手册。

## 明日计划

- 将妙手导出器内部的等待阈值统一提升至 600 秒，并外部化到配置文件（含“最新导出记录就绪”“下载完成确认”两个路径）。
- 为“跨平台落盘”加入最小契约测试：对导出完成后的 URL `?platform` 与最终输出路径中的 `<subtype>` 做一致性断言。
- 再次做“单次/批量/一键”全量回归，特别关注 orders/tiktok 子目录落盘与文件名日期区间一致性。

## 晚间补充（orders 入库与解析策略）

- 队列修复与重跑
  - 将 `temp/outputs/miaoshou/xihong/xihong__miaoshou_real_001/orders/` 下 8 个订单文件在 catalog_files 中的状态从 ingested/failed 统一重置为 pending
  - 执行入库任务：run_once(domains=['orders'])，阶段日志已开启（parse/map/convert/commit）
  - 本轮结果：picked=8, succeeded=0, failed=8（原因一致）
- 诊断结论（已生成极小诊断样本 temp/development/diagnostics/\*.diag.txt）
  - 8 个文件均为真实 OLE 二进制 .xls（非 HTML 伪装）
  - 当前环境的 xlrd 版本不支持 .xls（xlrd>=2.0 已移除对 .xls 的支持）
- 解决方案（需依赖授权）
  - 安装并固定：xlrd==1.2.0（仅用于 .xls；.xlsx 走 openpyxl；HTML 伪装 .xls 走 read_html+lxml/bs4/html5lib）
  - 安装命令：pip install "xlrd==1.2.0"（或统一 pip install -r requirements.txt 后续我会写入约束）
  - 完成后重跑 orders 入库，可获得 rows_ingested>0 的样本，并解锁前端“订单入库摘要”联调
- 文档与前端
  - README 已补充依赖说明与 sidecar（可选）开关
  - Streamlit 新 DB 看板已加入“口径说明（运营 vs 经营）”与“订单入库摘要（按平台/店铺）”区块
