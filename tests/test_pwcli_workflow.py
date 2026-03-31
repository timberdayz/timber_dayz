from pathlib import Path

from scripts.pwcli_workflow import (
    build_capture_paths,
    build_note_path,
    build_pack_manifest,
    build_step_snapshot_path,
    build_work_dir,
    validate_work_package,
    write_pack_manifest,
)


def test_build_work_dir_uses_platform_and_work_tag(tmp_path: Path):
    result = build_work_dir(
        repo_root=tmp_path,
        platform="miaoshou",
        work_tag="login",
    )

    assert result == tmp_path / "output" / "playwright" / "work" / "miaoshou" / "login"


def test_build_step_snapshot_path_formats_step_name_and_phase(tmp_path: Path):
    path = build_step_snapshot_path(
        work_dir=tmp_path,
        step="01",
        name="submit-login",
        phase="before",
    )

    assert path.name == "01-submit-login-before.md"


def test_build_note_path_uses_step_prefix(tmp_path: Path):
    path = build_note_path(work_dir=tmp_path, step="04")

    assert path.name == "04-note.md"


def test_build_capture_paths_reuses_name_for_snapshot_and_screenshot(tmp_path: Path):
    snapshot_path, screenshot_path = build_capture_paths(
        work_dir=tmp_path,
        name="09-date-picker-open",
    )

    assert snapshot_path.name == "09-date-picker-open.md"
    assert screenshot_path.name == "09-date-picker-open.png"


def test_validate_work_package_requires_before_after_pairs(tmp_path: Path):
    (tmp_path / "01-open-login-before.md").write_text("before", encoding="utf-8")

    report = validate_work_package(tmp_path)

    assert report["ok"] is False
    assert "missing after snapshot" in " ".join(report["errors"]).lower()


def test_build_pack_manifest_sorts_steps_and_includes_notes(tmp_path: Path):
    (tmp_path / "02-submit-login-after.md").write_text("after-2", encoding="utf-8")
    (tmp_path / "02-submit-login-before.md").write_text("before-2", encoding="utf-8")
    (tmp_path / "02-note.md").write_text("action=click 登录按钮", encoding="utf-8")
    (tmp_path / "01-open-login-after.md").write_text("after-1", encoding="utf-8")
    (tmp_path / "01-open-login-before.md").write_text("before-1", encoding="utf-8")
    (tmp_path / "02-captcha-visible.png").write_bytes(b"png")

    manifest = build_pack_manifest(
        tmp_path,
        platform="miaoshou",
        work_tag="login",
    )

    assert manifest["platform"] == "miaoshou"
    assert manifest["work_tag"] == "login"
    assert [step["step"] for step in manifest["steps"]] == ["01", "02"]
    assert manifest["steps"][1]["note_path"].endswith("02-note.md")
    assert manifest["steps"][1]["screenshots"][0].endswith("02-captcha-visible.png")


def test_write_pack_manifest_creates_evidence_pack_file(tmp_path: Path):
    (tmp_path / "01-open-login-before.md").write_text("before", encoding="utf-8")
    (tmp_path / "01-open-login-after.md").write_text("after", encoding="utf-8")

    output = write_pack_manifest(
        tmp_path,
        platform="miaoshou",
        work_tag="login",
    )

    assert output.name == "evidence-pack.json"
    assert output.exists()


def test_validate_work_package_still_recognizes_legacy_txt_files(tmp_path: Path):
    (tmp_path / "01-open-login-before.txt").write_text("before", encoding="utf-8")
    (tmp_path / "01-open-login-after.txt").write_text("after", encoding="utf-8")

    report = validate_work_package(tmp_path)

    assert report["ok"] is True
    assert report["errors"] == []


def test_build_pack_manifest_fills_step_name_even_when_note_is_scanned_first(tmp_path: Path):
    (tmp_path / "01-note.md").write_text("expected=login_success", encoding="utf-8")
    (tmp_path / "01-open-login-before.md").write_text("before", encoding="utf-8")
    (tmp_path / "01-open-login-after.md").write_text("after", encoding="utf-8")

    manifest = build_pack_manifest(
        tmp_path,
        platform="miaoshou",
        work_tag="login",
    )

    assert manifest["steps"][0]["name"] == "open-login"
