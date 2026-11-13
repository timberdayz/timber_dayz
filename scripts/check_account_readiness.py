"""新增账号前置检查（只读）。

为什么需要它
------------
「新增一个可用账号」在系统里是**三步**，而不是一步：

1. 建号（账号管理页 / API）
2. 建店铺账号
3. **人工首登一次** —— profile 从无到有，登录态才成立

第 3 步没有任何界面提示，于是「建完号」看起来像"配好了"，实际第一次采集才暴露问题。
本脚本把这三步的**前置条件**一次性检查出来，避免"建完才发现不撞车/不在白名单/没首登"。

检查项
------
| # | 检查 | 依据 |
|---|---|---|
| 1 | 主账号 ID 规范 | 只允许小写字母 / 数字 / 下划线；不含空格、冒号、邮箱、中文、括号 |
| 2 | profile 目录**不撞车** | 目录名 = ID 净化结果；撞车 ⇒ 两个账号共用一份登录态 |
| 3 | 平台在巡店白名单 | `{miaoshou, shopee, tiktok}`；否则巡店面板**静默跳过** |
| 4 | 设备画像已分配 | `profiles/<平台>/<账号>/.device_profile.json` |
| 5 | `machine_id` 已隔离 | profile 内 `Local State` 的 `user_experience_metrics.machine_id` |
| 6 | 已人工首登 | profile 内存在 Chromium 的 cookie 库（与采集侧同一判据） |
| 7 | 出口 IP 已配置 | 主账号级 `extra_config['proxy']` 优先（**提示项**，当前未强制） |

用法
----
```powershell
# 体检一个已存在的账号
python scripts/check_account_readiness.py --platform shopee --account-id hongxikeji:main

# 检查一个**还没建**的候选 ID（只查 1/2/3 项）
python scripts/check_account_readiness.py --candidate-id my_new_acc --platform shopee

# 体检全部主账号
python scripts/check_account_readiness.py --all
```

**只读**：不写库、不写盘、不改任何 profile。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


#: 巡店面板支持的平台（与 ``scripts/pwcli_account_inventory.py`` 的 PLATFORM_HELPERS 一致）
INSPECTION_PLATFORMS = {"miaoshou", "shopee", "tiktok"}

#: 主账号 ID 允许的字符：小写字母 / 数字 / 下划线
ID_ALLOWED_RE = re.compile(r"^[a-z0-9_]+$")

#: 明确禁止出现的字符（会破坏目录名 / 指纹 key / 编码）
ID_FORBIDDEN_HINTS = (
    (" ", "含空格 ⇒ 目录名会被去掉空格，容易与别的账号撞车"),
    (":", "含冒号 ⇒ 目录名会被去掉冒号"),
    ("@", "含 @ ⇒ 目录名会被去掉 @"),
    ("（", "含全角括号 ⇒ 编码在部分链路会被误解码"),
    (".", "含点 ⇒ 与旧的历史目录命名混淆"),
)


OK = "OK"
WARN = "WARN"
FAIL = "FAIL"


class Check:
    __slots__ = ("status", "title", "detail")

    def __init__(self, status: str, title: str, detail: str = "") -> None:
        self.status = status
        self.title = title
        self.detail = detail


def _profile_dir(platform: str, account_id: str) -> Path:
    """profile 目录 —— 与系统唯一命名规则同源。"""
    from modules.utils.sessions.session_manager import SessionManager

    return SessionManager().get_persistent_profile_path(platform, account_id)


def check_id_format(account_id: str, *, existing: bool) -> Check:
    """ID 规范。

    存量账号用 WARN：ID 已经定型，重命名会连带换掉 profile 目录与登录态，
    属于「历史事实」而不是「故障」；但新建账号必须一次遵守（候选模式判 FAIL）。
    """
    text = str(account_id or "").strip()
    if not text:
        return Check(FAIL, "主账号 ID 规范", "ID 为空")
    if not ID_ALLOWED_RE.match(text):
        hints = [
            f"{ch!r}：{why}"
            for ch, why in ID_FORBIDDEN_HINTS
            if ch in text
        ]
        detail = "只允许小写字母 / 数字 / 下划线"
        if hints:
            detail += "；" + "；".join(hints)
        if existing:
            detail += "。存量账号：改名会换掉 profile 目录与登录态，先记录为技术债"
            return Check(WARN, "主账号 ID 规范", detail)
        return Check(FAIL, "主账号 ID 规范", detail)
    return Check(OK, "主账号 ID 规范", text)


def sanitized_dir_name(account_id: str) -> str:
    """profile 目录名 —— 与 ``session_manager.get_persistent_profile_path`` 同源规则。

    规则 B：``profiles/<平台>/<主账号ID净化后>``；净化 = 只保留字母/数字/下划线/连字符。
    """
    return "".join(c for c in str(account_id) if c.isalnum() or c in "_-")


def check_profile_collision(
    database_url: str,
    platform: str,
    account_id: str,
    *,
    existing: bool,
) -> Check:
    """profile 目录**真实撞车**检查。

    两种语义，判据不同：

    - 候选模式（``existing=False``）：目标目录已存在 ⇒ 新账号会与它共用一份登录态 ⇒ FAIL。
    - 体检模式（``existing=True``）：本账号的目录**本来就该存在**（它就是登录态载体）。
      真正的风险是**另一个主账号净化后落到同一目录** ⇒ 两个账号共用一份登录态 ⇒ FAIL。
    """
    target_name = sanitized_dir_name(account_id)

    if not existing:
        profiles_root = PROJECT_ROOT / "profiles"
        platform_dir = profiles_root / str(platform).lower()
        if platform_dir.exists() and (platform_dir / target_name).is_dir():
            return Check(
                FAIL,
                "profile 目录不撞车",
                f"目录名 {target_name!r} 已存在 ⇒ 新账号会与它**共用同一份登录态**。"
                f"请换一个 ID（当前规则：去掉空格/冒号/@/括号后得到的目录名）",
            )
        return Check(OK, "profile 目录不撞车", target_name)

    # 体检模式：和同平台其它主账号比目录名
    others = list_platform_accounts(database_url, platform)
    collided = [
        other
        for other in others
        if other != account_id and sanitized_dir_name(other) == target_name
    ]
    if collided:
        return Check(
            FAIL,
            "profile 目录不撞车",
            f"目录名 {target_name!r} 同时被 {collided} 使用 ⇒ "
            f"这些账号**共用同一份登录态**（同一浏览器 profile）",
        )
    return Check(OK, "profile 目录不撞车", target_name)


def check_platform(platform: str) -> Check:
    if platform in INSPECTION_PLATFORMS:
        return Check(OK, "平台在巡店白名单", platform)
    return Check(
        FAIL,
        "平台在巡店白名单",
        f"{platform!r} 不在 {sorted(INSPECTION_PLATFORMS)} 内 ⇒ "
        f"该账号**不会**出现在 PWCLI 本地巡店面板（面板静默跳过，零提示）",
    )


def _profile_state(platform: str, account_id: str) -> dict:
    """profile 只读快照 —— 判据真源在 ``modules/utils/sessions/account_readiness.py``。

    巡店面板的 ``/api/accounts/readiness`` 用的是**同一份** ⇒ 面板与体检不会各说各话。
    """
    from modules.utils.sessions.account_readiness import build_profile_state

    return build_profile_state(_profile_dir(platform, account_id), platform=platform, account_id=account_id)


def check_device_profile(platform: str, account_id: str) -> Check:
    state = _profile_state(platform, account_id)
    if not state["has_device_profile"]:
        return Check(
            WARN,
            "设备画像已分配",
            "尚无 .device_profile.json ⇒ 采集路径**不注入画像**（走 profile 原生环境，"
            "与其它账号撞指纹）；首次**巡店**启动时会自动分配（账号内稳定、账号间不同）",
        )
    device = state.get("device") or {}
    viewport = device.get("viewport") or {}
    return Check(
        OK,
        "设备画像已分配",
        f"{device.get('os')}/{device.get('browser')} {device.get('browser_version')} · "
        f"{device.get('locale')} · {device.get('timezone_id')} · "
        f"{viewport.get('width')}x{viewport.get('height')}",
    )


def check_machine_id(platform: str, account_id: str) -> Check:
    state = _profile_state(platform, account_id)
    current = str(state.get("machine_id") or "")
    expected = str(state.get("expected_machine_id") or "")

    if state["machine_id_isolated"]:
        return Check(OK, "machine_id 已隔离", current)
    if not state["profile_exists"]:
        return Check(
            WARN,
            "machine_id 已隔离",
            "profile 目录还不存在 ⇒ 首次巡店/采集时会自动隔离",
        )
    if not current:
        return Check(
            WARN,
            "machine_id 已隔离",
            "Local State 里没有 machine_id ⇒ 首次巡店/采集时会写入账号专属值",
        )
    return Check(
        WARN,
        "machine_id 已隔离",
        f"当前 {current} ≠ 账号专属值 {expected} ⇒ 下次巡店/采集会自动改写。"
        f"注意：改写前该 profile 与其它同机账号共享 machine_id",
    )


def check_login_state(platform: str, account_id: str) -> Check:
    """是否已人工首登 —— 与采集侧**同一判据**（单一来源）。"""
    state = _profile_state(platform, account_id)
    if not state["profile_exists"]:
        return Check(
            WARN,
            "已人工首登",
            "profile 目录还不存在 ⇒ 请先通过巡店面板打开一次并登录",
        )
    if state["logged_in"]:
        return Check(OK, "已人工首登", "profile 内已有 Chromium cookie 库")
    return Check(
        WARN,
        "已人工首登",
        "profile 内没有 cookie 库 ⇒ 尚未登录成功（Chromium 启动过但没登进去不算）",
    )


def check_proxy(database_url: str, platform: str, account_id: str) -> Check:
    """出口 IP —— 提示项（当前不做强制）。"""
    import sqlalchemy as sa

    from backend.services.account_proxy_config import extract_proxy_config

    engine = sa.create_engine(database_url)
    with engine.connect() as conn:
        row = conn.execute(
            sa.text(
                """
                select m.extra_config as main_extra_config
                from core.main_accounts m
                where m.platform = :platform and m.main_account_id = :account_id
                """
            ),
            {"platform": platform, "account_id": account_id},
        ).fetchone()

    if row is None:
        return Check(WARN, "出口 IP 已配置", "库里查不到该主账号")

    proxy = extract_proxy_config(row.main_extra_config)
    if proxy.get("proxy_enabled") and proxy.get("proxy_server"):
        return Check(OK, "出口 IP 已配置", proxy.get("proxy_server"))
    return Check(
        WARN,
        "出口 IP 已配置",
        "主账号级 extra_config['proxy'] 未配置 ⇒ 该账号与其它账号**共用同一个出口 IP**。"
        "当前不强制，但平台可据此关联账号矩阵（同一出口多账号）",
    )


def run_checks(
    database_url: str,
    platform: str,
    account_id: str,
    *,
    include_runtime: bool = True,
) -> List[Check]:
    checks: List[Check] = [
        check_id_format(account_id, existing=True),
        check_platform(platform),
    ]
    if include_runtime:
        checks.append(
            check_profile_collision(database_url, platform, account_id, existing=True)
        )
        checks.append(check_device_profile(platform, account_id))
        checks.append(check_machine_id(platform, account_id))
        checks.append(check_login_state(platform, account_id))
        checks.append(check_proxy(database_url, platform, account_id))
    return checks


def _print_checks(title: str, checks: List[Check]) -> bool:
    print(f"\n=== {title} ===")
    for check in checks:
        mark = {OK: "[OK]", WARN: "[WARN]", FAIL: "[FAIL]"}.get(check.status, "[?]")
        line = f"{mark} {check.title}"
        if check.detail:
            line += f" —— {check.detail}"
        print(line)
    return all(check.status != FAIL for check in checks)


def list_all_accounts(database_url: str) -> List[Tuple[str, str]]:
    import sqlalchemy as sa

    engine = sa.create_engine(database_url)
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                """
                select platform, main_account_id
                from core.main_accounts
                order by platform, main_account_id
                """
            )
        ).fetchall()
    return [(str(row[0]), str(row[1])) for row in rows]


def list_platform_accounts(database_url: str, platform: str) -> List[str]:
    """同平台其它主账号 ID —— 用于检测**真实目录撞车**。"""
    import sqlalchemy as sa

    engine = sa.create_engine(database_url)
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                """
                select main_account_id
                from core.main_accounts
                where platform = :platform
                """
            ),
            {"platform": platform},
        ).fetchall()
    return [str(row[0]) for row in rows]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_account_readiness",
        description="新增账号前置检查（只读，不写库不写盘）",
    )
    parser.add_argument("--platform", help="平台代码（miaoshou / shopee / tiktok）")
    parser.add_argument("--account-id", help="已存在的主账号 ID")
    parser.add_argument(
        "--candidate-id",
        help="还没建的候选 ID（只检查 ID 规范 / 目录撞车 / 平台白名单）",
    )
    parser.add_argument("--all", action="store_true", help="体检全部主账号")
    parser.add_argument(
        "--database-url",
        default=os.getenv(
            "DATABASE_URL",
            "postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp",
        ),
        help="数据库连接串（默认取 DATABASE_URL）",
    )
    args = parser.parse_args(argv)

    if not args.all and not args.candidate_id and not args.account_id:
        parser.error("必须给 --account-id / --candidate-id / --all 其中之一")

    if args.candidate_id:
        if not args.platform:
            parser.error("--candidate-id 需要配合 --platform")
        checks = [
            check_id_format(args.candidate_id, existing=False),
            check_platform(args.platform),
            check_profile_collision(
                args.database_url, args.platform, args.candidate_id, existing=False
            ),
        ]
        # 库里已有账号也可能已经占了这个目录名（它还没建过 profile 时磁盘上看不出来）
        for other in list_platform_accounts(args.database_url, args.platform):
            if other == args.candidate_id:
                continue
            if sanitized_dir_name(other) == sanitized_dir_name(args.candidate_id):
                checks.append(
                    Check(
                        FAIL,
                        "profile 目录不撞车",
                        f"目录名与现有账号 {other!r} 相同 ⇒ 会**共用同一份登录态**",
                    )
                )
                break
        ok = _print_checks(
            f"候选 ID 检查（platform={args.platform}, id={args.candidate_id}）", checks
        )
        print()
        print("下一步：账号管理页建号 → 建店铺账号 → 巡店面板人工首登一次")
        return 0 if ok else 1

    if args.account_id:
        if not args.platform:
            parser.error("--account-id 需要配合 --platform")
        checks = run_checks(args.database_url, args.platform, args.account_id)
        ok = _print_checks(
            f"账号就绪检查（platform={args.platform}, id={args.account_id}）", checks
        )
        return 0 if ok else 1

    # --all
    accounts = list_all_accounts(args.database_url)
    print(f"共 {len(accounts)} 个主账号")
    failed = 0
    for platform, account_id in accounts:
        checks = run_checks(args.database_url, platform, account_id)
        ok = _print_checks(f"{platform} / {account_id}", checks)
        if not ok:
            failed += 1
    print()
    print(f"体检完成：{len(accounts)} 个账号，其中 {failed} 个有 FAIL")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
