# 采集组件 lint 阶段一基线快照

> **快照日期**：2026-10-23（当日第二次刷新：库存域「仓库范围筛选」取证驱动修正之后）
> **运行命令**：`python scripts/lint_collection_components.py --fail-on none`
> **扫描范围**：`modules/platforms/**`（**排除 `archive/` 目录**）
> **规则实现**：`backend/services/collection_component_lint.py`（唯一来源，录制器与 CLI 共用）
> **CLI 入口**：`scripts/lint_collection_components.py`

---

## 0. 这是告警模式基线，不是阻断基线

本文件记录的是**阶段一（告警模式）**跑出来的真实数字，**不构成阻断基线**：

- CI 步骤使用 `--fail-on none`，**只打印不阻断**；
- 下文的 error 数量是**存量历史违规**，不是「新增违规」；
- 阶段二才会对**新增/修改**的组件强制阻断（判据见 §6），届时**历史违规不阻断**。

> 2026-10-23 刷新说明：库存域「仓库范围筛选」组件按真实页面取证修正定位器时，
> 顺带把该文件里 10 处 `.first`/`.nth` 补上了业务语义理由（转 warning）、
> 去掉 2 处多余的 `except Exception: pass`、给 2 处固定等待补了「动画」理由，
> 因此 `warehouse_filters.py` 的 error 从 14 处降到 11 处、warning 从 0 处升到 12 处。
> 全仓库 error 由 395 条 / 677 处降到 **385 条 / 656 处**。

---

## 1. 总览

| 指标 | 数值 |
|---|---|
| 扫描文件数 | **62** |
| 有命中的文件数 | **34** |
| error 命中（条） | **385** |
| error 命中（处） | **656** |
| warning 命中（条） | **15** |
| warning 命中（处） | **25** |
| 命中合计（处） | **681** |

> 「条」= 报告里的问题条目数；「处」= 展开到具体代码位置的违规点数。
> 聚合型规则（如 `first_nth_usage`）一条对应多处，所以两者不等。

---

## 2. 按规则命中统计

| 规则 type | 级别 | 命中处数 | 命中文件数 |
|---|---|---|---|
| `swallow_exception_pattern` | error | 266 | 27 |
| `first_nth_usage` | error | 205 | 21 |
| `wait_for_timeout_usage` | error | 102 | 19 |
| `oversized_function` | error | 27 | 12 |
| `missing_report_step` | error | 25 | 25 |
| `count_is_visible_pattern` | error | 13 | 13 |
| `fixed_sleep_usage` | error | 8 | 4 |
| `oversized_class` | error | 6 | 6 |
| `missing_stable_component_record` | error | 4 | 4 |
| `first_nth_with_reason` | warning | 10 | 1 |
| `missing_logger_usage` | warning | 9 | 9 |
| `single_signal_navigation` | warning | 4 | 4 |
| `wait_for_timeout_with_reason` | warning | 2 | 1 |
| `stable_points_to_archived_file` | error | 0 | 0 |
| `invalid_ignore_comment` | error | 0 | 0 |
| `syntax_error` | error | 0 | 0 |

> `swallow_exception_pattern` 的 266 处里包含 AST 扩展新覆盖的 `except Exception: continue`
> 与 `except Exception: return` 形态——既有正则只覆盖 `pass` 形态。
>
> `first_nth_with_reason` / `wait_for_timeout_with_reason` 是**带业务语义理由**的同类命中，
> 级别为 warning、不阻断——这是规则的既定放行路径（见 §7）。

---

## 3. 命中文件 Top 15

| # | 文件 | 命中处数 | 主要规则 |
|---|---|---|---|
| 1 | `modules/platforms/tiktok/components/date_picker.py` | 82 | swallow / first_nth / wait_for_timeout |
| 2 | `modules/platforms/shopee/components/date_picker.py` | 71 | swallow / first_nth / wait_for_timeout |
| 3 | `modules/platforms/shopee/components/products_export.py` | 64 | swallow / wait_for_timeout / first_nth |
| 4 | `modules/platforms/tiktok/components/login.py` | 55 | first_nth / swallow / wait_for_timeout |
| 5 | `modules/platforms/shopee/components/login.py` | 44 | first_nth / swallow / wait_for_timeout |
| 6 | `modules/platforms/tiktok/components/services_agent_export.py` | 43 | swallow / first_nth / wait_for_timeout |
| 7 | `modules/platforms/miaoshou/components/inventory_export.py` | 36 | first_nth / swallow / wait_for_timeout |
| 8 | `modules/platforms/miaoshou/components/date_picker.py` | 35 | swallow / first_nth / wait_for_timeout |
| 9 | `modules/platforms/tiktok/components/products_export.py` | 26 | first_nth / swallow / wait_for_timeout |
| 10 | `modules/platforms/miaoshou/components/orders_export_base.py` | 24 | first_nth / swallow / wait_for_timeout |
| 11 | `modules/platforms/miaoshou/components/purchase_export.py` | 22 | first_nth / swallow / oversized_function |
| 12 | `modules/platforms/miaoshou/components/filters.py` | 21 | first_nth / swallow |
| 13 | `modules/platforms/miaoshou/components/login.py` | 16 | swallow / first_nth / fixed_sleep |
| 14 | `modules/platforms/shopee/components/shop_switch.py` | 16 | wait_for_timeout / swallow / first_nth |
| 15 | `modules/platforms/shopee/components/services_export_base.py` | 13 | swallow / first_nth |

---

## 4. 平台分布

| 平台 | 文件数 | error 处数 | warning 处数 | 合计 |
|---|---|---|---|---|
| **miaoshou** | 19 | 169 | 16 | 185 |
| **shopee** | 19 | 230 | 4 | 234 |
| **tiktok** | 16 | 249 | 4 | 253 |
| amazon | 7 | 8 | 1 | 9 |
| `modules/platforms/` 直属文件 | 1 | 0 | 0 | 0 |
| **合计** | **62** | **656** | **25** | **681** |

三个目标平台的对比：

- **tiktok** 命中最多（253 处），其中吞异常 100 处、`.first/.nth` 77 处；
- **shopee** 次之（234 处），吞异常 96 处、`wait_for_timeout` 49 处；
- **miaoshou** 最少（185 处），但 `.first/.nth` 77 处仍是三个平台里最突出的问题；
- **amazon** 只有 9 处，主要是 4 个组件缺 `report_step`、3 个组件缺 stable 记录。

### 4.1 平台 × 规则（处数）

**miaoshou**

| 规则 | 处数 |
|---|---|
| `first_nth_usage` | 89 |
| `swallow_exception_pattern` | 75 |
| `wait_for_timeout_usage` | 8 |
| `missing_report_step` | 6 |
| `missing_logger_usage` | 5 |
| `count_is_visible_pattern` | 4 |
| `oversized_function` | 4 |
| `fixed_sleep_usage` | 3 |
| `oversized_class` | 1 |
| `single_signal_navigation` | 1 |

**shopee**

| 规则 | 处数 |
|---|---|
| `swallow_exception_pattern` | 96 |
| `first_nth_usage` | 51 |
| `wait_for_timeout_usage` | 49 |
| `oversized_function` | 13 |
| `missing_report_step` | 8 |
| `count_is_visible_pattern` | 6 |
| `fixed_sleep_usage` | 4 |
| `oversized_class` | 3 |
| `missing_logger_usage` | 3 |
| `single_signal_navigation` | 1 |

**tiktok**

| 规则 | 处数 |
|---|---|
| `swallow_exception_pattern` | 100 |
| `first_nth_usage` | 77 |
| `wait_for_timeout_usage` | 46 |
| `oversized_function` | 11 |
| `missing_report_step` | 7 |
| `count_is_visible_pattern` | 3 |
| `oversized_class` | 3 |
| `single_signal_navigation` | 2 |
| `missing_logger_usage` | 2 |
| `fixed_sleep_usage` | 1 |
| `missing_stable_component_record` | 1 |

**amazon**

| 规则 | 处数 |
|---|---|
| `missing_report_step` | 4 |
| `missing_stable_component_record` | 3 |
| `swallow_exception_pattern` | 1 |
| `single_signal_navigation` | 1 |

---

## 5. 仓库级规则（需 DB）状态

本次快照环境**数据库可用**，仓库级规则实际执行了：

| 项目 | 数值 |
|---|---|
| `core.component_versions` 中 `is_stable=True` 记录数 | 23 |
| `stable_points_to_archived_file`（#6）命中 | **0** |
| `missing_stable_component_record`（#5）命中 | **4** |

缺 stable 记录的 canonical 组件：

| 组件 | 说明 |
|---|---|
| `amazon/date_picker` | 文件在 active 目录，但没有 stable 版本记录 |
| `amazon/login` | 同上 |
| `amazon/navigation` | 同上 |
| `tiktok/navigation` | 同上 |

> **DB 不可用时的行为**：CLI 会打印明确跳过行
> `[SKIP] 数据库不可用，跳过 missing_stable_component_record / stable_points_to_archived_file（原因：...）`，
> 并以退出码 0 结束（`--fail-on none`）。**不会静默当作通过**。
> 引擎导入时不连接数据库，DB 只在 `load_stable_component_records()` 被调用时才连接。

---

## 6. 阶段二切换判据（三条全满足才切换）

依据 `docs/superpowers/specs/2026-10-23-collection-component-lint-gate-design.md` §6：

1. **阶段一已完整跑满一轮，且 miaoshou 平台新增/修改组件零 error**；
2. **仓库级规则（#5 / #6）在 CI 环境能稳定拿到 DB 连接**（无 DB 时有明确的 skip 语义，不静默通过）；
3. **豁免机制（`# lint:ignore[...]` + 无效豁免检测）已上线并有单测覆盖**。

切换方式：CI 步骤改为 `--changed-only --fail-on error`。
**历史违规不阻断**——只有本次改动引入或触及的违规才阻断。

---

## 7. 豁免机制用法

```python
# 行内豁免：作用于注释所在行及其下一行的违规
# lint:ignore[swallow_exception_pattern] —— 探测型候选，失败即换下一个，不值得记日志
except Exception:
    continue

# 文件级豁免：放在文件首行或模块 docstring 之后，对整个文件生效
# lint:ignore-file[first_nth_usage] —— 本文件所有 .first/.nth 均有业务语义
```

规则：

- 行内与文件级豁免**都必须写理由**，理由少于 4 个字符（或为空）视为**无效豁免**：
  额外报一条 `invalid_ignore_comment`（error），且**该豁免不生效**；
- `wait_for_timeout_usage` / `wait_for_timeout_with_reason`、
  `fixed_sleep_usage` / `fixed_sleep_with_reason`、
  `first_nth_usage` / `first_nth_with_reason` 属同一**规则族**，豁免其中之一即放行该族。

---

## 8. 已知局限

- **录制器路径不支持豁免**：`analyze_python_code()` 保持既有 9 条规则**一字未改**，
  录制器保存门禁行为零变化；豁免机制只在文件级分析（`analyze_component_file()`）生效。
- **`swallow_exception_pattern` 文案按形态分两种**：只出现 `pass` 时文案与既有规则一字不差；
  出现 `continue` / `return` 时文案里的形态词随之变化（`except Exception: continue`）。
- **`missing_stable_component_record` 只覆盖 canonical 命名**（`*_export` / 固定组件名），
  非 canonical 文件不参与判定。
- **豁免规则名拼错不会报错**：目前只校验「理由是否有效」，未校验规则名是否存在。
- 本次快照与并行会话对 `modules/platforms/miaoshou/components/` 的改动在同一工作区进行，
  数字对应快照时刻的工作区状态。
