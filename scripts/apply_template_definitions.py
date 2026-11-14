#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把仓库里的**模板决策资产**投影到数据库, 并提供「仓库 ↔ 库内」差异守卫。

三个子命令
----------
``--validate-only``
    **纯离线**校验定义文件本身(格式、字段、唯一性)。不连数据库 ⇒
    可以进 GitHub CI(CI runner 上没有业务库)。

``--check``
    连库比对「仓库定义」与「库内 published 实例」的**决策资产**。
    有任何差异就以退出码 1 结束, 并逐条打印差异。
    ⇒ 这是「有人在库里改了模板但没改 Git」或反之的**守门人**。

``--apply``
    把定义**投影**到数据库: 对有差异的维度发布新版本
    (走 :class:`backend.services.field_mapping_template_service.FieldMappingTemplateService`
    的正常发布流程 ⇒ 归档旧版本 + 版本号自增 + 家族投影, 与界面发布同一条路)。

为什么要有「仓库定义」这一层
----------------------------
以前改模板只发生在数据库里: 没法 review、没法回滚、换环境要手工重配。
现在「这个维度该长什么样」是仓库里的一个文件, 改它就是一次可 review 的提交。

但**状态**仍在数据库里: 版本号、命中次数、成功率、审计字段。
⇒ 两者的分界线由 :mod:`scripts.template_definitions` 统一定义。

用法
----
    python scripts/apply_template_definitions.py --validate-only   # CI 用
    python scripts/apply_template_definitions.py --check             # 差异守卫
    python scripts/apply_template_definitions.py --apply --dry-run   # 看投影计划
    python scripts/apply_template_definitions.py --apply             # 真投影

注意
----
* ``--check`` / ``--apply`` **只读/只写模板表**, 不碰业务数据。
* ``--apply`` 会发布新版本(旧版本自动归档) —— 这是**发布动作**,
  属于会改变线上行为的人工决策, 请在确认差异无误后再执行。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from scripts.template_definitions import (
        DEFINITIONS_DIR,
        DECISION_FIELDS,
        OVERLAYS_DIR,
        TemplateDefinitionError,
        changed_decision_fields,
        decision_payload,
        diff_decision_payload,
        dimension_key,
        dimension_key_text,
        load_definitions,
        load_overlays,
        merge_overlay,
    )
except ModuleNotFoundError:  # 直接 `python scripts/...` 执行(Windows)
    from template_definitions import (  # type: ignore[no-redef]
        DEFINITIONS_DIR,
        DECISION_FIELDS,
        OVERLAYS_DIR,
        TemplateDefinitionError,
        decision_payload,
        diff_decision_payload,
        dimension_key,
        dimension_key_text,
        load_definitions,
        load_overlays,
        merge_overlay,
    )


DimensionKey = Tuple[str, Optional[str], ...]


def _apply_overlays(
    definitions: Dict[DimensionKey, Dict[str, Any]],
    overlay_names: List[str],
) -> Dict[DimensionKey, Dict[str, Any]]:
    """把指定 overlay 叠加到基线定义上。"""
    if not overlay_names:
        return definitions
    overlays = load_overlays()
    merged = dict(definitions)
    for name in overlay_names:
        overlay = overlays.get(name)
        if overlay is None:
            available = ", ".join(sorted(overlays)) or "(无)"
            raise TemplateDefinitionError(f"找不到 overlay {name!r}; 可用: {available}")
        for entry in overlay.get("definitions") or []:
            key = dimension_key(entry)
            base = merged.get(key)
            if base is None:
                raise TemplateDefinitionError(
                    f"overlay {name!r} 覆盖了不存在的维度 " f"{dimension_key_text(key)}"
                )
            merged[key] = merge_overlay(base, entry)
    return merged


def _load_all(
    overlay_names: List[str],
) -> Dict[DimensionKey, Dict[str, Any]]:
    definitions = load_definitions()
    return _apply_overlays(definitions, overlay_names)


def _validate_only(overlay_names: List[str]) -> int:
    """纯离线校验(不连数据库)。"""
    try:
        definitions = _load_all(overlay_names)
    except TemplateDefinitionError as exc:
        print(f"[ERROR] 定义校验失败: {exc}", file=sys.stderr)
        return 2

    if not definitions:
        print("[ERROR] 没有任何模板定义 —— templates/definitions 是空的")
        return 2

    print(f"[OK] 模板定义校验通过: {len(definitions)} 份定义")
    print(f"     决策字段: {list(DECISION_FIELDS)}")
    if overlay_names:
        print(f"     已叠加 overlay: {', '.join(overlay_names)}")
    return 0


async def _load_published() -> Dict[DimensionKey, Any]:
    from sqlalchemy import select

    from backend.models.database import AsyncSessionLocal
    from modules.core.db import FieldMappingTemplate

    async with AsyncSessionLocal() as db:
        rows = (
            (
                await db.execute(
                    select(FieldMappingTemplate).where(
                        FieldMappingTemplate.status == "published"
                    )
                )
            )
            .scalars()
            .all()
        )
        return {dimension_key(row): row for row in rows}


async def _check(overlay_names: List[str]) -> int:
    """连库比对「仓库定义」与「库内实例」。"""
    try:
        definitions = _load_all(overlay_names)
    except TemplateDefinitionError as exc:
        print(f"[ERROR] 定义加载失败: {exc}", file=sys.stderr)
        return 2

    published = await _load_published()

    mismatched: List[str] = []
    missing_in_db: List[str] = []
    matched = 0

    for key, payload in sorted(
        definitions.items(), key=lambda item: dimension_key_text(item[0])
    ):
        label = dimension_key_text(key)
        row = published.get(key)
        if row is None:
            missing_in_db.append(label)
            continue
        actual = decision_payload(row)
        differences = diff_decision_payload(payload, actual)
        if differences:
            mismatched.append(label)
            print(f"[DIFF] {label}")
            for line in differences:
                print(f"        - {line}")
        else:
            matched += 1

    extra_in_db = [
        dimension_key_text(key)
        for key in sorted(published, key=dimension_key_text)
        if key not in definitions
    ]

    print()
    print("=" * 72)
    print("模板决策资产差异检查(仓库定义 ↔ 库内 published 实例)")
    print("=" * 72)
    print(f"仓库定义      : {len(definitions)}")
    print(f"库内 published : {len(published)}")
    print(f"完全一致      : {matched}")
    print(f"存在差异      : {len(mismatched)}")
    print(f"仓库有库内缺  : {len(missing_in_db)}")
    print(f"库内有仓库缺  : {len(extra_in_db)}")
    if mismatched:
        print("\n-- 有差异的维度 --")
        for label in mismatched:
            print(f"  {label}")
    if missing_in_db:
        print("\n-- 仓库有、库内没有(需要 --apply 投影) --")
        for label in missing_in_db:
            print(f"  {label}")
    if extra_in_db:
        print("\n-- 库内有、仓库没有(库里多了模板, 需要导出或补定义) --")
        for label in extra_in_db:
            print(f"  {label}")

    if not (mismatched or missing_in_db or extra_in_db):
        print("\n[OK] 仓库定义与库内实例完全一致")
        return 0
    print(
        "\n[提示] 差异的处理方式:\n"
        "  * 库里改了、仓库没改 -> python scripts/export_template_definitions.py\n"
        "  * 仓库改了、库里没改 -> python scripts/apply_template_definitions.py --apply"
    )
    return 1


async def _sync_notes(db: Any, template_id: int, notes: Optional[str]) -> None:
    """把定义文件里的 ``notes`` 同步到库里(投影后单独补一步)。

    为什么需要单独一步
    ------------------
    :meth:`FieldMappingTemplateService.save_template` **不写 ``notes`` 列**
    (它的参数里压根没有 ``notes``) ⇒ 投影完库里的 notes 仍是旧版本的内容
    ⇒ 定义守卫 ``--check`` 永远报 notes 差异 ⇒ 守卫永远不绿。

    而 ``notes`` 在 :data:`scripts.template_definitions.DECISION_FIELDS` 里
    **参与比对** ⇒ 设计意图就是「notes 也要镜像」, 只是发布服务漏了这个参数。

    为什么不改 ``save_template``
    --------------------------
    那个服务是**界面发布路径**也在用的(归档旧版本 + 插入新版本 + 家族投影,
    同一个事务)。给它加参数会牵动界面发布的行为与事务边界。
    notes 只是**决策说明文字**, 不参与任何运行时口径
    (hash / 清单 / 漂移判定都不读它) ⇒ 用一条独立 UPDATE 补齐, 风险最小。

    只在定义里有 notes 时才写
    --------------------------
    定义里没写 notes ⇒ 可能是漏写, 不该顺手把库里的运维备注抹掉
    ⇒ 这种情况保持库内原值, 由差异守卫报出来交给人决定。

    调用时机
    ---------
    * 发布了新版本 ⇒ 跟着补新版本的 notes;
    * 差异**只有** notes ⇒ 原地补当前 published 模板的 notes, 不发新版本
      (见 :func:`_apply`)。
    """
    if notes is None:
        return

    from sqlalchemy import text

    await db.execute(
        text("UPDATE core.field_mapping_templates SET notes = :notes WHERE id = :id"),
        {"notes": notes, "id": template_id},
    )
    await db.commit()


async def _apply(overlay_names: List[str], dry_run: bool) -> int:
    """把定义投影到数据库(发布新版本)。"""
    from backend.models.database import AsyncSessionLocal
    from backend.services.field_mapping_template_service import (
        FieldMappingTemplateService,
    )

    try:
        definitions = _load_all(overlay_names)
    except TemplateDefinitionError as exc:
        print(f"[ERROR] 定义加载失败: {exc}", file=sys.stderr)
        return 2

    published = await _load_published()

    plans: List[Tuple[DimensionKey, Dict[str, Any], Any]] = []
    for key, payload in sorted(
        definitions.items(), key=lambda item: dimension_key_text(item[0])
    ):
        row = published.get(key)
        if row is None:
            plans.append((key, payload, None))
            continue
        differences = diff_decision_payload(payload, decision_payload(row))
        if differences:
            plans.append((key, payload, row))

    if not plans:
        print("[OK] 仓库定义与库内实例一致, 无需投影")
        return 0

    print(f"待投影维度: {len(plans)}")
    for key, payload, row in plans:
        label = dimension_key_text(key)
        if row is None:
            print(f"  [新建] {label}")
        else:
            print(f"  [更新] {label}  (库内 id={row.id} v={row.version})")
            for line in diff_decision_payload(payload, decision_payload(row)):
                print(f"          - {line}")

    if dry_run:
        print("\n[DRY-RUN] 未写入任何数据")
        return 0

    async with AsyncSessionLocal() as db:
        service = FieldMappingTemplateService(db)
        for key, payload, row in plans:
            label = dimension_key_text(key)
            if row is not None and changed_decision_fields(
                payload, decision_payload(row)
            ) == ["notes"]:
                # 只差「说明文字」⇒ 原地补 notes, **不发布新版本**。
                # notes 不参与任何运行时口径(hash / 清单 / 漂移判定都不读它),
                # 为它发一个新版本只会让版本号无意义地膨胀。
                await _sync_notes(db, int(row.id), payload.get("notes"))
                print(
                    f"[OK] 已同步 notes: {label} "
                    f"(库内 id={row.id} v={row.version}, 未发布新版本)"
                )
                continue
            result = await service.save_template(
                platform=payload["platform"],
                data_domain=payload["data_domain"],
                header_columns=list(payload.get("header_columns") or []),
                granularity=payload.get("granularity"),
                account=payload.get("account"),
                created_by="git_definition",
                header_row=int(payload.get("header_row") or 0),
                sub_domain=payload.get("sub_domain"),
                sheet_name=payload.get("sheet_name"),
                encoding=payload.get("encoding") or "utf-8",
                deduplication_fields=list(payload.get("deduplication_fields") or [])
                or None,
                header_bindings=list(payload.get("header_bindings") or []),
                field_parse_rules=list(payload.get("field_parse_rules") or []),
                core_fields=list(payload.get("core_fields") or []),
                ignored_extra_fields=list(payload.get("ignored_extra_fields") or []),
                save_mode="new_version",
                base_template_id=getattr(row, "id", None),
            )
            print(f"[OK] 已投影 {label}: {result}")
            await _sync_notes(db, int(result["template_id"]), payload.get("notes"))

    print("\n投影完成。可以用 --check 复验。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="模板决策资产: 校验 / 差异守卫 / 投影")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="只校验定义文件(纯离线, 不连数据库; CI 用)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="比对仓库定义与库内实例, 有差异则退出码 1",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="把定义投影到数据库(发布新版本)",
    )
    parser.add_argument(
        "--overlay",
        action="append",
        default=[],
        help="叠加指定 overlay(可重复); overlay 目录: templates/overlays",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="配合 --apply: 只打印投影计划, 不写库",
    )
    args = parser.parse_args()

    if not (args.validate_only or args.check or args.apply):
        parser.error("至少要指定 --validate-only / --check / --apply 之一")

    from backend.utils.project_env import load_project_env

    load_project_env(REPO_ROOT)

    try:
        if args.validate_only:
            return _validate_only(args.overlay)
        if args.check:
            return asyncio.run(_check(args.overlay))
        return asyncio.run(_apply(args.overlay, args.dry_run))
    except TemplateDefinitionError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
