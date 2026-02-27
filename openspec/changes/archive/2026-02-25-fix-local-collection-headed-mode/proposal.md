# Change: 本地采集有头模式可预期（run.py --local + 有头开关文案）

## Why

1. **run.py --local 未强制 ENVIRONMENT**：使用 `python run.py --local` 时仅加载 `.env`，未显式设置 `ENVIRONMENT=development`。若 `.env` 中为 `ENVIRONMENT=production`，后端会按生产配置（`browser_config` 默认 `headless=True`），采集时不会弹出浏览器窗口，与「本地观察采集过程」的预期不符。
2. **「调试模式」语义不清**：前端开关文案为「调试模式」，实际主要控制「是否强制有头浏览器」。用户易误解为仅影响日志，不知道不勾选会导致无头、看不到窗口；且与 Playwright 官方的「headed = headless=False」概念不一致。
3. **文档与失败提示不足**：有头模式需本机完整安装 Chromium（`playwright install`，非仅 `--only-shell`）；任务失败时若为浏览器启动失败，缺少「请执行 playwright install」或「请开启有头模式」的明确提示。

## What Changes

### 1. run.py --local 时强制 ENVIRONMENT=development

- 在 `run.py` 的 `--local` 分支中，在启动后端（及 Celery、前端）之前，将当前进程的 `os.environ['ENVIRONMENT']` 设为 `'development'`，使子进程继承该环境。
- 效果：使用 `run.py --local` 时，后端与 Celery 始终按开发环境配置；`browser_config` 在 development 下默认 `headless=PLAYWRIGHT_HEADLESS`（默认 false），即默认有头，无需用户必须勾选「有头」开关才能看到窗口。

### 2. 前端：开关文案改为「有头模式」并补充说明

- 将「调试模式」改为「有头模式」或「显示浏览器窗口」；`quickForm.debugMode` 与 API 的 `debug_mode` 保持不变（仅文案与提示调整）。
- Tooltip 明确说明：开启后会在**运行后端的电脑**上打开浏览器窗口，便于观察采集；若看不到窗口请确认已执行 `playwright install chromium` 且后端单进程。

### 3. 文档与采集说明

- 在「如何真正执行采集？」中补充：有头模式需本机执行 `playwright install`（或 `playwright install chromium`），勿仅安装 `--only-shell`；本地观察采集请开启「有头模式」。
- 可选：在 `docs/guides/` 或 CLAUDE.md 中增加一句「run.py --local 会强制 ENVIRONMENT=development，保证本地采集默认有头」。

## Impact

### 受影响的规格

- 无新增 spec 变更；可选在 data-collection 或 project 文档中注明「本地有头」行为。

### 受影响的代码与文档

| 类型 | 位置 | 修改内容 |
|------|------|----------|
| 启动脚本 | run.py | --local 分支内设置 os.environ['ENVIRONMENT']='development' |
| 前端 | frontend/src/views/collection/CollectionTasks.vue | 开关 active-text、tooltip 与「如何真正执行采集」说明文案 |
| 文档 | 同上（采集说明）或 docs/guides | playwright install 与有头模式提示 |

### 不修改

- 不修改 backend/utils/config.py 的 browser_config 逻辑。
- 不修改 browser_config_helper 的 debug_mode 覆盖逻辑（仍保留：勾选则强制 headless=False）。
- API 请求体仍为 debug_mode，无需改接口。

## Non-Goals

- 不实现浏览器启动失败时的自动检测与专用错误码。
- 不修改 Docker 或生产环境下的 ENVIRONMENT 行为。
