## 1. Implementation

- [ ] 1.1 定义生产 Bootstrap 流程与幂等策略（可重复执行，无副作用）
- [ ] 1.2 新增/整理生产 Bootstrap 脚本入口（建议：`/app/scripts/bootstrap_production.py`）
  - [ ] 必须使用异步架构（AsyncSession、await db.execute，禁止 db.query）
  - [ ] 脚本入口必须使用 `asyncio.run(main())` 启动异步事件循环
  - [ ] 必须使用 `AsyncSessionLocal()` 作为上下文管理器（禁止使用 `get_async_db()`，那是 FastAPI 依赖注入函数）
  - [ ] 必须手动管理事务（`async with` 块内调用 `await db.commit()` 和 `await db.rollback()`）
  - [ ] 注意：`async with AsyncSessionLocal() as db:` 会自动关闭会话，但不会自动提交或回滚事务
  - [ ] 异常时必须回滚并重新抛出，确保脚本失败时部署被阻断
  - [ ] 脚本退出码：成功时 `sys.exit(0)`，失败时 `sys.exit(1)`（确保部署流程检测失败）
  - [ ] 必须遵循无 emoji 日志规范（使用 ASCII 符号：[OK], [FAIL], [WARN]）
  - [ ] 必须通过 `scripts/verify_no_emoji.py` 验证
  - [ ] 确认脚本在容器内路径为 `/app/scripts/bootstrap_production.py`
- [ ] 1.3 规范 secrets 来源与加载顺序（GitHub Secrets/服务器端/`.env`），并实现 CRLF/空格清理与"来源可诊断但不泄露"
  - [ ] 明确区分部署态 secrets（GitHub Secrets，仅 CI 使用）和运行态 secrets（服务器 `.env`/`.secrets`）
  - [ ] 在部署流程开始前清洗 `.env` 文件（去除 CRLF 和尾随空格）：`sed -e 's/\r$//' -e 's/[ \t]*$//' "${PRODUCTION_PATH}/.env" > "${PRODUCTION_PATH}/.env.cleaned"`（使用完整路径）
  - [ ] 所有 `docker-compose` 命令统一使用 `--env-file "${PRODUCTION_PATH}/.env.cleaned"`（禁止依赖自动 `.env` 读取，使用完整路径）
  - [ ] Bootstrap 脚本启动时验证关键环境变量不包含 `\r` 字符（fail fast）
- [ ] 1.4 在 `deploy-production.yml` 增加 bootstrap 阶段（基础设施健康后、应用层启动前），失败阻断
  - [ ] 位置：阶段 0.5（在阶段 1 之前清洗 `.env` 文件）和阶段 2.5（迁移后、应用层启动前执行 bootstrap）
  - [ ] 阶段 0.5：清洗 `.env` 文件：`sed -e 's/\r$//' -e 's/[ \t]*$//' "${PRODUCTION_PATH}/.env" > "${PRODUCTION_PATH}/.env.cleaned"`（使用完整路径）
  - [ ] 阶段 2.5：使用 `docker-compose ... --env-file "${PRODUCTION_PATH}/.env.cleaned" ... run --rm --no-deps backend python3 /app/scripts/bootstrap_production.py`
  - [ ] 在 bootstrap 命令后检查退出码（`$?`），失败时阻断部署：`if [ $? -ne 0 ]; then echo "[FAIL] Bootstrap 失败"; exit 1; fi`
  - [ ] 所有后续 `docker-compose` 命令统一使用 `--env-file "${PRODUCTION_PATH}/.env.cleaned"`（使用完整路径）
  - [ ] 失败时阻断部署并输出诊断信息（不含 secrets，使用 ASCII 符号）
  - [ ] 确保使用 `bash -c '...'` 执行远程命令（禁止 heredoc，符合 v4.20.0 规范）
  - [ ] 部署成功后删除 `.env.cleaned` 文件：`rm -f "${PRODUCTION_PATH}/.env.cleaned"`（避免敏感信息残留）
  - [ ] 部署失败时保留 `.env.cleaned` 用于诊断，但下次部署前必须手动清理
- [ ] 1.5 完善管理员创建流程（默认关闭；仅在无 superuser 时允许；密码必须来自 secret；不得输出明文）
  - [ ] 定义环境变量：`BOOTSTRAP_CREATE_ADMIN`（默认 false）、`BOOTSTRAP_ADMIN_USERNAME`（默认 admin）、`BOOTSTRAP_ADMIN_PASSWORD`（必须）、`BOOTSTRAP_ADMIN_EMAIL`（可选）
  - [ ] 实现严格的双重检查：同时查询 `is_superuser = True` **或** `role_code/role_name == "admin"` 的用户
  - [ ] 如果存在任一条件满足的用户，则视为"已存在管理员"，禁止创建
  - [ ] 使用数据库唯一约束（用户名）防止并发重复创建
  - [ ] 所有数据库操作包裹在事务中，使用 `ON CONFLICT DO NOTHING` 或等价逻辑
- [ ] 1.6 为 bootstrap 增加最小验证：校验关键表存在、关键角色存在、管理员记录存在（避免真实登录带来的副作用）
  - [ ] 验证关键表存在（DimUser, DimRole 等）
  - [ ] 验证基础角色存在（role_code: admin, manager, operator, finance）
  - [ ] 验证管理员记录存在（使用双重检查：is_superuser 或 role_code == "admin"）
  - [ ] 所有验证使用异步查询（await db.execute(select(...))）
  - [ ] 实现基础角色创建逻辑：如果角色不存在则创建，已存在则跳过（幂等）
- [ ] 1.7 更新文档：新增 Day-1 Bootstrap 使用说明与故障排查
- [ ] 1.8 定义迁移失败恢复/回滚/重试流程（文档 + deploy 输出指引）
- [ ] 1.9 建立生产镜像内置脚本白名单（仅复制必要 ops 脚本，禁止全量 scripts/）
  - [ ] 在 `Dockerfile.backend` 中明确复制 `scripts/bootstrap_production.py`
  - [ ] 确认脚本在容器内路径为 `/app/scripts/bootstrap_production.py`
  - [ ] 验证脚本权限和执行权限（chmod +x 或通过 python3 执行）

## 2. Safety / Security

- [ ] 2.1 确认所有 CI/CD 输出不包含 secrets 明文（包括 Redis/DB/JWT 等）
- [ ] 2.2 为服务器端 secrets 文件设置权限与推荐路径（如 `600`）
- [ ] 2.3 为 bootstrap 脚本提供审计日志（不含敏感信息）
  - [ ] 使用 ASCII 符号，禁止 emoji（通过 `scripts/verify_no_emoji.py` 验证）
  - [ ] 仅输出掩码或存在性，不输出 secrets 明文
  - [ ] 记录 bootstrap 执行时间、步骤、结果（不含敏感信息）
  - [ ] 日志格式示例：`[INFO] Bootstrap step: create_admin_user, status: skipped, reason: superuser_exists`
- [ ] 2.4 生产环境禁止默认占位 secrets：缺失或默认值直接 fail fast（在 deploy/boot 阶段）

## 3. Tests / Validation

- [ ] 3.1 本地 Docker Compose 模拟“全新空库”启动：验证迁移 + bootstrap 后可登录
- [ ] 3.2 生产回归：在已有库上发布新 tag，验证迁移幂等与 bootstrap 幂等
- [ ] 3.3 失败场景：故意提供错误 Redis/DB 密码，验证 deploy 会失败并给出可诊断输出（不泄露 secrets）
- [ ] 3.4 管理员创建保护：库中已有 superuser 时启用 admin 创建开关，验证 bootstrap 仍然跳过且给出非敏感提示
  - [ ] 测试场景1：存在 `is_superuser = True` 的用户，验证创建被跳过
  - [ ] 测试场景2：存在 `role_code == "admin"` 的用户但 `is_superuser = False`，验证创建被跳过
  - [ ] 测试场景3：无任何管理员时，验证可以创建（需显式启用）
- [ ] 3.5 异步架构验证：确认 bootstrap 脚本使用 AsyncSession 和 await db.execute（不使用 db.query）
- [ ] 3.6 日志规范验证：运行 `scripts/verify_no_emoji.py` 确认 bootstrap 脚本无 emoji 字符
- [ ] 3.7 Windows 兼容性验证：在 Windows 环境下运行 bootstrap 脚本，确认无 UnicodeEncodeError
- [ ] 3.8 CRLF 清理验证：使用包含 CRLF 的 `.env` 文件，验证清洗后的 `.env.cleaned` 不包含 `\r`，且容器内环境变量正确
- [ ] 3.9 幂等性并发验证：模拟并发执行 bootstrap 脚本（同时运行两次），验证基础数据和角色不重复创建（使用唯一约束保护）
- [ ] 3.10 事务原子性验证：模拟部分失败场景（如角色创建成功但管理员创建失败），验证事务回滚正确，无残留数据
- [ ] 3.11 环境变量验证：测试 `BOOTSTRAP_CREATE_ADMIN`、`BOOTSTRAP_ADMIN_USERNAME`、`BOOTSTRAP_ADMIN_PASSWORD` 等环境变量的正确读取和使用

