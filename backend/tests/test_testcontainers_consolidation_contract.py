"""契约测试：集成测试必须共用同一个 postgres 容器，库必须每用例独立。

背景（2026-11-13 实测）
------------------------
``backend/tests/data_pipeline/`` 里有 **40** 处复制粘贴的样板，分布在 11 个文件里：

    with PostgresContainer("postgres:15") as pg:
        sync_url = pg.get_connection_url()
        ...
        await engine.dispose()

代价（实测）
------------
* 容器启动 **1.76 秒/个** ⇒ 一轮 data_pipeline 回归要付 **~70 秒**纯启动开销；
* 每个容器自带一个匿名卷 ⇒ 进程被强杀就留下残卷（本机 4 天攒了 11 个）。

目标形态
--------
**一个会话级容器 + 每个用例一个独立 database**：

* 容器：复用会话护栏在 import 期起好的那一个 ⇒ 整个后端测试会话**不再多起容器**；
* 库：每个用例 ``CREATE DATABASE``（实测 **0.063 秒**）→ 用完 ``DROP DATABASE``
  （实测 **0.076 秒**）⇒ 40 个用例总共多花 ~6 秒，而不是 ~70 秒。

为什么不能简单地"共用一个数据库"
----------------------------------
共享 **database** 会直接让测试红：这些用例里有 21 处是**裸** ``CREATE TABLE``
（没有 ``IF NOT EXISTS``），其中 3 张表跨文件重名：

* ``core.shop_accounts``            —— 3 个文件都建
* ``core.shop_account_aliases``     —— 2 个文件都建
* ``semantic.fact_orders_atomic``   —— 2 个文件都建

第二个文件建同名表就会报 ``relation already exists``。

为什么"每用例独立库"与原来"每用例独立容器"等价
----------------------------------------------
原实现每个用例起的是**全新容器**（库里只有 ``public`` schema）⇒ 新建 database
与之等价。且 ``refresh_runner._OPS_TABLES_READY_SIGNATURE`` 是按 ``db_url`` 签名的
⇒ 每个用例的库地址不同 ⇒ 不会被上一个用例的"已就绪"标记跳过建表。

这些约定写进纸上，免得收敛成果被悄悄改回去。
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_PIPELINE = PROJECT_ROOT / "backend" / "tests" / "data_pipeline"
BACKEND_TESTS = PROJECT_ROOT / "backend" / "tests"
CONFTEST = BACKEND_TESTS / "conftest.py"
CI_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"

#: 唯一允许创建 postgres 容器的位置。
ALLOWED_CONTAINER_SITES = (CONFTEST,)

#: 共享容器 fixture 的名字（会话级）。
SHARED_CONTAINER_FIXTURE = "pg_shared_container"

#: 每用例独立库 fixture 的名字（函数级）。
PER_TEST_DATABASE_FIXTURE = "pg_database"

#: 本文件自己就是守护 ⇒ 它必须能包含被禁的写法而不自我误伤。
SELF = Path(__file__).resolve()


def _tracked_python_files() -> List[Path]:
    out = subprocess.run(
        ["git", "ls-files", "backend/tests", "tests"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(PROJECT_ROOT),
    )
    files = []
    for line in out.stdout.splitlines():
        if not line.strip().endswith(".py"):
            continue
        path = (PROJECT_ROOT / line.strip()).resolve()
        if path == SELF:
            # 守护文件本身必然写着被禁的样板（那是它要举证的证据）
            continue
        files.append(path)
    return files


def _container_sites() -> List[tuple]:
    """每一个创建 postgres 容器的位置。"""
    sites = []
    for path in _tracked_python_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r"PostgresContainer\(", text):
            line_no = text[: match.start()].count("\n") + 1
            sites.append((path, line_no))
    return sites


def _fixture_scope(text: str, name: str) -> Optional[str]:
    """取 fixture 的 scope；找不到装饰器或没写 scope 时返回 ``None``。"""
    pattern = (
        r"@pytest(?:_asyncio)?\.fixture\s*(?:\(([^)]*)\))?\s*\n"
        r"(?:@[^\n]*\n)*\s*(?:async\s+)?def\s+" + re.escape(name) + r"\b"
    )
    match = re.search(pattern, text)
    if not match:
        return None
    decorator = match.group(1) or ""
    scope = re.search(r"scope\s*=\s*[\"']([^\"']+)[\"']", decorator)
    return scope.group(1) if scope else "function"


def test_no_test_module_starts_its_own_postgres_container():
    """**核心守护**：测试模块里不许再自己起 postgres 容器。

    只允许 ``backend/tests/conftest.py`` 起 —— 那是唯一的、单例的来源。
    """
    offenders = [
        (path.relative_to(PROJECT_ROOT).as_posix(), line_no)
        for path, line_no in _container_sites()
        if path not in ALLOWED_CONTAINER_SITES
    ]
    assert not offenders, (
        "这些测试模块各自起了 postgres 容器（每个 1.76 秒、每个留一个匿名卷）: "
        "{0}\n"
        "⇒ 一律改用 backend/tests/conftest.py 的共享容器 + 每用例独立库。".format(
            offenders
        )
    )


def test_conftest_provides_shared_container_and_per_test_database():
    """conftest 必须同时提供「共享容器」与「每用例独立库」两个 fixture。"""
    text = CONFTEST.read_text(encoding="utf-8", errors="replace")
    for name in (SHARED_CONTAINER_FIXTURE, PER_TEST_DATABASE_FIXTURE):
        assert re.search(
            r"def\s+" + name + r"\b", text
        ), "conftest 必须提供 {0} fixture".format(name)


def test_shared_container_fixture_is_session_scoped():
    """共享**容器** fixture 必须是 **session 级** —— 否则还是每用例起一个。

    ⚠️ 装饰器可能写成 ``@pytest_asyncio.fixture(scope="session")``,
    也可能写成无参 ``@pytest_asyncio.fixture``（函数级）——
    两种写法都要能识别，否则守护会漏判。
    """
    text = CONFTEST.read_text(encoding="utf-8", errors="replace")
    scope = _fixture_scope(text, SHARED_CONTAINER_FIXTURE)
    assert scope is not None, "找不到 {0} 的 fixture 装饰器".format(
        SHARED_CONTAINER_FIXTURE
    )
    assert (
        scope == "session"
    ), "{0} 必须是 session 级(scope='session'), 现在是 {1!r} —— " "否则每个用例仍会起一个容器".format(
        SHARED_CONTAINER_FIXTURE, scope
    )


def test_per_test_database_fixture_is_function_scoped():
    """每用例独立**库** fixture 必须是**函数级** —— 这是隔离语义的底线。

    这条与上一条是一对：容器共享（session 级），但**库必须每用例独立**（函数级）。

    为什么不能改成 session 级：这些用例里有 21 处裸 ``CREATE TABLE``
    （没有 ``IF NOT EXISTS``），其中 3 张表跨文件重名 ⇒ 共用一个库会让第二个
    文件报 ``relation already exists``；更要命的是用例之间会互相看见对方
    写进去的行 ⇒ 断言结果不可复现。
    """
    text = CONFTEST.read_text(encoding="utf-8", errors="replace")
    scope = _fixture_scope(text, PER_TEST_DATABASE_FIXTURE)
    assert scope is not None, "找不到 {0} 的 fixture 装饰器".format(
        PER_TEST_DATABASE_FIXTURE
    )
    assert scope == "function", (
        "{0} 必须是函数级(scope 不写或写 'function'), 现在是 {1!r} —— "
        "库共享会让用例之间串数据，也会撞上跨文件重名的表".format(
            PER_TEST_DATABASE_FIXTURE, scope
        )
    )


def test_data_pipeline_never_builds_its_own_container():
    """data_pipeline 里不许再出现"自己拉容器"的迹象。

    两条:

    1. 不许再 import/调用 ``testcontainers`` —— 起容器的唯一入口;
    2. 每个 ``as pg`` 的上下文必须是 ``pg_database()`` —— 防止有人把容器
       换个变量名再塞回来。

    ⚠️ 这里**不查** ``get_connection_url()``：改写后用例正文仍然要靠它拿
    本用例的库地址（``pg`` 现在是共享 fixture 给的），查它等于误伤。
    也不查 ``create_async_engine`` —— 有 8 个 data_pipeline 模块连的是
    ``DATABASE_URL`` 指向的隔离库，本来就该自己建 engine；误判它们等于
    把守护变成噪音（噪音的守护没人看）。
    """
    offenders = []
    for path in sorted(DATA_PIPELINE.glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(text)

        # (1) 真的 import 了 testcontainers 才算违规 —— 文档字符串里提一句
        #     "隔离库是 testcontainers 起的" 是说明文字, 不是依赖。
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] == "testcontainers":
                        offenders.append(
                            "{0}:{1} import testcontainers".format(
                                path.name, node.lineno
                            )
                        )
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                if root == "testcontainers":
                    offenders.append(
                        "{0}:{1} from testcontainers import ...".format(
                            path.name, node.lineno
                        )
                    )

        # (2) 每个 ``as pg`` 的上下文必须是 ``pg_database()``
        for node in ast.walk(tree):
            if not isinstance(node, (ast.With, ast.AsyncWith)):
                continue
            for item in node.items:
                if not isinstance(item.optional_vars, ast.Name):
                    continue
                if item.optional_vars.id != "pg":
                    continue
                call = item.context_expr
                shared = (
                    isinstance(node, ast.AsyncWith)
                    and isinstance(call, ast.Call)
                    and getattr(call.func, "id", "") == PER_TEST_DATABASE_FIXTURE
                )
                if not shared:
                    offenders.append(
                        "{0}:{1} `as pg` 的上下文不是 {2}()".format(
                            path.name, node.lineno, PER_TEST_DATABASE_FIXTURE
                        )
                    )
    assert not offenders, "data_pipeline 里还在自己拉容器: {0}".format(offenders)


def test_data_pipeline_users_declare_the_shared_fixture():
    """用了 ``pg_database`` 的用例，必须把 ``pg_database`` 声明成参数。

    守护的是**注入链**：如果用例正文里调了 ``pg_database()``，而签名里没有
    这个参数 ⇒ 运行时直接 ``NameError``，而且只在跑到那个用例时才炸。
    """
    offenders = []
    for path in sorted(DATA_PIPELINE.glob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if PER_TEST_DATABASE_FIXTURE + "(" not in text:
            continue
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            if PER_TEST_DATABASE_FIXTURE + "(" not in ast.unparse(node):
                continue
            args = node.args
            declared = [a.arg for a in list(args.args) + list(args.kwonlyargs)]
            if PER_TEST_DATABASE_FIXTURE not in declared:
                offenders.append(
                    "{0}:{1}::{2}".format(path.name, node.lineno, node.name)
                )
    assert (
        not offenders
    ), "这些用例正文用了 {0}()，签名里却没有声明这个 fixture(会 NameError): " "{1}".format(
        PER_TEST_DATABASE_FIXTURE, offenders
    )


def test_guard_test_itself_is_collected_by_ci():
    """这份守护必须进 CI 清单 —— 否则它和被守护的约定一样只是摆设。"""
    assert CI_WORKFLOW.exists(), "CI workflow 不存在"
    relative = "backend/tests/test_testcontainers_consolidation_contract.py"
    assert relative in CI_WORKFLOW.read_text(
        encoding="utf-8", errors="replace"
    ), "{0} 不在 CI 根契约清单里 ⇒ 这份守护在 CI 上不会跑".format(relative)
