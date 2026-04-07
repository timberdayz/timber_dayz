# Tasks: 本地采集有头模式可预期

## 1. run.py --local 强制 ENVIRONMENT=development

- [x] 1.1 在 run.py 的 --local 分支中，在启动后端/Celery/前端之前（如 `processes = []` 之后、`start_backend()` 之前），当 `args.local` 为 True 时设置 `os.environ['ENVIRONMENT'] = 'development'`，使子进程继承，保证本地默认有头。

## 2. 前端：有头模式文案与说明

- [x] 2.1 将「调试模式」开关的 active-text 改为「有头模式」或「显示浏览器」；inactive-text 可保留为空或简短说明。
- [x] 2.2 更新该开关的 tooltip：明确写「开启后会在运行后端的电脑上打开浏览器窗口；若看不到窗口请确认已执行 playwright install chromium 且后端单进程」。
- [x] 2.3 在「如何真正执行采集？」说明中补充：有头模式需本机执行 `playwright install`（或 `playwright install chromium`），勿仅安装 `--only-shell`；本地观察采集请开启「有头模式」。

## 3. 文档（可选）

- [x] 3.1 在 CLAUDE.md 或 docs/guides 中增加一句：使用 `run.py --local` 时会强制 `ENVIRONMENT=development`，本地采集默认有头，无需必勾有头开关。
