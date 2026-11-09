# Engineering Status

## Current State

- Repository workflow is `skill-first`
- Active flow is `superpowers` + `planning-with-files`
- `openspec/` is historical archive only
- Normal maintenance goal is to keep `main`, `origin/main`, and `cnb/main` aligned after synchronization work is complete
- Short-lived drift can still happen during active work or when only release tags are pushed

## Active Source Of Truth

- Rule entrypoint:
  - [`AGENTS.md`](F:/Vscode/python_programme/AI_code/xihong_erp/AGENTS.md)
- Tool adapter:
  - [`CLAUDE.md`](F:/Vscode/python_programme/AI_code/xihong_erp/CLAUDE.md)
- Detailed reference:
  - [`docs/DEVELOPMENT_RULES/README.md`](F:/Vscode/python_programme/AI_code/xihong_erp/docs/DEVELOPMENT_RULES/README.md)

## CI Model

- Default GitHub `CI Pipeline` is change-scoped, not full-repository regression
- Python test job is aligned to `3.11`
- `black`, `ruff`, `bandit`, and secret scan only inspect changed Python files
- `pytest` only runs changed test files in default CI
- Integration-style validations that depend on full external environments should not be folded back into the default CI gate

Key files:
- [`ci.yml`](F:/Vscode/python_programme/AI_code/xihong_erp/.github/workflows/ci.yml)
- [`ci_changed_python_files.py`](F:/Vscode/python_programme/AI_code/xihong_erp/scripts/ci_changed_python_files.py)
- [`pyproject.toml`](F:/Vscode/python_programme/AI_code/xihong_erp/pyproject.toml)

## Release Model

- GitHub deployment remains tag-driven
- Production source of truth is release tags such as `vX.Y.Z`
- `origin/main` is not deployment truth by itself
- Release checklist lives in [`RELEASE_CHECKLIST.md`](F:/Vscode/python_programme/AI_code/xihong_erp/docs/guides/RELEASE_CHECKLIST.md)

## Deployment Status

- Production deploy flow is healthy
- SSH host key pinning is enabled
- `StrictHostKeyChecking=no` is no longer part of the active deploy flow
- Production compose is expected to read `${DATABASE_URL}` instead of hardcoded database credentials

## Current Non-Blocking Warnings

- Docker build workflows may still show Node 20 deprecation warnings from upstream Docker-maintained GitHub Actions
- Those warnings are currently upstream-action warnings, not repository logic failures
- **`main` 分支的 `Validate Data Flow` 工作流会因 `api.delete` 误报而变红** — **已修复 (2026-11-09)**
  - 现象: `Validate Frontend API Methods` 报「缺失方法调用: delete (2 处)」
    —— 出自 `frontend/src/domains/business/views/finance/ExpenseManagement.vue`
    的 `api.delete(...)` 调用。
  - 根因: `scripts/validate_frontend_api_methods.py` 把 `delete` 放进了
    `_JS_KEYWORDS`, 于是**方法定义**侧看不见
    `frontend/src/api/index.js` 里真实存在的 `async delete(path, config) {}`
    ⇒ 方法侧查不到、调用侧查得到 ⇒ 误报成「缺失」。
  - 为什么**不阻塞发布**: 部署流水线(`deploy-production.yml`)的同一道门禁按
    **「自上个 tag 起的变更文件」**扫描, 该文件不在变更集里 ⇒ 门禁通过。
    只有 `main` 分支的全量扫描工作流会命中。
  - **实际修法**: 没有采用「把 `delete` 从 `_JS_KEYWORDS` 去掉」这个最省事的写法 ——
    现有契约用例 `backend/tests/test_validate_frontend_api_methods_contract.py`
    断言 `delete (true) {` 这种「关键字 + 括号 + 块」形态**不得**被当成方法,
    直接去掉 `delete` 会打破该断言(即削弱既有守护)。
    改为: `delete` 仍留在 `_JS_KEYWORDS` 里, 但**只有紧跟 `async` 时**才按方法定义处理
    (真实写法是 `async delete(path, config = {}) {}`), 其余情形按关键字语句跳过。
    ⇒ 既有断言一条未动, 另新增 4 条守护用例(真方法被识别 / 运算符用法不被识别 /
    真实 API 文件含 `delete` / 真实前端调用不再报缺失)。
  - 效果: 已定义方法数 274 → 275, 缺失方法调用 2 → 0, 校验器退出码 0。
  - 原触发条件(已消除): 下次发布若变更集里包含 `api.delete(...)` 的调用方,
    部署门禁也会误报 ⇒ 现已修复, 该风险不再存在。

## Practical Guidance

1. Do not revert default CI back to full-repository lint/test scanning
2. Keep release operations tag-driven
3. Keep repository-specific constraints in `AGENTS.md`, not ad hoc workflow comments
4. When a future session investigates CI failures, inspect the latest GitHub Actions run first before changing rules
