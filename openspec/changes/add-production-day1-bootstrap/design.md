## Context

生产环境目前采用 Docker Compose 部署，发布流程以 tag（`vX.Y.Z`）作为入口，通过 GitHub Actions 进行 build/push/deploy。

历史问题表明：

- `.env` 容易因 CRLF、尾随空格导致 secrets 读取不一致
- 数据库字段变更若仅依赖 `create_all()`，无法保证已存在表的 schema 与当前版本一致
- 首次上线缺少标准化 bootstrap，导致“部署完成但不可用”的人工步骤与不可追溯变更

## Goals / Non-Goals

### Goals

- 建立生产发布的最小可用闭环（Day-1 Bootstrap）
- 以幂等方式执行迁移与初始化，支持重复运行
- Secrets 输出零泄露（CI 与容器日志）
- 对故障提供高可诊断信息（不含敏感信息）

### Non-Goals

- 不引入 Kubernetes/Helm
- 不在此变更中实现蓝绿/金丝雀发布（可作为后续 change）
- 不在此变更中替换全部配置体系，只做标准化与安全约束

## Decisions

### Decision: 在部署阶段使用一次性 backend 容器执行 bootstrap

**方案**：使用 `docker-compose ... run --rm --no-deps backend <cmd>` 执行：

1. `alembic upgrade head`
2. `python3 /app/scripts/bootstrap_production.py`（幂等）

**原因**：

- 与实际运行环境一致（同一镜像、同一依赖）
- 不要求在宿主机安装 Python/依赖
- 可控且易回滚（失败不会影响后续容器启动）

**架构规范要求**：

- Bootstrap 脚本必须遵循异步架构规范（v4.19.0）：

  - 使用 `AsyncSession` 和 `get_async_db()`（禁止使用 `get_db()`）
  - 所有数据库操作使用 `await db.execute(select(...))`（禁止使用 `db.query()`）
  - 所有服务类只接受 `AsyncSession`，不再支持 `Union[Session, AsyncSession]`
  - **脚本入口规范**：必须使用 `asyncio.run(main())` 启动异步事件循环，并使用 `AsyncSessionLocal()` 作为上下文管理器

    ```python
    import asyncio
    from backend.models.database import AsyncSessionLocal
    from sqlalchemy.ext.asyncio import AsyncSession

    async def main():
        async with AsyncSessionLocal() as db:
            try:
                # Bootstrap 逻辑
                # 1. 验证环境变量（CRLF检查）
                # 2. 创建基础角色（如果不存在）
                # 3. 创建管理员（如果启用且不存在）
                # ...

                await db.commit()  # 提交事务
            except Exception as e:
                await db.rollback()  # 回滚事务
                raise  # 重新抛出异常，让脚本失败

    if __name__ == "__main__":
        asyncio.run(main())
    ```

    **注意**：

    - `get_async_db()` 是 FastAPI 依赖注入函数，**不能在独立脚本中使用**
    - 独立脚本必须使用 `AsyncSessionLocal()` 作为上下文管理器
    - 必须手动管理事务（`commit()` 和 `rollback()`）
    - 异常时必须回滚并重新抛出，确保脚本失败时部署被阻断

- 日志输出规范（Windows 兼容性）：
  - 禁止使用 emoji 字符（会导致 `UnicodeEncodeError`）
  - 使用 ASCII 符号：`[OK]`, `[FAIL]`, `[WARN]`, `[INFO]`
  - 必须通过 `scripts/verify_no_emoji.py` 验证

**在部署流程中的集成点**：

Bootstrap 插入到 `deploy-production.yml` 的以下位置：

1. **阶段 1**：基础设施健康（PostgreSQL、Redis）✅ 已存在
2. **阶段 2**：数据库迁移（`alembic upgrade head`）✅ 已存在
3. **阶段 2.5**：Bootstrap 初始化 ⭐ 新增（在迁移后、应用层启动前）
4. **阶段 3**：Metabase 启动 ✅ 已存在
5. **阶段 4**：应用层启动（Backend、Celery）✅ 已存在

**执行命令示例**：

```bash
# 步骤1：清洗 .env 文件（去除 CRLF 和尾随空格）
sed -e 's/\r$//' -e 's/[ \t]*$//' .env > .env.cleaned

# 步骤2：使用清洗后的 .env 文件执行 bootstrap
docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml -f docker-compose.deploy.yml \
  --env-file .env.cleaned \
  --profile production run --rm --no-deps backend \
  python3 /app/scripts/bootstrap_production.py
```

**注意事项**：

- 必须在**部署开始阶段**（阶段 1 之前）清洗 `.env` 文件
- 所有后续 `docker-compose` 命令统一使用 `--env-file .env.cleaned`
- `.env.cleaned` 文件在部署完成后**必须删除**（避免敏感信息残留）
  - 删除时机：部署成功后的清理步骤
  - 如果部署失败，保留 `.env.cleaned` 用于诊断（但在下次部署前必须手动清理）

### Decision: Secrets 的处理原则

- CI/CD 与脚本输出中严禁出现 secrets 明文
- `.env` 读取必须做 CRLF/尾随空格清理
- 生产环境禁止使用默认占位 secrets（如默认 JWT/SECRET_KEY 等），发现即 fail fast
- 对 secrets 的来源与覆盖顺序做标准化并可诊断（仅显示来源名/是否设置，不显示值）
- 对敏感项仅允许输出：
  - 是否设置（true/false）
  - 长度（可选）
  - 掩码（如前后各 2 位，中间用 `***`）

**Secrets 来源优先级（两层架构）**：

- **部署态 secrets**（仅在 CI/CD 使用）：

  - GitHub Secrets：`PRODUCTION_SSH_PRIVATE_KEY`、`GITHUB_TOKEN` 等（用于 SSH 连接、镜像拉取）
  - 不传递到容器运行环境（安全隔离）

- **运行态 secrets**（容器内使用）：
  - 优先级 1：服务器端 secrets 文件（如 `.secrets`，权限 600）
  - 优先级 2：服务器 `.env` 文件（标准化后使用，见下方 CRLF 清理）
  - **禁止**：默认占位符（如 `your-secret-key-change-this`）

**CRLF/尾随空格清理的强制要求**：

由于 `docker-compose` 在读取 `.env` 时可能直接传递包含 `\r` 的值到容器环境变量，导致连接失败（历史问题根源），必须：

1. **部署前清洗 `.env` 文件**：

   ```bash
   # 生成清洗后的 .env 文件（去除 CRLF 和尾随空格）
   sed -e 's/\r$//' -e 's/[ \t]*$//' .env > .env.cleaned
   ```

2. **统一使用 `--env-file`**：

   - 所有 `docker-compose` 命令必须使用 `--env-file .env.cleaned`
   - 禁止直接依赖 Docker Compose 的自动 `.env` 读取（无法保证清理）

3. **验证步骤**：
   - Bootstrap 脚本启动时验证关键环境变量不包含 `\r` 字符
   - 发现 `\r` 时 fail fast 并输出诊断信息（不泄露值）

**日志输出规范**：

- 所有日志输出必须遵循无 emoji 规范（Windows 兼容性）
- 使用 ASCII 符号替代：`[OK]`, `[FAIL]`, `[WARN]`, `[INFO]`, `[WAIT]`
- Secrets 诊断信息示例：
  - [OK] 正确：`[INFO] SECRET_KEY is set (length: 32, masked: se***ey)`
  - [FAIL] 错误：`[INFO] SECRET_KEY: your-secret-key-here`（泄露明文）
  - [FAIL] 错误：`[OK] SECRET_KEY 已设置`（虽然使用 ASCII 符号，但中文可能导致编码问题）

### Decision: Admin bootstrap 的安全边界

- 默认不创建/不修改管理员账号（safe-by-default）
- 仅在显式启用且数据库中不存在任何 superuser 时允许创建
- 管理员密码必须来自 secret（不可使用默认值），且不得输出到日志
- bootstrap 必须记录审计信息（不含敏感信息）

**管理员/超级用户判定标准（严格双重检查）**：

系统使用两套机制标识管理员：

1. `is_superuser` 标志（`DimUser.is_superuser = True`）
2. 角色绑定（`DimRole.role_code == "admin"` 或 `DimRole.role_name == "admin"`）

**Bootstrap 判定逻辑**（必须同时满足）：

- 如果数据库中**存在任何用户满足以下任一条件**，则视为“已存在管理员”，**禁止创建**：
  - `is_superuser = True`，**或**
  - 绑定了 `role_code == "admin"` 的角色，**或**
  - 绑定了 `role_name == "admin"` 的角色

**管理员创建的环境变量定义**：

- `BOOTSTRAP_CREATE_ADMIN`: 是否启用管理员创建（默认：`false`，必须显式设置为 `true`）
- `BOOTSTRAP_ADMIN_USERNAME`: 管理员用户名（默认：`admin`，可通过环境变量覆盖）
- `BOOTSTRAP_ADMIN_PASSWORD`: 管理员密码（**必须设置**，禁止使用默认值，必须来自 secret）
- `BOOTSTRAP_ADMIN_EMAIL`: 管理员邮箱（可选，默认：`admin@xihong.com`）

**注意**：所有环境变量值必须来自服务器 `.env` 文件或 secrets 文件，不能硬编码在脚本中。

**查询示例**（异步架构）：

```python
# 检查是否存在任何管理员（幂等查询）
from sqlalchemy import select, or_
from modules.core.db import DimUser, DimRole

# 方法1：检查 is_superuser
superuser_check = select(DimUser).where(DimUser.is_superuser == True)

# 方法2：检查角色绑定
admin_role_check = select(DimUser).join(DimUser.roles).where(
    or_(
        DimRole.role_code == "admin",
        DimRole.role_name == "admin"
    )
)

# 如果任一查询返回结果，则跳过创建
```

**幂等性与并发安全**：

- 使用数据库唯一约束（如用户名唯一索引、角色代码唯一索引）防止重复创建
- 使用 `ON CONFLICT DO NOTHING` 或等价逻辑处理并发插入
- 所有数据库操作必须包裹在事务中
- 基础数据（角色、权限）的插入使用 upsert 模式（查询存在性 + 插入或跳过）

**基础角色定义（必须创建）**：

根据系统权限矩阵，以下角色必须在 Bootstrap 中创建（如果不存在）：

| role_code  | role_name | description                                                            | is_system |
| ---------- | --------- | ---------------------------------------------------------------------- | --------- |
| `admin`    | `管理员`  | 系统管理员，拥有所有系统权限，包括用户审批、系统配置、数据管理等       | `true`    |
| `manager`  | `主管`    | 部门主管，拥有业务管理、审批和配置权限，可管理账号、目标、采购、报表等 | `false`   |
| `operator` | `操作员`  | 日常操作人员，拥有基础业务操作权限，可进行数据同步、订单处理等日常操作 | `false`   |
| `finance`  | `财务`    | 财务人员，拥有财务和销售数据查看权限，可进行财务管理和报表查看         | `false`   |

**角色创建逻辑**：

- 使用 `role_code` 作为唯一标识（数据库唯一约束）
- 如果角色已存在，跳过创建（幂等）
- 如果角色不存在，创建并设置 `is_system` 标志（`admin` 角色为 `true`，其他为 `false`）

**Bootstrap 部分失败的处理策略**：

- **原子性保证**：所有数据库操作在单个事务中执行，要么全部成功，要么全部回滚
  - 使用 `async with AsyncSessionLocal() as db:` 确保会话生命周期管理
  - 成功时调用 `await db.commit()` 提交事务
  - 异常时调用 `await db.rollback()` 回滚事务并重新抛出异常
- **重试机制**：如果 Bootstrap 失败（非致命错误），可以直接重试（依赖幂等性）
- **回滚策略**：如果部分步骤成功但后续步骤失败，事务自动回滚，无需手动清理
- **致命错误**：如果关键步骤失败（如数据库连接失败、权限不足、环境变量验证失败），fail fast 并输出诊断信息（不含 secrets）
- **非致命错误**：如果非关键步骤失败（如某个角色创建失败但已存在），记录警告但继续执行
- **脚本退出码**：成功返回 0，失败返回非 0（确保部署流程能够检测失败）

## Migration Plan

- 在不改变现有手动运维方式的前提下，先将 bootstrap 作为“发布流程的一部分”引入
- 保持 bootstrap 幂等：已存在则跳过/校验，不重复写入
- 对管理员创建提供开关与显式确认（避免误创建或覆盖）
- 迁移失败时阻断发布，并提供恢复/回滚/重试的标准操作指引（文档化）

## Risks / Trade-offs

- **风险**：bootstrap 增加发布时长
  - **缓解**：仅做 P0 级必需操作，避免重计算/大扫描
- **风险**：错误的 secrets 导致发布失败
  - **缓解**：失败前输出明确诊断（不含 secrets），并提供回滚/重试说明

## Open Questions

- 管理员创建默认策略：是否默认关闭，且仅在“无任何 superuser”时创建？（提案建议：是）
- 生产 secrets 推荐落地方式：纯 `.env`、还是 `.env + permissions`、或单独 secrets 文件（如 `.secrets`）？
