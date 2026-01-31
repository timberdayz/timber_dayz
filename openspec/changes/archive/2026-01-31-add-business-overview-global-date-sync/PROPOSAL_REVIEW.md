# 提案审查：业务概览全局日期同步

## 一、对照现有实现的模块清单

| 模块       | 日期控件           | 粒度支持 | 提案覆盖 | 备注 |
|------------|--------------------|----------|----------|------|
| 核心 KPI   | kpiMonth (月)      | 仅月     | 可选跟随 | 无日/周粒度 |
| 经营指标   | operationalDate    | 仅单日   | 默认跟随 | API 用 month(YYYY-MM-DD) 标识月份 |
| 数据对比   | granularity+date   | 日/周/月 | 默认跟随 | ✓ |
| 店铺赛马   | granularity+date   | 日/周/月 | 默认跟随 | ✓ |
| 流量排名   | granularity+date   | 日/周/月 | 默认跟随 | ✓ |
| 库存滞销   | 无日期控件         | -        | 未纳入   | 仅刷新按钮，正确排除 |
| 清仓排名   | clearanceMonth + clearanceWeek | 月 + 周（两个独立选择器） | 可选跟随 | 结构特殊 |

---

## 二、发现的漏洞与建议

### 1. 核心 KPI 与全局「日/周」不匹配（中）

**问题**：KPI 只有月份选择器，无日/周粒度。当全局为「日」或「周」时，无法按语义同步。

**建议**：在 proposal / spec 中明确：
- 当全局为「月」且 KPI 跟随时，同步为同一月份。
- 当全局为「日」或「周」时，KPI 不参与同步（保持当前月或保持上次手动选择）。

---

### 2. 清仓排名双选择器与全局「日」粒度（中）

**问题**：清仓有「月度」「周度」两个独立选择器。当全局为「日」时，没有清晰映射规则。

**建议**：在 design.md 中补充：
- 全局=月：可选同步 clearanceMonth；clearanceWeek 保持不变或取该月第一周。
- 全局=周：可选同步 clearanceWeek；clearanceMonth 保持不变或取该周所在月。
- 全局=日：两者均不同步，或均从该日派生（日→所在周→clearanceWeek，日→所在月→clearanceMonth）。

---

### 3. 平台筛选（kpiPlatform）未纳入同步范围（低）

**现状**：kpiPlatform 同时影响 KPI、数据对比、经营指标，但不在全局日期同步范围内。

**建议**：在 proposal 的 Non-Goals 或「技术细节」中说明：平台筛选保持独立，不纳入本次全局同步。若未来要统一，可单独提案。

---

### 4. 流量排名 value-format 与 UTC 偏差（低）

**现状**：`loadTrafficRanking` 使用 `dateValue.toISOString().split("T")[0]`，存在 UTC 偏差风险（与店铺赛马曾修复的问题类似）。

**建议**：在 tasks.md 中增加一项：实现时统一流量排名的 value-format 与本地日期拼接，消除 toISOString UTC 偏差。

---

### 5. 初始化加载顺序与重复请求（中）

**问题**：若先执行现有 `refreshData()` 再设置全局日期，会先用各模块默认日期加载一次，再被全局覆盖，导致重复请求。

**建议**：在 tasks.md 2.x 中明确：
- 页面加载顺序：先初始化 globalDate、useGlobalDate，再调用各模块 loadXxx。
- 或在 onMounted 中先设置全局日期，再统一触发 refreshData，避免「默认值加载 → 全局覆盖」双重请求。

---

### 6. 快速切换日期时的防抖（低）

**问题**：用户快速切换全局日期可能触发多次并行请求。

**建议**：在 design.md 的「Risks / Trade-offs」中补充：对全局日期 watch 增加防抖（如 200–300ms），减少无效请求。

---

### 7. 经营指标「今日销售额」等语义（低）

**现状**：经营指标有「今日销售额」「今日销售单数」，当用户选「上周一」时，语义上为「该日销售」，但文案仍为「今日」。

**建议**：在 design 或 spec 中说明：跟随全局时，`operationalDateLabel` 应根据 operationalDate 动态显示（如「9月1日」而非「今日」），当前实现已有类似逻辑，可保持一致性。

---

### 8. Spec Scenario 覆盖（低）

**现状**：spec 未覆盖「全局=日时，KPI 和清仓不跟随」的边界场景。

**建议**：在 specs/dashboard/spec.md 中增加 Scenario：
- **全局为日/周时 KPI 不跟随**：当全局粒度为日或周时，核心 KPI 保持当前月份，不随全局变更。

---

### 9. 清仓排名 API 参数（信息）

**现状**：前端传 `month`、`week`、`granularity`，而后端 `clearance-ranking` 定义使用 `start_date`、`end_date`。需确认实际请求参数与后端是否一致。

**建议**：实现前核实 clearance 相关 API 的入参格式，若有差异需在实现任务中一并修正。

---

## 三、总结

| 类型     | 数量 | 建议 |
|----------|------|------|
| 需补充说明 | 4  | 在 proposal/design/spec 中补全 |
| 需增加任务 | 2  | 初始化顺序、流量 UTC 修复 |
| 需实现时注意 | 2  | 防抖、清仓 API 参数 |
| 信息性    | 1  | 清仓 API 参数核实 |

建议在实施前更新 proposal、design、tasks、spec，纳入上述修改，以降低实现阶段返工风险。
