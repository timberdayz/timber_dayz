from __future__ import annotations

import os
from pathlib import Path


#: 测试期护栏标记(由 ``backend/tests/conftest.py`` 在 pytest 启动时设置)。
#:
#: 为什么需要它
#: ------------
#: ``backend/utils/config.py`` 的 ``DATABASE_URL`` 默认值是**真实业务库**
#: (``postgresql://erp_user:...@localhost:15432/xihong_erp``), 仓库根 ``.env``
#: 里也是同一个地址。而 ``backend/main.py`` 会在 import 时调用
#: ``load_project_env(project_root)`` 把 ``.env`` 灌进进程环境。
#:
#: 于是任何在**测试进程**里导入 ``backend.models.database`` 的代码,
#: 拿到的都是能直连真实库的 engine —— 靠"每次记得打桩"防不住。
#:
#: 真实事故(2026-10-28, 本地库实测): 回归测试跑了
#: ``scheduled_tasks.auto_ingest_pending_files``, 它用**真实库**的
#: ``SessionLocal`` 重检了 21 个真实文件, 把它们的持久化状态改回
#: ``template_update_required``, 还抹掉了一个文件刚回填的模板契约。
#:
#: 所以护栏分三层:
#: 1. ``config.py``  —— 测试期强制 ``DATABASE_URL`` 为隔离库(源头拦截)
#: 2. 本模块        —— 测试期不让 ``.env`` 覆盖已设好的环境变量
#: 3. ``conftest.py`` —— 护栏失效时让整个测试会话直接失败(最后兜底)
TEST_ENV_GUARD_VAR = "XIHONG_TEST_ENV_GUARD"

#: 护栏期间**强制生效**的隔离库地址变量。
#:
#: 用独立变量(而不是复用 ``DATABASE_URL``)是刻意的:
#: 护栏必须**无视**环境变量与 ``.env`` 里的 ``DATABASE_URL`` ——
#: 否则任何人(或任何脚本)改一下 ``DATABASE_URL`` 就能把测试指回真实库。
#: 所以 ``config.py`` 在护栏开启时只认这个变量。
TEST_DATABASE_URL_VAR = "XIHONG_TEST_DATABASE_URL"

#: 护栏开启时**不允许被 .env 覆盖**的环境变量。
#:
#: 只保护护栏自己写进去的那几个。其余变量必须保持 ``load_dotenv`` 的原有语义
#: (``.env`` 覆盖 ``.env.local``, 后者再覆盖既有环境变量) ——
#: 否则等于悄悄改了 ``load_project_env`` 的契约,
#: ``backend/tests/test_project_env.py`` 里直接校验覆盖顺序的用例就会失败。
GUARDED_ENV_KEYS = ("DATABASE_URL", TEST_DATABASE_URL_VAR)


def isolated_database_url() -> str:
    """测试期隔离库地址(由 ``backend/tests/conftest.py`` 写入)。

    隔离库是一个**一次性 PostgreSQL 容器**(testcontainers):
    - 真实业务库既不会被读也不会被写;
    - 必须是 PostgreSQL ⇒ 本项目的表分布在 PG 的 schema 命名空间里
      (``core`` / ``a_class`` / ...), SQLite 根本建不出来
      (仓库自带的 ``sqlite_session`` fixture 就是因此一直是坏的);
    - 端口随机 ⇒ 上一次会话异常退出不会把端口占住, 下一次照样能起。

    这里只是把 conftest 写好的地址读出来; 真正起容器的是 conftest。
    """
    return os.getenv(TEST_DATABASE_URL_VAR, "").strip()


def is_test_env_guarded() -> bool:
    """当前进程是否处于「测试环境护栏」模式。"""
    return os.getenv(TEST_ENV_GUARD_VAR, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def resolve_env_profile(profile: str | None = None) -> str:
    raw_value = profile if profile is not None else os.getenv("XIHONG_ENV_PROFILE", "")
    return raw_value.strip().lower()


def resolve_project_env_files(
    project_root: str | Path,
    *,
    profile: str | None = None,
) -> list[Path]:
    root = Path(project_root)
    files = [
        root / ".env",
        root / ".env.local",
    ]

    if resolve_env_profile(profile) == "collection":
        files.append(root / ".env.collection.local")

    return [path for path in files if path.exists()]


def load_project_env(
    project_root: str | Path,
    *,
    profile: str | None = None,
    override: bool = True,
) -> list[Path]:
    loaded_files: list[Path] = []
    try:
        from dotenv import load_dotenv
    except ImportError:
        return loaded_files

    # [*] 测试期不让 ``.env`` 覆盖护栏写好的隔离库地址。
    # 见 ``TEST_ENV_GUARD_VAR`` 的说明: 护栏必须活到 ``.env`` 加载之后,
    # 否则测试又会连上真实业务库。
    protected: dict[str, str] = {}
    if is_test_env_guarded():
        protected = {
            key: os.environ[key]
            for key in GUARDED_ENV_KEYS
            if key in os.environ
        }

    for env_file in resolve_project_env_files(project_root, profile=profile):
        try:
            load_dotenv(env_file, encoding="utf-8", override=override)
        except TypeError:
            load_dotenv(env_file, override=override)
        loaded_files.append(env_file)
        # 还原护栏保护的变量(其余变量保持 load_dotenv 的原有语义)
        for key, value in protected.items():
            os.environ[key] = value

    return loaded_files
