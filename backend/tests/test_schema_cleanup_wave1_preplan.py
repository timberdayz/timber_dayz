"""wave1 schema 清理预演的「批准 / 阻塞」判定守护。

背景
----
``docs/superpowers/plans/2026-03-28-database-schema-cleanup-wave1.md``(2026-03-28)
落笔时, 只有 ``public.target_breakdown`` 够格进 wave1, 另外三张
(``performance_config`` / ``sales_campaigns`` / ``sales_campaign_shops``)
被卡在「ORM/runtime 仍解析到默认 schema」。

但 ORM 口径后来变了:

* 2026-05-06(commit ``128385141``「refactor(schema): continue phase6 schema slice
  decomposition」)起, 这四张表的 ORM **全部**声明 ``{"schema": "a_class"}``;
* 当前事实源 ``current_migrations`` 的静态基线也只建 ``a_class.*``。

⇒ 阻塞理由已经消失, 预演工具现在按「ORM 已对齐 + 运行时不再引用 public 副本」
判定, 四张表都够格。旧断言(只批一张、另外三张必须被阻塞)已经过期。

本文件改为盯**判定规则本身**:
批准 ⇔ ``ready_for_wave1``(ORM 落在目标 schema 且没有 public 引用);
被阻塞的条目必须给出具体阻塞理由。
"""

from backend.utils.schema_cleanup_low_risk_proofs import collect_low_risk_candidate_proofs
from backend.utils.schema_cleanup_wave1_preplan import build_wave1_preplan


#: wave1 的候选表(与 ``backend/utils/schema_cleanup_wave1_preplan.py`` 一致)
CANDIDATE_TABLES = (
    "target_breakdown",
    "performance_config",
    "sales_campaigns",
    "sales_campaign_shops",
)


def _preplan_by_table():
    preplan = build_wave1_preplan()
    approved = {item["table_name"]: item for item in preplan["approved_targets"]}
    blocked = {item["table_name"]: item for item in preplan["blocked_targets"]}
    return approved, blocked


def test_wave1_preplan_approves_target_breakdown_after_orm_alignment():
    approved, blocked = _preplan_by_table()
    proofs = collect_low_risk_candidate_proofs()

    # 计划里的目标表必须被批准, 且归到 a_class + 归档改名
    assert "target_breakdown" in approved
    assert approved["target_breakdown"]["source_schema"] == "public"
    assert approved["target_breakdown"]["target_schema"] == "a_class"
    assert approved["target_breakdown"]["operation"] == "archive_rename"
    assert "target_breakdown" not in blocked

    # 批准 ⇔ ready_for_wave1(ORM 已落目标 schema 且运行时不再引用 public 副本)
    for table_name in CANDIDATE_TABLES:
        if proofs[table_name]["ready_for_wave1"]:
            assert table_name in approved, f"{table_name} 应当被批准"
        else:
            assert table_name in blocked, f"{table_name} 应当被阻塞"


def test_wave1_preplan_has_no_orm_schema_blockers_left():
    approved, blocked = _preplan_by_table()
    proofs = collect_low_risk_candidate_proofs()

    # 四张候选表的 ORM 都已经落在 a_class ⇒ 不该再有「schema 口径」类阻塞
    for table_name in CANDIDATE_TABLES:
        assert proofs[table_name]["model_schema"] == "a_class"
        assert proofs[table_name]["public_schema_sql_refs"] == 0

    assert blocked == {}

    # 每条被批准的记录都要写清目标 schema 与动作
    for table_name, item in approved.items():
        assert item["target_schema"] == proofs[table_name]["expected_target_schema"]
        assert item["operation"] == "archive_rename"

    # 候选表必须被完整分类, 不能凭空多出/少掉
    assert set(approved) | set(blocked) == set(CANDIDATE_TABLES)
