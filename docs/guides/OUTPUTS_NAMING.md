# 输出命名与目录规范（v1.1）

> 文档索引（推荐入口）: docs/INDEX.md

本规范适用于所有平台（Shopee、Amazon、Lazada、妙手 ERP 等）的本地落盘输出，目标是保证路径唯一、稳定、可预测，降低数据入库与自动化处理的路径错误率。

## 目录结构

- 根目录：`temp/outputs/<platform>/`
- 账号目录：`<account_slug>/`
- 店铺目录：`<shop_slug>__<shop_id>`（默认启用 include_shop_id = true）
- 数据类型目录：`products`/`traffic`/`services`/`orders`/`finance`
- 子类型目录（可选）：如 `services/ai_assistant`、`services/agent`
- 粒度目录：`daily`/`weekly`/`monthly`/`manual`

完整路径：

```
temp/outputs/<platform>/<account_slug>/<shop_slug>__<shop_id>/<data_type>[/<subtype>]/<granularity>/

可选（配置开关）:
- 如需兼容历史环境，可将 `path_options.include_shop_id` 设为 false，此时店铺目录为 `<shop_slug>`（不推荐）。
- 当数据域存在子类型时（如 services），会增加 `<subtype>` 目录层；无子类型则省略。
```

## 文件命名

```
{TS}__{account}__{shop}__{data_type}__{granularity}[__{start}_{end}].xlsx
```

- TS：`YYYYMMDD_HHMMSS`
- `start/end`：`YYYY-MM-DD`（可选，存在时间范围时添加）

## safe_slug 规则（统一命名）

- Unicode 正规化：NFKD 分解并去除音标；再执行 NFKC
- 小写化：统一为小写
- 允许字符：字母、数字、`-_.`；其余替换为 `_`
- 连续下划线折叠：多个 `_` 折叠为一个
- 去除首尾的 `.` 与 `_`
- 为空时回退为 `unknown`

示例：

- `Loja_de_balões_rei.br` → `loja_de_baloes_rei.br`
- `The King’s Lucky Shop` → `the_king_s_lucky_shop`

## 历史目录清理与重分类

- 别名合并：`product/prod` → `products`；`analytics/traffic_overview` → `traffic`
- 粒度统一：`overview/manual` 基于文件名中的日期范围重分类到 `daily/weekly/monthly`
- 店铺目录采用 `__<shop_id>` 规范；历史无 shop_id 的目录不再生成，建议归档或保留即可（不做强制迁移）
- 特殊情况：当店铺名与账号名相同时，可统一重命名为 `unknown_shop`（避免两级同名冲突）

## 工具脚本

- 目录规范化与清理：`temp/development/cleanup_outputs.py`
  - 预演：`python temp/development/cleanup_outputs.py --base temp/outputs/<platform> --preflight`
  - 执行：`python temp/development/cleanup_outputs.py --base temp/outputs/<platform> --apply`
  - 选项：
    - `--rename-same-shop` 当仅一个店铺且与账号同名时改 `unknown_shop`
    - `--rename-equal-shop-any` 只要店铺名与账号名相同，一律改 `unknown_shop`
- 快照：`temp/development/snapshot_outputs.py` → `temp/development/outputs_tree_<platform>.json`

## 回滚方案

- 所有脚本均为“移动/合并”，不做硬删除；冲突时重命名保留
- 若需回滚：
  1. 检查 `temp/development/*report*.json` 了解迁移映射
  2. 反向移动文件/目录即可恢复

## 故障排查

- Windows 大小写不敏感导致无法直接重命名：脚本使用“两步法”临时名规避
- 仍有相似目录：补充别名映射后运行预演 → 执行
- 路径异常字符：核对 `safe_slug` 是否应用于所有落盘逻辑
