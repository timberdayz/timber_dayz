from pathlib import Path

from modules.utils.sessions.device_fingerprint import DeviceFingerprintManager
from modules.utils.sessions.legacy_shop_artifact_cleanup import (
    ShopSessionScope,
    collect_legacy_shop_artifact_paths,
)


def test_collect_legacy_shop_artifact_paths_only_returns_shop_scoped_artifacts(tmp_path: Path):
    root = tmp_path

    # Shop-scoped legacy artifacts that should be cleaned.
    targets = [
        root / "profiles" / "shopee" / "shopee_sg_chenewei666_local",
        root / "data" / "session_profiles" / "shopee" / "shopee_sg_chenewei666_local",
    ]
    for target in targets:
        target.mkdir(parents=True, exist_ok=True)

    # 会话文件目录（data/sessions/**）已随会话文件体系整体废除：新代码根本不读它，
    # 所以它不再是「会被误用的店铺级遗留物」——留着只会让运维去删一批无害文件。
    retired_session_dir = root / "data" / "sessions" / "shopee" / "shopee_sg_chenewei666_local"
    retired_session_dir.mkdir(parents=True, exist_ok=True)

    fingerprint_manager = DeviceFingerprintManager(base_path=root / "data" / "device_fingerprints")
    fingerprint_file = fingerprint_manager.get_fingerprint_file(
        "shopee",
        "shopee_sg_chenewei666_local",
    )
    fingerprint_file.write_text("{}", encoding="utf-8")

    # Main-account artifacts with identical main/shop IDs should not be treated as legacy.
    keep_dir = root / "data" / "sessions" / "miaoshou" / "miaoshou_real_001"
    keep_dir.mkdir(parents=True, exist_ok=True)

    scopes = [
        ShopSessionScope(
            platform="shopee",
            shop_account_id="shopee_sg_chenewei666_local",
            main_account_id="chenewei666:main",
        ),
        ShopSessionScope(
            platform="miaoshou",
            shop_account_id="miaoshou_real_001",
            main_account_id="miaoshou_real_001",
        ),
    ]

    actual = collect_legacy_shop_artifact_paths(root, scopes)

    assert actual == sorted(targets + [fingerprint_file])
    # 会话文件目录不再被当作「需要清理的店铺级遗留物」
    assert retired_session_dir not in actual
    assert keep_dir not in actual


def test_collect_legacy_shop_artifact_paths_ignores_missing_artifacts(tmp_path: Path):
    scopes = [
        ShopSessionScope(
            platform="tiktok",
            shop_account_id="tiktok_sg_hx_home_local",
            main_account_id="chenzeweinbnb@163.com",
        )
    ]

    assert collect_legacy_shop_artifact_paths(tmp_path, scopes) == []
