"""根 ``tests/`` 的**文件系统护栏**：测试绝不能写正式数据目录。

事故现场（2026-11-11）
----------------------
跑一次 ``tests/test_executor_v2.py``（27 个用例）会往
**正式** ``data/raw/2026/`` 里写 **8 个文件**（4 个 xlsx + 4 个 .meta.json）。

实测（本地开发库）:
* 167 个文件内容是 ``fake-export``（**11 字节**）—— 根本不是有效的 xlsx;
* 其中 114 个带 ``_1`` / ``_2`` / ``_3`` 序号后缀（同一时间戳重复 4 份）;
* 全部**没有** ``public.catalog_files`` 入库记录（孤儿文件）;
* 与真实采集文件对照：真实的是 **89 KB** 的有效 .xls。

⇒ 排查数据问题时, 这些假文件会让人误判成「订单采了没入库」
   （本次差点这么判）⇒ **必须清掉, 且不能再发生**。

根因
----
``modules/apps/collection_center/executor_v2.py`` 的
``_process_collected_files`` 用 ``get_data_raw_dir()`` 决定落盘目录。
``modules/core/path_manager.py`` 的 ``get_data_raw_dir()`` 读
**环境变量 ``DATA_DIR``** ⇒ 那才是正确的隔离点。

而 ``backend/tests/conftest.py`` 已经给**数据库 / Redis / Celery** 都加了护栏
（护栏失效就整场测试失败），**唯独漏了文件系统** ⇒
「测试写生产数据」这次写的是**磁盘上的正式目录**。

为什么用环境变量而不是 monkeypatch
-----------------------------------
``get_data_raw_dir()`` 带 ``@lru_cache`` ⇒ 测试中途改它不生效,
必须**在任何模块 import 之前**设好环境变量
（与 ``backend/tests/conftest.py`` 里数据库护栏同一个道理）。

⇒ 这里在 **conftest 模块顶层**设 ``DATA_DIR``, 指向一个**临时目录**。
   正式链路 (``scripts/start_collection_formal.ps1`` 等) 不读这个变量,
   不受影响。

⚠️ 只在**测试会话**里生效 —— 这是 pytest 进程内的环境变量,
   跑完即随进程消失。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


#: 测试期间的隔离数据根目录（``data/`` 的替身）。
_TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="mcode_test_data_"))

#: 必须**早于任何模块 import** —— ``get_data_raw_dir`` 带 ``lru_cache``,
#: import 期求值之后就改不动了。
os.environ["DATA_DIR"] = str(_TEST_DATA_DIR)

#: 隔离根下的各子目录（提前建好, 免得代码里 ``mkdir`` 之前先读目录不存在）。
for _sub in ("raw", "processed", "input", "output"):
    try:
        (_TEST_DATA_DIR / _sub).mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


#: 正式数据目录（测试期间**绝不能**被写入的位置）。
_REAL_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


#: ``modules.core.path_manager`` 里带 ``lru_cache`` 的目录函数。
#:
#: ⚠️ 必须一起清掉 —— 只改环境变量**不够**:
#:   ``get_data_dir()`` 是 ``@lru_cache(maxsize=1)``, 第一次调用就把结果**冻住**了。
#:   而第一次调用发生在「谁先 import 了它」那一刻。
_CACHE_CLEARABLE_DIR_GETTERS = (
    "get_data_dir",
    "get_data_raw_dir",
    "get_data_processed_dir",
    "get_data_input_dir",
)


def _reassert_isolated_data_dir() -> None:
    """把 ``DATA_DIR`` 重新钉回隔离目录, 并清掉 ``path_manager`` 的目录缓存。

    为什么每个用例前都要重来一遍
    --------------------------
    仓库根 ``.env`` 里有 ``DATA_DIR=./data``（相对路径 ⇒ 相对 cwd ⇒ 就是**正式目录**）。
    而 ``backend/main.py`` / ``run.py`` 在 **import 时**就会调
    ``load_project_env(project_root)``, 它的 ``load_dotenv(..., override=True)``
    会把 ``DATA_DIR`` **覆盖回** ``./data``。

    ⇒ 只在 conftest 顶层设一次环境变量是**不够**的:
      import 期一被覆盖, ``get_data_dir()`` 的 lru_cache 就把 ``./data`` 冻住,
      之后测试就会往正式数据目录里写文件。

    ⇒ 所以这里在**每个用例开始前**重新钉一次环境变量, 并清掉目录缓存 ——
      让 ``get_data_dir()`` 下次调用时重新读到隔离目录。

    ⚠️ 用 ``pytest_runtest_setup`` 而不是 ``pytest_configure``:
      ``.env`` 是在**收集期**(import 测试模块时)被加载的,
      ``pytest_configure`` 跑在收集**之前**, 那时覆盖还没发生。
    """
    os.environ["DATA_DIR"] = str(_TEST_DATA_DIR)
    try:
        from modules.core import path_manager
    except Exception:  # noqa: BLE001  (导入失败不该让整场测试挂掉)
        return
    for name in _CACHE_CLEARABLE_DIR_GETTERS:
        getter = getattr(path_manager, name, None)
        cache_clear = getattr(getter, "cache_clear", None)
        if cache_clear is not None:
            try:
                cache_clear()
            except Exception:  # noqa: BLE001
                pass


def pytest_runtest_setup(item):
    """每个用例开始前重新钉死隔离目录（见 ``_reassert_isolated_data_dir``）。"""
    _reassert_isolated_data_dir()


def pytest_sessionfinish(session, exitstatus):
    """会话结束时的**兜底自检**：正式数据目录有没有被测试动过。

    ⚠️ 正常情况下**不应该**有任何新增 —— 所以这里只**告警**不失败
    （失败会让「历史遗留污染」变成「每次跑测试都红」⇒ 反而没人敢跑测试）。
    但告警必须足够显眼, 让人知道又脏了。
    """
    try:
        if not _REAL_DATA_DIR.exists():
            return
        suspicious = [
            p
            for p in _REAL_DATA_DIR.rglob("*")
            if p.is_file() and p.stat().st_size < 64
        ]
        if suspicious:
            print(
                "\n[文件系统护栏] 正式数据目录里出现了 %d 个**极小文件**"
                "（疑似测试产物, <64 字节）:" % len(suspicious)
            )
            for p in suspicious[:10]:
                print("           %s" % p)
            print(
                "           ⇒ 正式数据目录被测试污染了, 请检查 conftest 的 DATA_DIR 隔离。\n"
            )
    except Exception:
        pass
