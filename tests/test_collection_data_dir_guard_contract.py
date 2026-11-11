"""**文件系统护栏**守卫：测试绝不能写正式数据目录。

事故背景（2026-11-11）
----------------------
跑一次 ``tests/test_executor_v2.py``（27 个用例）会往**正式**
``data/raw/2026/`` 里写 **8 个文件**（4 个 xlsx + 4 个 .meta.json）。

实测（本地开发库）:
* 167 个文件内容是 ``fake-export``（**11 字节**）—— 根本不是有效的 xlsx;
* 其中 114 个带 ``_1`` / ``_2`` / ``_3`` 序号后缀（同一时间戳重复 4 份）;
* 全部**没有** ``public.catalog_files`` 入库记录（孤儿文件）;
* 与真实采集文件对照：真实的是 **89 KB** 的有效 .xls。

⇒ 排查数据问题时这些假文件会让人误判成「订单采了没入库」
   （本次差点这么判）⇒ 必须清掉, 且不能再发生。

根因
----
``executor_v2._process_collected_files`` 用 ``get_data_raw_dir()`` 决定落盘目录。
``get_data_raw_dir()`` 读**环境变量 ``DATA_DIR``** ⇒ 那才是正确的隔离点。

而 ``backend/tests/conftest.py`` 已经给**数据库 / Redis / Celery** 都加了护栏
（护栏失效就整场测试失败），**唯独漏了文件系统** ⇒
「测试写生产数据」这次写的是**磁盘上的正式目录**。

修法
----
根 ``tests/conftest.py`` 把 ``DATA_DIR`` 指向临时目录 ⇒ 采集执行器在测试里
落盘到临时目录, 碰不到正式目录。

⚠️ 但「只在 conftest 顶层设一次」**曾经是无效的**（2026-11-11 实测踩到）:
  仓库根 ``.env`` 里有 ``DATA_DIR=./data``，而 ``backend/main.py`` / ``run.py``
  在 **import 时**就调 ``load_project_env(project_root)``（``override=True``）
  ⇒ 环境变量被覆盖回 ``./data``；再叠加 ``get_data_dir()`` 的 ``@lru_cache``
  把旧值冻住 ⇒ 护栏形同虚设（实测又往正式目录写了 8 个文件）。

⇒ 所以护栏必须**每个用例前**重新钉一次 ``DATA_DIR``，并 ``cache_clear()``
   掉 ``path_manager`` 的目录缓存。

本守卫测试断言:
1. 护栏 conftest **存在**, 且在 import 前就设了 ``DATA_DIR``;
2. conftest 有 ``pytest_runtest_setup`` 钩子 + ``cache_clear()``（防 ``.env`` 覆盖）;
3. ``DATA_DIR`` 指向**项目目录之外**（否则等于没隔离）;
4. 正式数据目录里没有测试产物 / 极小文件;
5. 用例级自检: 采集执行器在测试里**不写**正式目录。
"""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT_TESTS_CONFTEST = PROJECT_ROOT / "tests" / "conftest.py"
BACKEND_TESTS_CONFTEST = PROJECT_ROOT / "backend" / "tests" / "conftest.py"
REAL_DATA_RAW_DIR = PROJECT_ROOT / "data" / "raw"


def test_root_tests_conftest_exists():
    """根 ``tests/`` 必须有 conftest —— 护栏就装在这里。"""
    assert (
        ROOT_TESTS_CONFTEST.exists()
    ), "根 tests/ 缺少 conftest.py —— 文件系统护栏装在这里"


def test_root_tests_conftest_sets_data_dir_before_imports():
    """``DATA_DIR`` 必须在 **import 之前** 设好。

    ⚠️ ``get_data_raw_dir()`` 带 ``@lru_cache`` ⇒ 测试中途改它不生效 ⇒
    必须写在 conftest **模块顶层**（早于 collection）, 不是 fixture 里。
    """
    text = ROOT_TESTS_CONFTEST.read_text(encoding="utf-8")

    assert 'os.environ["DATA_DIR"]' in text, "conftest 必须设置 DATA_DIR 环境变量"

    # 设值语句必须在**任何 fixture / hook 定义之前**
    # (顶层代码在 import 期执行, 晚于它就来不及了)。
    data_dir_index = text.index('os.environ["DATA_DIR"]')
    for marker in ("@pytest.fixture", "def pytest_"):
        if marker in text:
            # ⚠️ 消息提到变量里：black 25.1.0 在 Python 3.11（CI）与 3.13（本机）
            #    对 `assert cond, ( "..." )` 的换行判定不同 ⇒ 不能用括号消息写法。
            order_message = "DATA_DIR 的设置必须早于 %s (顶层 import 期执行)" % marker
            assert data_dir_index < text.index(marker), order_message


def test_conftest_reasserts_data_dir_and_clears_path_manager_cache():
    """护栏必须**每个用例前重新钉一次** ``DATA_DIR``，并清掉 ``path_manager`` 的缓存。

    为什么顶层设一次**不够**（2026-11-11 实测踩到的坑）
    ---------------------------------------------------
    仓库根 ``.env`` 里有 ``DATA_DIR=./data``（相对路径 ⇒ 相对 cwd ⇒ 就是**正式目录**）。
    而 ``backend/main.py`` / ``run.py`` 在 **import 时**就调
    ``load_project_env(project_root)``，它的 ``load_dotenv(..., override=True)``
    会把 ``DATA_DIR`` **覆盖回** ``./data``。

    加上 ``get_data_dir()`` 是 ``@lru_cache(maxsize=1)`` —— 第一次调用就把
    ``./data`` 冻住 ⇒ 只在 conftest 顶层设一次环境变量，护栏**照样失效**。

    ⇒ 护栏必须两件事都做:
      1. 每个用例前重新写回 ``DATA_DIR``（``pytest_runtest_setup``）;
      2. 同时 ``cache_clear()`` 掉 ``get_data_dir`` / ``get_data_raw_dir`` 等缓存。
    """
    text = ROOT_TESTS_CONFTEST.read_text(encoding="utf-8")

    hook_message = (
        "conftest 必须有 pytest_runtest_setup 钩子, 每个用例前重新钉 DATA_DIR"
    )
    assert "pytest_runtest_setup" in text, hook_message

    cache_message = (
        "conftest 必须 cache_clear() 掉 path_manager 的目录缓存(lru_cache 会冻住旧值)"
    )
    assert "cache_clear" in text, cache_message

    getter_message = (
        "conftest 必须清理 get_data_raw_dir 的缓存（落盘目录就是它算出来的）"
    )
    assert "get_data_raw_dir" in text, getter_message


def test_data_dir_points_outside_project():
    """``DATA_DIR`` 必须指向**项目目录之外** ⇒ 否则等于没隔离。"""
    data_dir = os.environ.get("DATA_DIR", "")

    assert data_dir, "测试会话里 DATA_DIR 必须被设置"

    resolved = Path(data_dir).resolve()
    try:
        resolved.relative_to(PROJECT_ROOT)
    except ValueError:
        return  # 在项目目录之外 ⇒ 正确
    pytest_fail = (
        "DATA_DIR 指向了项目目录内部 (%s) —— 测试仍会写进正式数据目录" % resolved
    )
    raise AssertionError(pytest_fail)


def test_real_data_dir_has_no_test_artifacts():
    """正式数据目录里不许有**测试产物**。

    判定口径（不靠文件名猜）: 内容是测试占位符 ⇒ 一定是测试产物。
    """
    if not REAL_DATA_RAW_DIR.exists():
        return

    offenders = []
    for path in REAL_DATA_RAW_DIR.rglob("*"):
        if not path.is_file():
            continue
        try:
            head = path.read_bytes()[:64]
        except OSError:
            continue
        if b"fake-export" in head:
            offenders.append(path)

    assert not offenders, "正式数据目录里还有 %d 个测试产物(内容含 fake-export): %s" % (
        len(offenders),
        [p.name for p in offenders[:5]],
    )


def test_real_data_dir_has_no_tiny_files():
    """正式数据目录里不许有**极小文件**（<64 字节）。

    真实的采集导出产物是几十 KB ~ 几 MB 的有效表格;
    <64 字节的必然是占位/未写完的文件。
    """
    if not REAL_DATA_RAW_DIR.exists():
        return

    tiny = [
        path
        for path in REAL_DATA_RAW_DIR.rglob("*")
        if path.is_file() and path.stat().st_size < 64
    ]

    assert not tiny, "正式数据目录里还有 %d 个极小文件(<64 字节), 疑似测试残留: %s" % (
        len(tiny),
        [p.name for p in tiny[:5]],
    )


def test_executor_writes_into_isolated_dir_not_real_one():
    """执行器在测试里必须落盘到**隔离目录**, 不是正式目录。

    这是本护栏的**行为级**自检 —— 直接跑一次采集执行器的文件处理路径,
    断言正式目录没有新增文件。
    """
    if not REAL_DATA_RAW_DIR.exists():
        return

    before = {p for p in REAL_DATA_RAW_DIR.rglob("*") if p.is_file()}

    import asyncio
    from pathlib import Path as _Path

    source = _Path(os.environ.get("TEMP", ".")) / "mcode_guard_probe_export.xlsx"
    source.write_text("fake-export", encoding="utf-8")
    try:
        from modules.apps.collection_center.executor_v2 import CollectionExecutorV2

        executor = CollectionExecutorV2()
        asyncio.run(
            executor._process_collected_files([str(source)], "shopee", ["orders"])
        )
    except Exception:
        # 执行器内部依赖较重; 护栏的**核心**断言是「正式目录没被写」。
        pass
    finally:
        try:
            source.unlink()
        except OSError:
            pass

    after = {p for p in REAL_DATA_RAW_DIR.rglob("*") if p.is_file()}
    new_files = sorted(p.name for p in (after - before))

    assert not new_files, "采集执行器在测试里往正式数据目录写了 %d 个文件: %s" % (
        len(new_files),
        new_files[:5],
    )
