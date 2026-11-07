"""``20261122_remove_disabled_shop_collection_scopes`` 迁移 + 三层修复的行为守护。

为什么要有这个测试
------------------
「停用店铺残留进采集配置」这个缺陷的**三个面**都要钉死:

1. **存量清理**(迁移) —— 停用店的 scope 必须在配置与模板里都被摘掉,
   且配置摘要(``account_ids`` / ``data_domains`` / ``sub_domains``)必须重算对。
   摘要算错 ⇒ 顶部统计对不上、``_config_targets_shop`` 判错归属。
2. **防复发**(停用联动) —— 店铺被停用时, 引用它的 scope 必须自动摘掉。
3. **不再展示**(响应/前端过滤) —— 停用店根本不该出现在采集工作区里。

外加一条**口径护栏**: 迁移里内联的摘要实现必须与权威的
``collection_contracts.summarize_shop_scopes`` 逐字等价 —— 否则「迁移算出来的摘要」
与「运行时保存算出来的摘要」会分叉, 将来再保存一次配置, 数字就变了。

测试环境
--------
按 ``backend/tests/conftest.py`` 的测试护栏, pytest 期间 ``DATABASE_URL``
被指向一次性隔离库(testcontainers), **绝不允许连真实业务库**。
本文件在隔离库里自造数据, 不依赖开发库的数据状态。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text


REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = (
    REPO_ROOT
    / "current_migrations"
    / "versions"
    / "20261122_remove_disabled_shop_collection_scopes.py"
)
COLLECTION_CONFIG_VUE = (
    REPO_ROOT
    / "frontend"
    / "src"
    / "domains"
    / "collection"
    / "views"
    / "collection"
    / "CollectionConfig.vue"
)

#: 自造账号: 两个在营 + 一个停用
ACTIVE_A_ID = 9101
ACTIVE_B_ID = 9102
DISABLED_ID = 9103
ACTIVE_A_SAID = "shopee_sg_alpha_local"
ACTIVE_B_SAID = "shopee_ph_beta_local"
DISABLED_SAID = "shopee_my_off_local"

CONFIG_ID = 9201
TEMPLATE_ID = 9301


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "migration_20261122_disabled_scope", MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def migration():
    return _load_migration()


# ---------------------------------------------------------------------------
# 迁移链
# ---------------------------------------------------------------------------


def test_migration_chain(migration):
    """迁移链的 revision / down_revision 必须是预期值。"""
    assert (
        migration.revision
        == "current_schema_20261122_remove_disabled_shop_collection_scopes"
    )
    assert migration.down_revision == "current_schema_20261121_selling_price_source_enum"


def test_migration_mentions_all_three_layers(migration):
    """迁移 docstring 必须说清三层修复 —— 免得后来人只读到一半。"""
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "collection_config_shop_scopes" in source
    assert "collection_config_templates" in source
    assert "summarize_shop_scopes" in source


# ---------------------------------------------------------------------------
# 摘要口径：迁移内联实现 ≡ 权威实现
# ---------------------------------------------------------------------------


def test_inline_summary_matches_authoritative_implementation(migration):
    """内联摘要必须与 ``collection_contracts.summarize_shop_scopes`` 等价。

    ⚠️ 迁移**故意不 import** 业务模块(迁移应是冻结的快照), 所以这里用
    守护测试把两者钉在一起 —— 业务口径一变, 这条立刻红。

    两边喂**完全相同**的 dict(权威版吃的也是 dict) ⇒ 结果必须逐字相等。
    """
    from backend.services.collection_contracts import summarize_shop_scopes

    cases = [
        [],
        [(ACTIVE_A_SAID, ["analytics"], None)],
        [
            (ACTIVE_A_SAID, ["products", "analytics", "services"], {"services": ["agent"]}),
            (ACTIVE_B_SAID, ["analytics"], None),
        ],
        [(ACTIVE_A_SAID, ["services"], {"services": ["agent", "ai_assistant"]})],
        # domain 不在该 scope 的 data_domains 里 ⇒ 权威版会跳过, 内联版也必须跳过
        [(ACTIVE_A_SAID, ["analytics"], {"services": ["agent"]})],
        # 多个 scope 的同一 domain 合并去重
        [
            (ACTIVE_A_SAID, ["services"], {"services": ["agent"]}),
            (ACTIVE_B_SAID, ["services"], {"services": ["agent", "ai_assistant"]}),
        ],
        # ⚠️ 白名单外的 subtype 必须被过滤(权威版按 DATA_DOMAIN_SUB_TYPES 过滤)
        [(ACTIVE_A_SAID, ["services"], {"services": ["agent", "not_allowed"]})],
        # ⚠️ 白名单外的 domain(analytics 没有子类型)整个 domain 都要丢掉
        [(ACTIVE_A_SAID, ["analytics"], {"analytics": ["whatever"]})],
        # ⚠️ orders 的子类型白名单是 shopee/tiktok
        [(ACTIVE_A_SAID, ["orders"], {"orders": ["shopee", "tiktok"]})],
        # ⚠️ legacy 数组形态的 sub_domains —— 权威版会兜底成各 domain 的取值
        [(ACTIVE_A_SAID, ["services"], ["agent"])],
        # enabled=false 的 scope 不参与
        [(ACTIVE_A_SAID, ["analytics"], None, False)],
    ]
    for case in cases:
        rows = [
            {
                "shop_account_id": item[0],
                "data_domains": item[1],
                "sub_domains": item[2],
                "enabled": item[3] if len(item) > 3 else True,
            }
            for item in case
        ]
        authoritative = summarize_shop_scopes(rows)
        assert migration.summarize_active_scopes(rows) == authoritative, case


def test_inline_subtype_whitelist_matches_business(migration):
    """迁移内嵌的白名单快照必须与业务侧当前值一致。

    迁移不 import 业务模块(冻结快照) ⇒ 白名单只能内嵌一份。
    业务侧改了白名单而迁移没同步 ⇒ 这条立刻红, 不会等到下次迁移才出事。
    """
    from backend.services.component_name_utils import DATA_DOMAIN_SUB_TYPES

    assert migration._DATA_DOMAIN_SUB_TYPES == DATA_DOMAIN_SUB_TYPES


def test_inline_summary_skips_disabled_scopes(migration):
    """enabled=false 的 scope 不参与摘要。"""
    summary = migration.summarize_active_scopes(
        [
            {
                "shop_account_id": ACTIVE_A_SAID,
                "data_domains": ["analytics"],
                "sub_domains": None,
                "enabled": True,
            },
            {
                "shop_account_id": DISABLED_SAID,
                "data_domains": ["products"],
                "sub_domains": None,
                "enabled": False,
            },
        ]
    )
    assert summary["account_ids"] == [ACTIVE_A_SAID]
    assert summary["data_domains"] == ["analytics"]


# ---------------------------------------------------------------------------
# 存量清理：隔离库里造数据, 跑迁移 SQL, 断言
# ---------------------------------------------------------------------------


async def _seed(pg_session) -> None:
    """在隔离库里造一份「2 个在营 + 1 个停用」的最小数据集。

    ⚠️ 必须用 **ORM 对象**而不是裸 SQL: 隔离库是 ``Base.metadata.create_all``
    建的, 模型的 ``default=`` 是 **Python 侧**默认(不是 server_default) ——
    裸 SQL 插入会漏掉 ``batch_status`` 这类 NOT NULL 列直接炸。
    """
    from modules.core.db import (
        CollectionConfig,
        CollectionConfigShopScope,
        CollectionConfigTemplate,
        MainAccount,
        ShopAccount,
    )

    pg_session.add(
        MainAccount(
            id=9050,
            platform="shopee",
            main_account_id="MA-X",
            username="x-user",
            password_encrypted="x",
            enabled=True,
        )
    )
    for account_id, said, store_name, platform_shop_id, region, enabled in (
        (ACTIVE_A_ID, ACTIVE_A_SAID, "alpha.sg", "1111111", "SG", True),
        (ACTIVE_B_ID, ACTIVE_B_SAID, "beta.ph", "2222222", "PH", True),
        (DISABLED_ID, DISABLED_SAID, "off.my", "3333333", "MY", False),
    ):
        pg_session.add(
            ShopAccount(
                id=account_id,
                platform="shopee",
                shop_account_id=said,
                main_account_id="MA-X",
                store_name=store_name,
                platform_shop_id=platform_shop_id,
                shop_region=region,
                enabled=enabled,
            )
        )
    await pg_session.flush()

    pg_session.add(
        CollectionConfig(
            id=CONFIG_ID,
            name="cfg-x",
            platform="shopee",
            main_account_id="MA-X",
            granularity="monthly",
            date_range_type="yesterday",
            schedule_enabled=False,
            retry_count=3,
            execution_mode="headless",
            is_active=True,
            account_ids=[ACTIVE_A_SAID, ACTIVE_B_SAID, DISABLED_SAID],
            data_domains=["products", "analytics", "services"],
            sub_domains={"services": ["agent"]},
        )
    )
    await pg_session.flush()

    for said in (ACTIVE_A_SAID, ACTIVE_B_SAID, DISABLED_SAID):
        pg_session.add(
            CollectionConfigShopScope(
                config_id=CONFIG_ID,
                shop_account_id=said,
                data_domains=["products", "analytics", "services"],
                sub_domains={"services": ["agent"]},
                enabled=True,
            )
        )

    pg_session.add(
        CollectionConfigTemplate(
            id=TEMPLATE_ID,
            name="tpl-x",
            platform="shopee",
            main_account_id="MA-X",
            granularity="monthly",
            default_date_range_type="yesterday",
            default_execution_mode="headless",
            default_schedule_enabled=False,
            default_retry_count=3,
            default_shop_scopes=[
                {
                    "shop_account_id": ACTIVE_A_SAID,
                    "data_domains": ["products", "analytics", "services"],
                    "sub_domains": {"services": ["agent"]},
                    "enabled": True,
                },
                {
                    "shop_account_id": ACTIVE_B_SAID,
                    "data_domains": ["products", "analytics", "services"],
                    "sub_domains": {"services": ["agent"]},
                    "enabled": True,
                },
                {
                    "shop_account_id": DISABLED_SAID,
                    "data_domains": ["products", "analytics", "services"],
                    "sub_domains": {"services": ["agent"]},
                    "enabled": True,
                },
            ],
            is_active=True,
        )
    )
    await pg_session.flush()


async def _run_upgrade(migration, pg_session) -> None:
    """跑迁移的**真实** upgrade 逻辑。

    ⚠️ 用 ``AsyncSession.run_sync`` 把同步 Session 喂给迁移 ⇒ 测的就是
    生产上真正执行的那份代码(不是测试里复刻一遍的副本 ⇒ 不会漂移)。
    """
    await pg_session.run_sync(migration.apply_cleanup)


async def _run_downgrade(migration, pg_session) -> None:
    """跑迁移的**真实** downgrade 逻辑。"""
    await pg_session.run_sync(migration.apply_restore)


async def test_scope_of_disabled_shop_is_disabled(migration, pg_session):
    """停用店的 scope 会被摘掉; 在营店的不受影响。"""
    await _seed(pg_session)
    await _run_upgrade(migration, pg_session)

    rows = (
        await pg_session.execute(
            text(
                """
                SELECT shop_account_id, enabled
                FROM core.collection_config_shop_scopes
                WHERE config_id = :config_id
                ORDER BY shop_account_id
                """
            ),
            {"config_id": CONFIG_ID},
        )
    ).all()
    state = {row[0]: bool(row[1]) for row in rows}
    assert state[DISABLED_SAID] is False
    assert state[ACTIVE_A_SAID] is True
    assert state[ACTIVE_B_SAID] is True


async def test_config_summary_is_recalculated(migration, pg_session):
    """摘要重算: 死账号被摘掉, 且 data_domains 顺序与 sub_domains 结构不被破坏。"""
    await _seed(pg_session)
    await _run_upgrade(migration, pg_session)

    row = (
        await pg_session.execute(
            text(
                """
                SELECT account_ids, data_domains, sub_domains
                FROM core.collection_configs
                WHERE id = :config_id
                """
            ),
            {"config_id": CONFIG_ID},
        )
    ).mappings().one()

    account_ids = row["account_ids"]
    if isinstance(account_ids, str):
        account_ids = json.loads(account_ids)
    data_domains = row["data_domains"]
    if isinstance(data_domains, str):
        data_domains = json.loads(data_domains)
    sub_domains = row["sub_domains"]
    if isinstance(sub_domains, str):
        sub_domains = json.loads(sub_domains)

    assert DISABLED_SAID not in account_ids
    assert sorted(account_ids) == sorted([ACTIVE_A_SAID, ACTIVE_B_SAID])
    # ⚠️ 顺序必须保持「products, analytics, services」(不是字母序)
    assert data_domains == ["products", "analytics", "services"]
    # ⚠️ sub_domains 必须还是 {"services": ["agent"]} —— 不能双重编码成 ["[\"agent\"]"]
    assert sub_domains == {"services": ["agent"]}


async def test_template_scope_of_disabled_shop_is_disabled(migration, pg_session):
    """模板里的停用店也要摘掉 —— 否则按该模板新建配置会被 400 拒绝。"""
    await _seed(pg_session)
    await _run_upgrade(migration, pg_session)

    row = (
        await pg_session.execute(
            text(
                "SELECT default_shop_scopes FROM core.collection_config_templates "
                "WHERE id = :template_id"
            ),
            {"template_id": TEMPLATE_ID},
        )
    ).scalar_one()
    scopes = row if isinstance(row, list) else json.loads(row)
    state = {scope["shop_account_id"]: bool(scope.get("enabled", True)) for scope in scopes}
    assert state[DISABLED_SAID] is False
    assert state[ACTIVE_A_SAID] is True


async def test_template_summary_drops_disabled_shop_scope(migration, pg_session):
    """模板响应里不能带停用店 —— 否则「用模板新建配置」会被 400 拒绝。

    实测成因: 前端把模板的 ``default_shop_scopes`` 整份当 payload 提交
    (``CollectionConfig.vue:1353``), 而后端 ``extra_shop_ids`` 校验只认
    **在营账号** ⇒ 停用店哪怕 ``enabled=false`` 也会被判成"越权店铺" ⇒ 400。
    ⇒ 所以必须**从模板响应里彻底拿掉**, 迁移只置 enabled=false 不够。
    """
    from backend.domains.collection.routers.collection_config import (
        _build_template_summary,
    )
    from backend.schemas.collection import CollectionAccountResponse
    from modules.core.db import CollectionConfigTemplate

    await _seed(pg_session)
    row = (
        await pg_session.execute(
            text(
                "SELECT * FROM core.collection_config_templates WHERE id = :template_id"
            ),
            {"template_id": TEMPLATE_ID},
        )
    ).mappings().one()
    template = CollectionConfigTemplate(**dict(row))

    summary = _build_template_summary(
        template,
        [],
        active_accounts=[
            CollectionAccountResponse(
                id=ACTIVE_A_SAID, name="alpha.sg", platform="shopee"
            ),
            CollectionAccountResponse(
                id=ACTIVE_B_SAID, name="beta.ph", platform="shopee"
            ),
        ],
    )

    # ``summary.default_shop_scopes`` 是 ``List[CollectionTemplateShopScopeResponse]``
    # (Pydantic 对象, 不是 dict) ⇒ 用属性访问取 shop_account_id
    shop_ids = [
        str(getattr(scope, "shop_account_id", "") or "")
        for scope in summary.default_shop_scopes
    ]
    assert DISABLED_SAID not in shop_ids, "停用店不能出现在模板响应的默认范围里"
    assert ACTIVE_A_SAID in shop_ids
    assert ACTIVE_B_SAID in shop_ids


async def test_upgrade_tolerates_non_object_template_scope_elements(
    migration, pg_session
):
    """模板 scope 数组里混进非对象元素时, 迁移不能崩, 且不能改动它。

    ``elem->>'shop_account_id'`` 只能作用在 object 上 ⇒ 迁移里用
    ``jsonb_typeof(elem) = 'object'`` 守卫。崩掉 = 整个部署被卡住。
    """
    await _seed(pg_session)
    template = (
        await pg_session.execute(
            text(
                "SELECT default_shop_scopes FROM core.collection_config_templates "
                "WHERE id = :template_id"
            ),
            {"template_id": TEMPLATE_ID},
        )
    ).scalar_one()
    scopes = list(template)
    scopes.append("legacy-string-element")
    await pg_session.execute(
        text(
            "UPDATE core.collection_config_templates "
            "SET default_shop_scopes = CAST(:scopes AS jsonb) WHERE id = :template_id"
        ),
        {
            "scopes": json.dumps(scopes),
            "template_id": TEMPLATE_ID,
        },
    )

    await _run_upgrade(migration, pg_session)

    after = (
        await pg_session.execute(
            text(
                "SELECT default_shop_scopes FROM core.collection_config_templates "
                "WHERE id = :template_id"
            ),
            {"template_id": TEMPLATE_ID},
        )
    ).scalar_one()
    after = list(after)
    assert "legacy-string-element" in after, "非对象元素必须原样保留"
    state = {
        scope["shop_account_id"]: bool(scope.get("enabled", True))
        for scope in after
        if isinstance(scope, dict)
    }
    assert state[DISABLED_SAID] is False
    assert state[ACTIVE_A_SAID] is True


async def test_upgrade_is_idempotent(migration, pg_session):
    """重跑不改变结果。"""
    await _seed(pg_session)
    await _run_upgrade(migration, pg_session)
    first = (
        await pg_session.execute(
            text(
                "SELECT account_ids, data_domains, sub_domains "
                "FROM core.collection_configs WHERE id = :config_id"
            ),
            {"config_id": CONFIG_ID},
        )
    ).mappings().one()
    await _run_upgrade(migration, pg_session)
    second = (
        await pg_session.execute(
            text(
                "SELECT account_ids, data_domains, sub_domains "
                "FROM core.collection_configs WHERE id = :config_id"
            ),
            {"config_id": CONFIG_ID},
        )
    ).mappings().one()
    assert dict(first) == dict(second)


async def test_downgrade_restores_scope(migration, pg_session):
    """回滚: 参与标记恢复, 摘要跟着恢复。"""
    await _seed(pg_session)
    await _run_upgrade(migration, pg_session)

    await _run_downgrade(migration, pg_session)

    state = {
        row[0]: bool(row[1])
        for row in (
            await pg_session.execute(
                text(
                    """
                    SELECT shop_account_id, enabled
                    FROM core.collection_config_shop_scopes
                    WHERE config_id = :config_id
                    ORDER BY shop_account_id
                    """
                ),
                {"config_id": CONFIG_ID},
            )
        ).all()
    }
    assert state[DISABLED_SAID] is True

    summary = (
        await pg_session.execute(
            text(
                "SELECT account_ids FROM core.collection_configs WHERE id = :config_id"
            ),
            {"config_id": CONFIG_ID},
        )
    ).scalar_one()
    if isinstance(summary, str):
        summary = json.loads(summary)
    assert DISABLED_SAID in summary


# ---------------------------------------------------------------------------
# 第二层 / 第三层：后端联动与展示过滤
# ---------------------------------------------------------------------------


def test_drop_disabled_shop_scopes_filters_response():
    """响应层过滤: 停用店从 shop_scopes 与 account_ids 里消失。"""
    from backend.domains.collection.routers.collection_config import (
        _drop_disabled_shop_scopes,
    )

    response = SimpleNamespace(
        shop_scopes=[
            SimpleNamespace(shop_account_id=ACTIVE_A_SAID),
            SimpleNamespace(shop_account_id=DISABLED_SAID),
            SimpleNamespace(shop_account_id=ACTIVE_B_SAID),
        ],
        account_ids=[ACTIVE_A_SAID, DISABLED_SAID, ACTIVE_B_SAID],
    )
    _drop_disabled_shop_scopes(response, {DISABLED_SAID})

    assert [s.shop_account_id for s in response.shop_scopes] == [
        ACTIVE_A_SAID,
        ACTIVE_B_SAID,
    ]
    assert response.account_ids == [ACTIVE_A_SAID, ACTIVE_B_SAID]


def test_drop_disabled_shop_scopes_is_noop_without_disabled_ids():
    """没有停用店时不得动响应(避免误伤正常配置)。"""
    from backend.domains.collection.routers.collection_config import (
        _drop_disabled_shop_scopes,
    )

    response = SimpleNamespace(
        shop_scopes=[SimpleNamespace(shop_account_id=ACTIVE_A_SAID)],
        account_ids=[ACTIVE_A_SAID],
    )
    _drop_disabled_shop_scopes(response, set())
    assert len(response.shop_scopes) == 1
    assert response.account_ids == [ACTIVE_A_SAID]


async def test_disable_shop_in_collection_scopes_on_account_disable(
    pg_session,
):
    """第二层: 店铺被停用 ⇒ 引用它的 scope 自动摘掉 + 摘要重算。"""
    from backend.domains.collection.routers.shop_accounts import (
        _disable_shop_in_collection_scopes,
    )

    await _seed(pg_session)
    removed = await _disable_shop_in_collection_scopes(pg_session, DISABLED_SAID)
    assert removed == 1

    row = (
        await pg_session.execute(
            text(
                "SELECT enabled FROM core.collection_config_shop_scopes "
                "WHERE config_id = :config_id AND shop_account_id = :said"
            ),
            {"config_id": CONFIG_ID, "said": DISABLED_SAID},
        )
    ).scalar_one()
    assert row is False

    summary = (
        await pg_session.execute(
            text(
                "SELECT account_ids FROM core.collection_configs WHERE id = :config_id"
            ),
            {"config_id": CONFIG_ID},
        )
    ).scalar_one()
    if isinstance(summary, str):
        summary = json.loads(summary)
    assert DISABLED_SAID not in summary


async def test_disable_shop_in_collection_scopes_is_noop_for_unknown_shop(
    pg_session,
):
    """没被任何配置引用时不得报错。"""
    from backend.domains.collection.routers.shop_accounts import (
        _disable_shop_in_collection_scopes,
    )

    assert await _disable_shop_in_collection_scopes(pg_session, "no_such_shop") == 0


class _NoCommitSession:
    """把 ``commit``/``rollback`` 换成 ``flush``。

    隔离库是**会话级**容器 ⇒ 一旦真的 commit, 数据会留给后面的用例,
    而本文件用固定主键造数 ⇒ 会撞主键。
    路由函数内部会 commit, 所以给它们喂这个壳。
    """

    def __init__(self, session):
        self._session = session

    def __getattr__(self, name):
        return getattr(self._session, name)

    async def commit(self):
        await self._session.flush()

    async def rollback(self):
        await self._session.flush()


async def _scope_enabled_map(pg_session, config_id=CONFIG_ID) -> dict:
    rows = (
        await pg_session.execute(
            text(
                """
                SELECT shop_account_id, enabled
                FROM core.collection_config_shop_scopes
                WHERE config_id = :config_id
                """
            ),
            {"config_id": config_id},
        )
    ).all()
    return {row[0]: bool(row[1]) for row in rows}


async def _config_account_ids(pg_session, config_id=CONFIG_ID) -> list:
    value = (
        await pg_session.execute(
            text(
                "SELECT account_ids FROM core.collection_configs WHERE id = :config_id"
            ),
            {"config_id": config_id},
        )
    ).scalar_one()
    if isinstance(value, str):
        value = json.loads(value)
    return list(value or [])


async def test_update_shop_account_disabling_cleans_up_scopes(pg_session):
    """第二层的**入口**被钉死: 在营店被停用 ⇒ 引用它的 scope 立刻摘掉。

    这正是本次线上问题的成因链路(上一批身份对齐停了店, 却没人回头清理
    采集配置里的引用 ⇒ 采集工作区多出一行点不动的幽灵店铺)。
    """
    from backend.domains.collection.routers.shop_accounts import update_shop_account
    from backend.schemas.shop_account import ShopAccountUpdate

    await _seed(pg_session)
    session = _NoCommitSession(pg_session)

    await update_shop_account(
        ACTIVE_A_SAID, ShopAccountUpdate(enabled=False), session
    )

    state = await _scope_enabled_map(pg_session)
    assert state[ACTIVE_A_SAID] is False
    assert state[ACTIVE_B_SAID] is True

    account_ids = await _config_account_ids(pg_session)
    assert ACTIVE_A_SAID not in account_ids
    assert ACTIVE_B_SAID in account_ids


async def test_delete_shop_account_cleans_up_scopes(pg_session):
    """店铺被删除 ⇒ 采集配置里的引用与摘要同样要清。

    ⚠️ scope 行本身会被数据库的 ``ON DELETE CASCADE`` 带走(实测确实如此),
    **但配置摘要没人自动重算** ⇒ 不做这一步, 顶部「店铺总览」会一直挂着
    一个已经删掉的账号。
    """
    from backend.domains.collection.routers.shop_accounts import delete_shop_account

    await _seed(pg_session)
    session = _NoCommitSession(pg_session)

    await delete_shop_account(ACTIVE_A_SAID, session)

    state = await _scope_enabled_map(pg_session)
    # 被删的店: scope 行要么被级联删除, 要么被摘掉 —— 两种都不算残留
    assert state.get(ACTIVE_A_SAID, False) is False
    assert state[ACTIVE_B_SAID] is True

    account_ids = await _config_account_ids(pg_session)
    assert ACTIVE_A_SAID not in account_ids


# ---------------------------------------------------------------------------
# 第三层：前端不再渲染停用店
# ---------------------------------------------------------------------------


def test_frontend_hides_rows_without_account():
    """前端必须过滤掉「账号查不到」的行(停用/已删除)。"""
    source = COLLECTION_CONFIG_VUE.read_text(encoding="utf-8")
    assert ".filter((row) => row.account)" in source, (
        "采集工作区必须过滤掉账号查不到的行 —— 否则停用店会变成一排点不动的复选框"
    )


def test_frontend_scope_row_maps_account():
    """行必须带 account, 过滤才有依据。"""
    source = COLLECTION_CONFIG_VUE.read_text(encoding="utf-8")
    assert "account: getAccountById(scope.shop_account_id)" in source
