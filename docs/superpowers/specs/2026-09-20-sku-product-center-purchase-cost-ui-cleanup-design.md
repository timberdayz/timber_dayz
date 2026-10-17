# 商品中心 SKU 资料页 — 采购成本展示列精简与时间格式本地化

**状态**: 设计稿待评审
**日期**: 2026-09-20
**范围**: 仅商品中心 SKU 资料页前端展示层（[`ProductCenter.vue`](frontend/src/domains/business/views/ProductCenter.vue)）。优化 SKU 资料 tab 内「采购成本来源」「采购成本确认时间」两列的展示。
**非范围**: 不修改数据库 schema / 不写新迁移 / 不恢复已删除的妙手导入脚本 / 不修改后端 API / 不修改 ORM / 不修改 Pydantic schema / 不修改飞书投影字段 / 不修改 SPU 资料页 / 不修改 `purchase_cost_confidence` 字段。

---

## 1. 背景与动机

SKU 资料页（用户提供截图）当前展示两个对用户不友好的元数据列：

### 1.1 「采购成本来源」— 冗余字段

- 后端字段：[`core.dim_erp_sku.purchase_cost_source`](modules/core/db/schema_parts/dimensions.py#L201)（`VARCHAR(64) NULL`），由迁移 [`20260910_product_profit_finalization.py:32-36`](current_migrations/versions/20260910_product_profit_finalization.py#L32-L36) 引入。
- 前端：[`ProductCenter.vue:248`](frontend/src/domains/business/views/ProductCenter.vue#L248) 只读列 `{{ row.purchase_cost_source || "待补充" }}`，**前端不可编辑、不可选择**。
- 写入路径：当前生产代码中**只有** [product_center.py:1516](backend/domains/business/routers/product_center.py#L1516)（PO 补充接口硬编码 `"purchase_order"`）；历史截图里大量出现的 `"妙手导入"` 字面值来自已被 [`422ea91e feat:21312`](../../) 删除的 `scripts/import_purchase_prices.py` 脚本（[plan 文档 §5.2](2026-09-18-purchase-price-import.md)）。
- **结论**：字段对终端用户没有信息增量，属于"系统内部水印"泄漏到 UI。

### 1.2 「采购成本确认时间」— 技术格式泄漏

- 后端字段：`DateTime(timezone=True)`，写入用 `datetime.now(timezone.utc)`（[product_center.py:1498](backend/domains/business/routers/product_center.py#L1498)）；Pydantic v2 默认序列化输出 ISO 8601 字符串 `2026-09-18T08:13:41.088218Z`（UTC + 微秒 + Z 后缀）。
- 前端：[`ProductCenter.vue:249`](frontend/src/domains/business/views/ProductCenter.vue#L249) 直接渲染，`{{ row.purchase_cost_confirmed_at || "-" }}`，**无任何 dayjs / toLocaleString / formatDate 格式化**。
- **问题**：`T` 分隔符、`Z` UTC 后缀、微秒精度对业务用户均无意义；中国用户难以解读 UTC 时间。

### 1.3 设计原则

按 [[minimal-fix-preference]] 原则——只针对问题根因做最小修复。问题根因在**前端展示层**，不在数据层：
- 不动 schema / 不动迁移 → 避免触发 schema-migration 对齐 CI 风险（参考 [schema-migration-alignment-script](schema-migration-alignment-script.md)）
- 不动写入路径 → 避免破坏现有 PATCH 流程
- 不动妙手脚本 → 已被删除，用户业务不依赖，恢复无收益

---

## 2. 决策

### 2.1 「采购成本来源」列：前端移除，字段保留

**改动**：
- 删除 [`ProductCenter.vue:248`](frontend/src/domains/business/views/ProductCenter.vue#L248) 的 `<el-table-column label="采购成本来源">` 块
- 同步清理 `blankSku()` 工厂中的 `purchase_cost_source: "manual"` 默认值（[`ProductCenter.vue:925-944`](frontend/src/domains/business/views/ProductCenter.vue#L925-L944)），避免新建行携带无效字段（SPU 侧的 `blankSpu()` 不在本文件改动范围）

**保持不变**：
- 数据库列 `core.dim_erp_sku.purchase_cost_source`（同名字段在 `finance.po_lines`、`finance.sku_profit_estimates` 上也不动）
- ORM [`modules/core/db/schema_parts/dimensions.py:201`](modules/core/db/schema_parts/dimensions.py#L201)
- Pydantic schema [`backend/schemas/product_center.py`](backend/schemas/product_center.py) 中所有 `purchase_cost_source` 字段定义
- API 路由 [`backend/domains/business/routers/product_center.py`](backend/domains/business/routers/product_center.py) 中所有引用
- 飞书投影 [`feishu_projection_service.py:212`](backend/services/feishu_projection_service.py#L212)（独立于本 UI）
- 历史 `purchase_cost_source = '妙手导入'` 数据**不主动清理**

**理由**：字段在 schema 中保留可作审计兜底；移除前端列不影响后端行为；不写迁移 = 零停机风险。

### 2.2 「采购成本确认时间」列：本地化格式

**目标格式**：`YYYY-MM-DD HH:mm`（Asia/Shanghai, UTC+8）

示例：`2026-09-18T08:13:41.088218Z` → `2026-09-18 16:13`

**实现**：
- 在 [`ProductCenter.vue`](frontend/src/domains/business/views/ProductCenter.vue) 内**就近**（不污染 [`utils/date.js`](frontend/src/utils/date.js)）：
  1. 顶部 `<script setup>` 引入 `dayjs` 与 `dayjs/plugin/timezone`、`dayjs/plugin/utc`
  2. 调用 `dayjs.extend(timezone); dayjs.extend(utc);`
  3. 定义 helper：`const formatPurchaseTime = (iso) => iso ? dayjs(iso).tz('Asia/Shanghai').format('YYYY-MM-DD HH:mm') : '-';`
- 列渲染改为：`{{ formatPurchaseTime(row.purchase_cost_confirmed_at) }}`
- 空值保留 `'-'`

**为何不复用 [`utils/date.js`](frontend/src/utils/date.js)**：
- 该工具函数仅暴露 `formatDateRange`、`getToday` 等纯本地日期工具，未引入 timezone/utc 插件
- 引入 tz/utc 到 utils 会全局修改 dayjs 行为，可能影响其他页面的 `dayjs()` 调用（虽然 extend 是 idempotent，但增加认知负担）
- 局部 extend 更符合最小修复原则

**为何不直接改后端 Pydantic 序列化**：
- 涉及 Pydantic model 字段类型变化（`datetime` → 自定义 `str`），影响所有 API 消费者（飞书投影、其他前端页面、移动端），属于破坏性变更
- 前端格式化是公认的标准做法（前后端解耦）

### 2.3 妙手导入脚本：不恢复

- `scripts/import_purchase_prices.py` 当前不在工作区（已被 `422ea91e feat:21312` 删除）
- 用户访谈明确：不知道该脚本存在
- 当前生产流程不依赖此脚本
- **不恢复、不重建、不写迁移清理历史 `妙手导入` 字面值**

---

## 3. 改动清单

### 3.1 前端文件改动

| 文件 | 改动 |
|---|---|
| [`ProductCenter.vue`](frontend/src/domains/business/views/ProductCenter.vue) | 1) 顶部 `<script setup>` 添加 `import dayjs from 'dayjs'; import timezone from 'dayjs/plugin/timezone'; import utc from 'dayjs/plugin/utc';` 和 `dayjs.extend(timezone); dayjs.extend(utc);`<br>2) 添加 helper：`const formatPurchaseTime = (iso) => iso ? dayjs(iso).tz('Asia/Shanghai').format('YYYY-MM-DD HH:mm') : '-';`<br>3) 删除 [L248](frontend/src/domains/business/views/ProductCenter.vue#L248) `<el-table-column label="采购成本来源">` 整块（3 行）<br>4) 修改 [L249](frontend/src/domains/business/views/ProductCenter.vue#L249) `<el-table-column label="采购成本确认时间">` 模板：`{{ row.purchase_cost_confirmed_at \|\| "-" }}` → `{{ formatPurchaseTime(row.purchase_cost_confirmed_at) }}`<br>5) 在 `blankSku()` 工厂（[L925-944](frontend/src/domains/business/views/ProductCenter.vue#L925-L944)）中删除 `purchase_cost_source: "manual"` 字段；`purchase_cost_confidence: "low"` 不动（保留后端契约） |

### 3.2 测试断言改动

[`productCenterUi.test.mjs:105-114`](frontend/tests/productCenterUi.test.mjs#L105-L114) 当前断言：

```js
test("SKU 资料按 CNY 维护采购成本、周转类型和参考仓储天数", () => {
  assert.match(source, /采购成本来源/);          // ← 本次：改为 doesNotMatch
  assert.match(source, /采购成本确认时间/);       // ← 本次：保留
  assert.match(source, /周转类型/);
  assert.match(source, /参考仓储天数/);
  assert.match(source, /fast.*30|30.*fast/);
  assert.match(source, /normal.*60|60.*normal/);
  assert.match(source, /slow.*90|90.*slow/);
  assert.doesNotMatch(source, /label="币种"/);
});
```

更新为：

```js
test("SKU 资料按 CNY 维护采购成本、周转类型和参考仓储天数", () => {
  // 「采购成本来源」列已移除（2026-09-20 优化），字段仍在 schema 中供审计
  assert.doesNotMatch(source, /采购成本来源/);
  // 「采购成本确认时间」列保留，新增 Asia/Shanghai 本地化格式
  assert.match(source, /采购成本确认时间/);
  assert.match(source, /formatPurchaseTime/);
  assert.match(source, /tz\(['"]Asia\/Shanghai['"]\)/);
  // dayjs.extend 是全局 mutation，断言避免后续重构误删导致 helper 静默失效
  assert.match(source, /dayjs\.extend\(timezone\)/);
  assert.match(source, /dayjs\.extend\(utc\)/);
  assert.match(source, /周转类型/);
  assert.match(source, /参考仓储天数/);
  assert.match(source, /fast.*30|30.*fast/);
  assert.match(source, /normal.*60|60.*normal/);
  assert.match(source, /slow.*90|90.*slow/);
  assert.doesNotMatch(source, /label="币种"/);
});
```

测试名加注释说明移除原因，避免后续 review 时困惑。

### 3.3 不改动的文件

- [`productCenter.js`](frontend/src/api/productCenter.js) — 接口契约不变
- [`utils/date.js`](frontend/src/utils/date.js) — 不引入 timezone/utc 插件，避免全局影响
- `backend/...` 所有文件
- `current_migrations/versions/*`
- `modules/core/db/schema_parts/dimensions.py`
- `backend/schemas/product_center.py`
- `backend/services/feishu_projection_service.py` — 飞书投影独立
- `docs/superpowers/specs/2026-09-18-purchase-price-import-design.md` — 描述的是已删除脚本

---

## 4. 验证

### 4.1 前端构建

```bash
cd frontend
npm run build
# 期望：无报错、无 TS 错误、无 ESLint 警告
```

### 4.2 前端测试

```bash
cd frontend
npm test
# 期望：productCenterUi.test.mjs 通过（更新后的断言）
```

### 4.3 视觉验证（手动）

打开商品中心 → SKU 资料 tab：

1. 「采购成本来源」列已消失
2. 「采购成本确认时间」列显示北京时间，格式 `2026-09-18 16:13`（原 `2026-09-18T08:13:41.088218Z`）
3. 无采购成本确认时间的行显示 `-`
4. SKU 资料页列数从 N 减到 N-1

### 4.4 数据完整性（不动数据，仅事后核对）

```sql
-- 仅作记录，本次不动数据
SELECT COUNT(*) FROM core.dim_erp_sku WHERE purchase_cost_source = '妙手导入';
-- 期望：与改动前数量一致（数据未变化）

-- 确认新格式生效需前端展示层验证
```

---

## 5. 回滚

改动仅限 2 个前端文件，回滚方式：

```bash
git checkout HEAD -- \
  frontend/src/domains/business/views/ProductCenter.vue \
  frontend/tests/productCenterUi.test.mjs
```

无需数据库回滚、无需服务重启。

---

## 6. 后续可选清理（不在本次范围）

如未来确认 `purchase_cost_source` 字段无审计价值，可走单独 spec：

1. 写新 Alembic 迁移：`ALTER TABLE core.dim_erp_sku DROP COLUMN purchase_cost_source;`（同名字段在 `finance.po_lines`、`finance.sku_profit_estimates` 上一并清理）
2. 同步清理 ORM、Pydantic schema、API、飞书投影、所有测试断言
3. 历史 `purchase_cost_source = '妙手导入'` 数据随列删除而消失（不可逆，需先确认无审计要求）

明确**不在**本次 spec 范围。

---

## 7. 不做的事（防越权）

- ❌ 不修改数据库 schema、不写新迁移
- ❌ 不恢复 `scripts/import_purchase_prices.py` 妙手导入脚本
- ❌ 不清理历史 `purchase_cost_source = '妙手导入'` 数据
- ❌ 不修改后端 API / ORM / Pydantic schema / 飞书投影
- ❌ 不修改 SKU 资料页外的任何页面（SPU 资料、采购订单行、利润测算页等）
- ❌ 不修改 `purchase_cost_confidence` 字段（与本次问题无关）
- ❌ 不在 [`utils/date.js`](frontend/src/utils/date.js) 中引入 timezone/utc（避免全局影响）
- ❌ 不修改 Pydantic 后端序列化（破坏性变更，影响其他消费者）
- ❌ 不引入新依赖（`dayjs` 已在 [`package.json:29`](frontend/package.json#L29)，timezone/utc 是其官方插件无需新增 dep）

---

## 8. 责任分工

| 角色 | 职责 |
|---|---|
| 用户（Owner） | 评审本 spec、批准实施 |
| agent（本会话执行） | 按本 spec 改前端文件、更新测试断言、跑构建/测试验证 |

---

## 9. 相关记忆

- [[minimal-fix-preference]] — 用户偏好只针对问题根因做最小修复
- [[short-session-no-auto-commit]] — 短期任务收尾时不主动 commit
- [schema-migration-alignment-script](schema-migration-alignment-script.md) — 本次不动 schema 是关键决策依据
- [product-center-sku-purchase-price](product-center-sku-purchase-price.md) — 妙手导入脚本/数据契约背景
- [ai-migration-directory-mistake](ai-migration-directory-mistake.md) — 即使未来要写迁移也要落到 `current_migrations/versions/`
