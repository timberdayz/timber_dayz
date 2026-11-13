"""router **唯一挂载点**的守护（2026-11-13，批次 C1）。

背景
----
``backend/domains/collection/routes.py`` 与 ``backend/domains/platform/routes.py``
**都** include 了同一批 5 个 router（主账号 / 店铺账号 / 店铺别名 /
平台店铺ID发现 / 仓名别名）⇒ 同一组接口被**挂载两次**。

后果
----
* 同一批端点被注册两遍 —— 实测（改前）development 模式 759 条端点条目里
  有 **24 条 (路径, 方法) 重复，涉及 17 条路径**；collector 模式同样是 24 条；
* FastAPI 生成 OpenAPI 时对每个重复的路由打一条
  ``UserWarning: Duplicate Operation ID``（实测 **24 条**）———
  这是重复挂载**唯一可观测**的信号：schema 里同一 (路径, 方法) 会被
  **后一次注册覆盖**，所以文档本身看不出重复；
* 路由匹配永远命中**先注册**的那一份 ⇒ 后一份是死代码。

⇒ 今天**没有功能故障**（两份挂载的 prefix 与 tags 完全相同），
   但它违反律 1「真源只能一个」。

修法与它的约束
--------------
账号类 router 的唯一挂载点定在 **platform 域**：

* ``backend/app/runtime.py`` 的 ``register_mode_routes`` 里，
  common（含 platform）**所有运行模式都注册**，
  而 **production 模式根本不注册 collection 域**
  ⇒ 账号类接口在生产上**只由 platform 提供**
  ⇒ 唯一挂载点只能在 platform 侧，反过来删会**删掉生产接口**。

本文件锁三件事
--------------
1. **任何运行模式**下都不存在重复的 (路径, 方法) 注册；
2. production 模式下账号类接口**依然存在** ——
   防止"去重复"变成"删接口"；
3. 这 5 组 router 的端点函数**各自只被注册一次**。

⚠️ 第 2 条是本文件存在的**主要理由**：
   去掉重复挂载最省事的写法是「两边都留一份 / 各删一半」，
   真正会出事的是**删掉了 platform 那份** ⇒ production 直接 404。
"""

import importlib
import warnings
from collections import defaultdict

import pytest


#: 这 5 组账号类 router 的**代表性路径** —— 用来证明"接口还在"，而不是"被删了"。
ACCOUNT_ROUTE_PATHS = (
    "/api/main-accounts",
    "/api/shop-accounts",
    "/api/shop-account-aliases",
    "/api/platform-shop-discoveries",
    "/api/warehouse-name-aliases",
)

#: 这 5 组 router 的**端点函数所在模块** —— 用来断言"只被注册一次"。
ACCOUNT_ROUTER_MODULES = (
    "backend.domains.collection.routers.main_accounts",
    "backend.domains.collection.routers.shop_accounts",
    "backend.domains.collection.routers.shop_account_aliases",
    "backend.domains.collection.routers.platform_shop_discoveries",
    "backend.domains.collection.routers.warehouse_name_aliases",
)


def _reload_main(monkeypatch, runtime_mode: str, *, deployment_role: str | None = None):
    import backend.main as main_module

    monkeypatch.setenv("APP_RUNTIME_MODE", runtime_mode)
    # DEPLOYMENT_ROLE 必须显式钉死（理由同 test_runtime_mode_route_registration.py）：
    # 不钉死的话，进程里残留的 DEPLOYMENT_ROLE 会让断言依赖执行顺序。
    if deployment_role is None:
        monkeypatch.delenv("DEPLOYMENT_ROLE", raising=False)
    else:
        monkeypatch.setenv("DEPLOYMENT_ROLE", deployment_role)
    return importlib.reload(main_module)


def _endpoint_index(app) -> dict:
    """(路径, 方法) → 端点函数列表（长度 > 1 即为重复注册）。"""
    index: dict[tuple[str, str], list] = defaultdict(list)
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        for method in methods:
            index[(path, method)].append(getattr(route, "endpoint", None))
    return index


def _paths_for(app) -> set[str]:
    return {route.path for route in app.routes if hasattr(route, "path")}


# ---------------------------------------------------------------------------
# 1. 任何运行模式都不许重复注册
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "runtime_mode, deployment_role",
    [
        ("development", None),
        ("collector", "collector"),
        ("collector", "local"),
        ("production", None),
    ],
)
def test_no_endpoint_is_registered_twice(monkeypatch, runtime_mode, deployment_role):
    """同一个 (路径, 方法) 在一个 app 里只能注册一次。

    ⚠️ 逐个运行模式都查 —— 重复只出现在**注册了 collection 域**的模式里，
       只查 production 会漏掉（production 根本不注册 collection）。
    """
    module = _reload_main(monkeypatch, runtime_mode, deployment_role=deployment_role)
    index = _endpoint_index(module.app)
    duplicates = {
        key: endpoints for key, endpoints in index.items() if len(endpoints) > 1
    }

    assert not duplicates, (
        f"{runtime_mode} 模式下有 {len(duplicates)} 条端点被重复注册："
        f"{sorted(duplicates)[:5]}"
    )


def test_building_openapi_emits_no_duplicate_operation_id_warning(monkeypatch):
    """生成 OpenAPI 时**不许**出现 ``Duplicate Operation ID`` 警告。

    ⚠️ 这条才是重复挂载**唯一可观测**的信号，别被表象骗了：
       FastAPI 生成 schema 时用的是 ``paths[path][method] = operation``
       ⇒ 同一 (路径, 方法) 会被**后一次注册覆盖**
       ⇒ 最终 schema 里的 operation_id 反而是唯一的、看不出重复；
       但每个重复的路由都会打一条 ``UserWarning: Duplicate Operation ID``
       （实测改前 **24 条**），而且注册表里有一份是**死代码**。
    """
    module = _reload_main(monkeypatch, "development")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        module.app.openapi()

    duplicates = [
        str(item.message)
        for item in caught
        if "Duplicate Operation ID" in str(item.message)
    ]
    assert not duplicates, (
        f"重复挂载产生了 {len(duplicates)} 条 Duplicate Operation ID 警告："
        f"{duplicates[:3]}"
    )


# ---------------------------------------------------------------------------
# 2. 去重复 ≠ 删接口
# ---------------------------------------------------------------------------


def test_account_routes_still_exist_in_production_mode(monkeypatch):
    """production 模式不注册 collection 域 ⇒ 账号类接口只能靠 platform 侧。

    ⚠️ 这是本次改动**最危险的方向**：若把唯一挂载点定在 collection 侧，
       生产上这 5 组接口会直接 404 ⇒ 店铺/主账号管理整体不可用。
    """
    module = _reload_main(monkeypatch, "production")
    paths = _paths_for(module.app)

    for path in ACCOUNT_ROUTE_PATHS:
        assert path in paths, f"production 模式下 {path} 不见了"


def test_account_routes_still_exist_in_development_mode(monkeypatch):
    module = _reload_main(monkeypatch, "development")
    paths = _paths_for(module.app)

    for path in ACCOUNT_ROUTE_PATHS:
        assert path in paths, f"development 模式下 {path} 不见了"


# ---------------------------------------------------------------------------
# 3. 这 5 组 router 的端点各只注册一次
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "runtime_mode, deployment_role",
    [
        ("development", None),
        ("collector", "collector"),
        ("production", None),
    ],
)
def test_account_router_endpoints_are_mounted_exactly_once(
    monkeypatch, runtime_mode, deployment_role
):
    """按**端点函数**维度再查一次 —— 路径没重复 ≠ 端点没重复。

    ⚠️ 只查 (路径, 方法) 有一个盲区：同一组端点被挂到**不同前缀**下时，
       路径不冲突，但仍然是"同一个接口挂了两遍"。
       这里按端点函数（module + qualname）统计被注册了几次。

    ⚠️ 注意口径：端点函数住在 ``collection/routers/`` 目录下，
       但**挂载点**在 platform 域 —— 所以这里数的是"注册了几次"，
       不是"在哪个域挂的"。
    """
    module = _reload_main(monkeypatch, runtime_mode, deployment_role=deployment_role)
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for route in module.app.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            continue
        key = (
            getattr(endpoint, "__module__", ""),
            getattr(endpoint, "__qualname__", ""),
        )
        counts[key] += 1

    repeated = {
        key: count
        for key, count in counts.items()
        if count > 1 and key[0] in ACCOUNT_ROUTER_MODULES
    }
    assert (
        not repeated
    ), f"{runtime_mode} 模式下这些端点被注册了多次：{sorted(repeated)}"
