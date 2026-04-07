# 开发规则更新（v4.3.7）

本页汇总今日重要架构与规范更新，确保后续协作一致且无“误导”。

## 1. 单一真源（SSOT）与模型合并
- 统一 ORM Base 与模型定义：所有表仅在 `modules/core/db/schema.py` 定义。
- 已合并：`field_mapping_dictionary/templates/template_items/audit` 四张表。
- 禁止：在其他文件重复定义 `Base = declarative_base()` 或重复模型。
- 统一导出：`from modules.core.db import FieldMappingDictionary, FieldMappingTemplate, ...`。

## 2. 字段映射辞典（DB+缓存）
- 辞典服务：`backend/services/field_mapping_dictionary_service.py`。
- 加载策略：优先返回指定 `data_domain`；为空时合并 `general`；仍为空时兜底返回全量活跃字段；traffic 还会自动补齐常用指标（UV/PV/CTR/加购/转化率/订单数）。
- 初始化脚本：
  - `scripts/init_field_mapping_dictionary.py`（orders/products/traffic 基础）
  - `scripts/seed_services_dictionary.py`（services 基础）
  - `scripts/seed_traffic_dictionary.py`（traffic 常用指标补全）

## 3. 前端字段映射 UI（增强）
- 组件：`frontend/src/views/FieldMappingEnhanced.vue`。
- 移除 JSX 依赖，全部采用原生 `<el-table>` 模板，避免 Vite JSX 解析问题。
- 交互：支持“表头行”调整与“重新预览”；生成智能映射前自动加载辞典；默认展开“必填字段/其他字段（未映射）”；大表横向滚动不影响页面比例。

## 4. Windows 终端规范（重要）
- 代码/测试日志禁用 Emoji；仅文档可用 Emoji。
- 发生 `UnicodeEncodeError` 时，统一改用 ASCII 文本；或使用安全打印封装（`errors='ignore'`）。

## 5. PostgreSQL 优先与性能
- 业务查询与扫描严格走 PostgreSQL；禁止递归扫描文件系统代替索引查询。
- `catalog_files` 是唯一文件索引表；平台/域/粒度/日期均从该表获取。

## 6. 根目录整洁与文档规范
- 根目录保留：`run.py`、`run_new.py`、`README.md`、`CHANGELOG.md`、环境样例、依赖清单、配置/脚本等核心文件（强制）。
- 已迁移：`请从这里开始_*.txt` → `docs/archive/20251029/`（归档）。
- 其他文档统一放在 `docs/` 目录；如需在根目录新增文档，需经审批（默认不允许）。

## 7. Agent 使用提示（避免误导）
- 查找模型：始终看 `modules/core/db/schema.py`。
- 数据库会话：`from backend.models.database import get_db`。
- 日志：`from modules.core.logger import get_logger`。
- 配置：后端用 `backend/utils/config.py` 的 `get_settings()`。
- 新增字段或表：务必在 `schema.py`，并编写增量脚本（`scripts/seed_*` / `migrations`）。

---

> 本文档随版本迭代更新；如遇到与历史文档不一致，以本页为准。


