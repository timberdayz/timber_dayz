# 采集组件 lint 门禁设计（spec §5.4 L3-1）

> **状态**：设计稿，**批次 3 落地**。本批次（批次 1）只出设计，不实现任何 lint 代码。
>
> **上游依据**：`docs/superpowers/specs/2026-10-23-miaoshou-inventory-domain-remediation-design.md` §5.4 L3-1（验收项 C1 / C2 / C3）。
> **规范依据**：`docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md` §13（五条强约束）、§16（`.first`/`.nth`）、`docs/DEVELOPMENT_RULES/TESTING_AND_QUALITY.md:211,213`（函数 ≤50 行 / 类 ≤500 行）。

---

## 1. 要解决的问题

**一句话**：把《规范》§13 的强约束从「靠人记得」变成「机器判定」，并且**能对手写组件生效**。

现有 lint 有两个硬伤：

1. **覆盖面**：`_analyze_python_code_for_lints()` 挂在**录制器保存路径**上（`component_recorder.py:1069` 预览、`:1134` 生成、`:1257` 保存）。手写组件（`modules/platforms/**/*.py`）**根本不经过那条路径**——本次妙手库存域的 4 个反模式全部手写，因此全部逃过。
2. **规则密度**：现有 5 条 error 规则中，`swallow_exception_pattern` 的正则是 `except\s+Exception\s*:\s*pass`，**只覆盖 `pass` 形态**。`except Exception: continue` / `except Exception: return` 两种更常见的吞异常写法**一条都不检**。

---

## 2. 现状事实（2026-10-23 实测）

### 2.1 现有 lint 的位置与形态

真实实现：**`backend/domains/collection/routers/component_recorder.py:458`**

```python
def _analyze_python_code_for_lints(python_code: str) -> Dict[str, List[Dict[str, str]]]:
    """返回 {"errors": [...], "warnings": [...]}，每项形如 {"type": ..., "message": ...}"""
```

规则清单（**9 条**，不是 spec 里写的 5 条——另 4 条是 `_with_reason` 形态的 warning）：

| type | 位置 | 级别 | 判定 |
|---|---|---|---|
| `syntax_error` | `:478` | error | `ast.parse` 抛 `SyntaxError` |
| `wait_for_timeout_usage` | `:507` | error | 有 `wait_for_timeout(` 且**邻近无理由注释** |
| `wait_for_timeout_with_reason` | `:514` | warning | 有 `wait_for_timeout(` 且**邻近有理由注释** |
| `fixed_sleep_usage` | `:533` | error | 有 `time.sleep(` / `asyncio.sleep(` 且邻近无理由注释 |
| `fixed_sleep_with_reason` | `:540` | warning | 同上，邻近有理由注释 |
| `count_is_visible_pattern` | `:547` | error | 正则 `count\(\)\s*>\s*0.*is_visible\(` |
| `swallow_exception_pattern` | `:554` | error | 正则 `except\s+Exception\s*:\s*pass` |
| `first_nth_usage` | `:569` | error | 有 `.first` / `.nth(` 且邻近无理由注释 |
| `first_nth_with_reason` | `:576` | warning | 同上，邻近有理由注释 |

**关键：`_has_reason_comment(i, reason_keywords)`（`:486`）已经实现了「有注释才放行」语义**——检查**当前行 + 前两行**是否存在以 `#` 开头且包含指定关键词的注释。

> 这正是 spec §16 要求的形态。**新规则必须复用这套语义，不要重复实现「带理由则放行」。**

### 2.2 调用点（决定了「为什么手写组件没被覆盖」）

| 位置 | 场景 | 是否阻断 |
|---|---|---|
| `component_recorder.py:1069` | 录制器预览 | 否，只回显 |
| `component_recorder.py:1134` | 录制器生成 | 否，只回显 |
| `component_recorder.py:1257` | 录制器保存 | **是**，受 `LINT_BLOCK_SAVE_ON_ERROR`（默认 `true`）控制 |

**没有第 4 个调用点。** 手写组件不经过录制器 → 现有 lint 对它们**零覆盖**。

### 2.3 反模式基线（`modules/platforms/**`，100 个 `.py` 文件）

| 形态 | 出现次数 |
|---|---|
| `except Exception:` 块总数 | 1081 |
| ├ `except Exception: pass` | 486 |
| ├ `except Exception: continue` | 236 |
| └ `except Exception: return` | 95 |
| `report_step(` 调用 | 16（**仅 2 个文件**用到） |
| 类总数 | 103 |

> **这组数字是「告警 → 阻断」两阶段策略的直接依据**：一次性全量阻断会爆出 1000+ 处违规，必然打挂流水线。

### 2.4 stable 记录基线

`core.component_versions`：**27 条记录，23 条 `is_stable=True`**（shopee 9 / miaoshou 8 / tiktok 6）。

> 注：批次 1 的 L0-2 已把 `miaoshou/inventory_snapshot_export` 从 24 条 stable 清理到 23 条。详见 `scripts/fix_orphan_stable_component_versions.py`。

---

## 3. 接入点设计

### 3.1 引擎抽到共享模块（满足验收 C1「不重复实现」）

```
backend/services/collection_component_lint.py     ← 新增：唯一规则实现
        ▲                              ▲
        │ import                       │ import
component_recorder.py:458        scripts/lint_collection_components.py   ← 新增：CLI
（改为薄转发，行为不变）              （CI / pre-commit 入口）
```

- `backend/services/collection_component_lint.py` 导出：
  - `analyze_python_code(python_code: str) -> dict`（**原样搬走**现有 9 条规则，规则名与判定**一字不改**）
  - `analyze_component_file(path: Path) -> dict`（新增：文件级 + 仓库级检查，见 §4）
  - `LintIssue` 数据结构（`type` / `severity` / `message` / `line` / `rule`）
- `component_recorder.py` 的 `_analyze_python_code_for_lints` 改为**一行转发**到 `analyze_python_code`，三个调用点**不改**。
  - 验收方式：录制器既有测试必须全绿（行为零变化）。

> **命名说明**：spec §5.4 提到过 `backend/services/component_recorder_lint.py`，该文件**不存在**。本设计用 `collection_component_lint.py`，避免与「录制器」这个 UI 概念绑定——它服务的是**采集组件**这一类对象，不只是录制器产物。

### 3.2 CLI 入口

```
scripts/lint_collection_components.py
```

| 参数 | 含义 |
|---|---|
| `--paths <p1,p2,...>` | 指定要检查的文件/目录（默认：全量 `modules/platforms/**`） |
| `--changed-only` | 只检查**相对基线被修改过**的组件（阶段二阻断用） |
| `--base <ref>` | `--changed-only` 的比较基线，默认 `origin/main` |
| `--severity error\|warning\|all` | 最低报告级别，默认 `all` |
| `--format text\|json` | 输出格式，默认 `text`（CI 用 `text`，本地排障可用 `json`） |
| `--fail-on error\|none` | 命中 error 时退出码非 0，默认 `error` |

**退出码**：`0` = 通过；`1` = 有 error 级问题；`2` = 执行异常（配置/依赖问题）。

### 3.3 CI 接入

在 `.github/workflows/ci.yml` 的 `test` job 里，**紧跟现有 "Linting"（ruff）之后**新增一步：

```yaml
- name: Collection component lint
  run: |
    python scripts/lint_collection_components.py --paths "${{ steps.changed-python.outputs.files }}" --fail-on none
```

> **阶段一（告警模式）**：`--fail-on none`——只打印，不阻断。
> **阶段二（阻断）**：改为 `--changed-only --fail-on error`。
>
> **注意**：CI 的 `pytest` 步骤只跑**改动的测试文件**（`ci.yml:189`），而 lint 是**按文件**跑的——两者粒度不同，不要混用。

---

## 4. 规则清单

### 4.1 已有规则（直接复用，不改判定）

| 检查项 | 规则 type | 级别 | 误报豁免 |
|---|---|---|---|
| 无理由固定等待 | `wait_for_timeout_usage` | error | 邻近 2 行内有含「固定等待 / reason / 验证码 / 回传 / 动画 / 节奏」的注释 |
| 有理由固定等待 | `wait_for_timeout_with_reason` | warning | 同上（已是豁免态） |
| 无理由固定 sleep | `fixed_sleep_usage` | error | 邻近有含「固定等待 / 验证码 / 回传 / 等待 / reason / 节奏 / 动画」的注释 |
| 有理由固定 sleep | `fixed_sleep_with_reason` | warning | 同上 |
| 单次 `count()` + `is_visible()` | `count_is_visible_pattern` | error | `# lint:ignore[count_is_visible_pattern]` |
| `except Exception: pass` | `swallow_exception_pattern` | error | `# lint:ignore[swallow_exception_pattern]` |
| `.first` / `.nth(` 无邻近业务语义注释 | `first_nth_usage` | error | 邻近有含「业务语义 / 第n / nth / first-nth-justified / 有序 / 第 」的注释 |
| `.first` / `.nth(` 有邻近注释 | `first_nth_with_reason` | warning | 同上（已是豁免态） |
| Python 语法错误 | `syntax_error` | error | — |

### 4.2 扩展既有规则

| 检查项 | 规则 type | 级别 | 判定方式 | 误报豁免 |
|---|---|---|---|---|
| `except Exception: continue` | `swallow_exception_pattern`（**扩展**） | error | AST 判定：`ExceptHandler` 的 type 捕获 `Exception` 且 body 末条是 `continue` | `# lint:ignore[swallow_exception_pattern]` |
| `except Exception: return` | `swallow_exception_pattern`（**扩展**） | error | AST 判定：同上，body 末条是 `return` | 同上 |

> **实现要求**：扩展必须用 **AST**，不要用正则。正则要处理换行缩进、嵌套 `try`、多分支 `except` 等情况，极易漏判；AST 判定是确定性的。
>
> 现有 `swallow_exception_pattern` 的正则 `except\s+Exception\s*:\s*pass` 在真实代码里同样应改用 AST（`pass` 出现在 `except` body 的**任意位置**都算吞异常，不只是末条）。

### 4.3 新增规则

| # | 检查项 | 规则 type | 级别 | 判定方式 | 误报豁免 |
|---|---|---|---|---|---|
| 1 | 关键步骤缺 `report_step` | `missing_report_step` | error | 组件类定义了 `run()` 但整个文件**零** `report_step(` 调用 | `# lint:ignore[missing_report_step]` |
| 2 | 未接 `ctx.logger` | `missing_logger_usage` | warn | 组件文件里出现 `self.logger` 但**没有** `ctx.logger` / `logger=` 注入痕迹；或组件类继承了 `ComponentBase` 却从不读 `self.logger` | `# lint:ignore[missing_logger_usage]` |
| 3 | 函数 > 50 行 | `oversized_function` | error | AST：函数体 `end_lineno - lineno + 1 > 50` | `# lint:ignore[oversized_function]`（需同时写明拆分计划） |
| 4 | 类 > 500 行 | `oversized_class` | error | AST：类体 `end_lineno - lineno + 1 > 500` | `# lint:ignore[oversized_class]` |
| 5 | 组件无 stable 记录 | `missing_stable_component_record` | error | 组件文件名匹配 `*_export.py` / `*_config.py` 之外的 canonical 命名（判定复用 `backend/services/collection_component_topology.py` 的 `is_canonical_component_filename`），但 `core.component_versions` 里没有 `is_stable=True` 的同名记录 | `# lint:ignore[missing_stable_component_record]` |
| 6 | stable 记录指向 `archive/` 或缺失文件 | `stable_points_to_archived_file` | error | 判定**直接复用** `backend/services/active_collection_components.py` 的 `is_missing_component_file()`（批次 1 的 L0-2 刚落地） | `# lint:ignore[stable_points_to_archived_file]` |
| 7 | 导航单信号 | `single_signal_navigation` | warn | 导航类组件里，页面就绪判定**只有一个**信号（无「URL 变化」+「元素可见」双信号） | `# lint:ignore[single_signal_navigation]` |
| 8 | 缺重试预算声明 | `missing_retry_budget` | warn | 组件内出现 `click(` / `wait_for(` 且**无界**（无 timeout 或 timeout 为常量上限）时，要求显式声明重试预算（`RetryStrategy` 或常量 timeout） | `# lint:ignore[missing_retry_budget]` |

### 4.4 规则级别的严重度汇总

| 级别 | 规则数 | 阶段二是否阻断 |
|---|---|---|
| error | 已有 6（含 `syntax_error`）+ 扩展 0（并入 `swallow_exception_pattern`）+ 新增 4（#1 #3 #4 #5 #6） | **是** |
| warning | 已有 4（`*_with_reason`）+ 新增 4（#2 #7 #8） | 否（只告警） |

> **注意 #5 / #6 是仓库级检查，不随单个文件走**：它们查的是 DB 里的 stable 记录。在 CI 里需要数据库连接；**无 DB 的环境（本地 pre-commit、fork 的 PR）必须自动降级为跳过**并明确打印「已跳过 DB 相关检查」，**不能静默当作通过**。

---

## 5. 豁免机制

### 5.1 行内豁免

```python
# lint:ignore[swallow_exception_pattern] —— 探测型候选，失败即换下一个，不值得记日志
except Exception:
    continue
```

- 语法：`# lint:ignore[<rule1>,<rule2>]`（逗号分隔），可带行尾说明。
- 生效范围：**该行所在的那条违规**。
- **必须写理由**：行内 `# lint:ignore[...]` 后面若没有任何非空文本，判为**无效豁免**并单独报一条 `invalid_ignore_comment`（error）——防止「无脑加豁免」变成新的技术债。
  - 例外：允许 `# lint:ignore[rule]  理由` 中理由少于 4 个字符时同样判为无效。

### 5.2 文件级豁免

```python
# lint:ignore-file[first_nth_usage] —— 本文件所有 .first/.nth 均有业务语义
```

放在文件**首行或 docstring 之后**。

### 5.3 为什么 `.first` 用「有注释才放行」而不是直接禁止

`.first` / `.nth(` 在 Playwright 里是**缩小作用域**的手段，本身不是错误。妙手页面上「导出搜索的商品」这类菜单项确实只有一个，直接禁止会逼出更糟的写法（更宽的 CSS 选择器 + `wait_for` 轮询），反而增加脆弱性。

所以规则形态是「**用了 `.first`/`.nth` 就必须说明为什么它是唯一命中**」：

- 通过条件：邻近 2 行内有业务语义注释（复用既有 `_has_reason_comment`，关键词含「业务语义 / 第n / nth / 有序 / 第 」）。
- 未通过：error，提示「先收敛作用域，或补充业务语义注释后再使用」。

这与《规范》§16 一致，也与既有 `first_nth_usage` 的实现完全一致——**不新增第二套语义**。

---

## 6. 告警 → 阻断的两阶段策略

### 阶段一：告警模式（批次 3 第一轮）

- CI 跑 `python scripts/lint_collection_components.py --fail-on none`，**只打印不阻断**。
- 同时产出一份基线快照（`docs/guides/COLLECTION_COMPONENT_LINT_BASELINE.md`），记录每个文件的违规条数。
- 目标：**先把 miaoshou 平台清干净**，再扩到 shopee / tiktok。

### 阶段二：对新增/修改组件强制阻断

- 切换判据（**三条全满足**才切换）：
  1. 阶段一已完整跑满一轮，且 miaoshou 平台**新增/修改**组件零 error；
  2. 仓库级规则（#5 #6）在 CI 环境**能稳定拿到 DB 连接**（无 DB 时有明确的 skip 语义，不静默通过）；
  3. 豁免机制（`# lint:ignore[...]` + 无效豁免检测）已上线并有单测覆盖。
- 切换方式：CI 步骤改为 `--changed-only --fail-on error`。
  - `--changed-only` 复用既有 `scripts/ci_changed_python_files.py` 的改动文件检测能力（`ALLOWED_PREFIXES` 已含 `modules/`），不另造轮子。
  - **历史违规不阻断**——只有本次改动引入或触及的违规才阻断。
- 切换后再经过一轮观察期（≥2 周、≥20 次合并），无「因 lint 阻断而卡住的正常需求」后，才考虑对**全量**组件开启 error 阻断。

### 阶段三（可选，不在本设计范围）

把 `--fail-on error` 从「只对改动文件」扩到「全量」。**需要先把历史违规清到 0 或全部显式豁免**，成本极高，不建议在批次 3 做。

---

## 7. 与 spec §5.4 L3-2 / L3-3 / L3-4 的边界

| 条款 | 内容 | 与本设计的关系 |
|---|---|---|
| **L3-1** | 把《规范》§13 强约束做成机器 lint | **本设计全部内容** |
| **L3-2** | 规范补三处空白：①重试口径冲突（以《规范》§6 为准）②同平台多域共用 filters 的结构约定 ③archive 前置条件的机器校验 | **有交集但不重复**：③「archive 前置条件的机器校验」由本设计的 `stable_points_to_archived_file`（#6）**在 CI 侧前置实现**；L3-2 负责把规则写进《规范》正文。本设计**不改《规范》**。①的重试口径由 `missing_retry_budget`（#8）**感知**，但不裁决口径——口径以《规范》为准。 |
| **L3-3** | 收紧「进入 active 清单」的准入三门：①有 `CANONICAL_RUNTIME_ISSUES.md` 条目 ②有**行为测试**（不接受源码字符串断言）③有 stable 记录且指向非 archive 文件 | **部分重叠**：第③门由本设计 #5 #6 覆盖。第①②门是**准入流程**，不是 lint 规则，本设计**不做**（见 §7.1）。 |
| **L3-4** | 修「域可勾选但无组件」的静默剪枝（前端按平台过滤 + 保存时校验 + `skipped_targets` 回写） | **完全无关**，不涉及组件源码 |

### 7.1 明确不做的事

- **不做**「源码字符串断言」检测。理由：这类断言不是「规范违反」，而是**测试写法问题**，且它们防的是「代码被重排」而非「行为变了」。批次 1 的 L1-3 已经把妙手库存域的这类断言全部换成行为测试——靠**移除**而不是靠 lint 禁止。
- **不做** `platform` / `data_domain` / `granularity` 等业务口径校验。理由：spec §1.3 明确「采集配置业务语义、粒度口径、入库链路一律不动」。
- **不做**「必须有 `CANONICAL_RUNTIME_ISSUES.md` 条目」的检查。理由：文档完备性无法自动化判定得可靠，硬做只会产生误报。

---

## 8. 验收（对应 spec §7.3 C1 / C2 / C3）

| # | 验收项 | 判定方式 |
|---|---|---|
| **C1** | lint 可对手写组件运行（**不依赖录制器路径**），且**复用** `component_recorder.py` 的既有规则，**不重复实现** | ① `component_recorder.py` 里不再有规则实现（只有一行转发）；② `scripts/lint_collection_components.py` 能对手写组件报出 `first_nth_usage` / `swallow_exception_pattern` / `oversized_function` 等；③ 录制器既有测试全绿（行为零变化） |
| **C2** | lint 覆盖 §5.4 L3-1 表中**全部**检查项，**逐项可验** | 每条规则有**至少一个单测**：一个「应报」用例 + 一个「应放行」用例（带理由注释 / 带豁免） |
| **C3** | 告警模式运行一轮后，转为对新增/修改组件强制阻断 | 阶段一报告 + 基线快照落库；阶段二 CI 步骤参数变更的 commit 存在，且 `--changed-only` 模式下历史违规不阻断 |

**新增的验收细节**：

- **无效豁免检测**必须有单测（写了 `# lint:ignore[...]` 但没写理由 → 报 `invalid_ignore_comment`）。
- **无 DB 环境**必须自动跳过 #5 #6 并**打印跳过原因**，不允许静默通过。

---

## 9. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| 一次性全量阻断打挂流水线 | CI 红灯，阻塞所有需求 | §6 两阶段策略：先告警，`--changed-only` 后阻断 |
| 规则误报淹没真实问题 | 开发者开始整体忽略 lint 输出 | 每条新规则**必须**先有「应放行」用例；豁免机制可用 |
| 无 DB 的 CI 环境让 #5 #6 静默通过 | 孤儿 stable 记录重新出现 | 无 DB 时打印明确的 skip 行；阶段二的切换判据要求 DB 稳定可用 |
| 抽走 lint 引擎影响录制器行为 | 录制器保存门禁变化 | `component_recorder.py` 改为**一行转发**，规则判定一字不改；既有录制器测试必须全绿 |
| `oversized_function` 命中 `executor_v2.py` 等历史大文件 | 阻断噪音 | 阶段二只对**改动文件**阻断；历史大文件用文件级豁免 + 拆分计划显式记录 |

---

## 10. 落地清单（批次 3）

1. `backend/services/collection_component_lint.py`：抽出现有 9 条规则 + 扩展 `swallow_exception_pattern`（AST）+ 新增 8 条。
2. `backend/domains/collection/routers/component_recorder.py`：`_analyze_python_code_for_lints` 改为转发。
3. `scripts/lint_collection_components.py`：CLI。
4. `backend/tests/test_collection_component_lint.py`：逐规则单测（应报 / 应放行 / 豁免 / 无效豁免）。
5. `.github/workflows/ci.yml`：新增 lint step（阶段一 `--fail-on none`）。
6. `docs/guides/COLLECTION_COMPONENT_LINT_BASELINE.md`：阶段一基线快照。
7. 观察期结束后：CI 步骤改 `--changed-only --fail-on error`，并提交「阶段二切换」说明。
