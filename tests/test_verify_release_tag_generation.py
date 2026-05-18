from pathlib import Path

from scripts.verify_release_tag_generation import (
    build_expected_release_tags,
    main,
    parse_args,
    verify_release_tag_generation,
)


def test_parse_args_accepts_release_tags():
    args = parse_args(["--release-tags", "v5.3", "v5.3.1"])

    assert args.release_tags == ["v5.3", "v5.3.1"]


def test_build_expected_release_tags_includes_full_variant():
    expected = build_expected_release_tags(["v5.3", "v5.3.1"])

    assert expected["backend"] == {"v5.3", "v5.3.1"}
    assert expected["frontend"] == {"v5.3", "v5.3.1"}
    assert expected["backend-full"] == {"v5.3-full", "v5.3.1-full"}


def test_verify_release_tag_generation_reads_workflow_contract():
    workflow = Path(".github/workflows/deploy-production.yml")

    assert verify_release_tag_generation(workflow, ["v5.3", "v5.3.1"]) is True


def test_main_returns_zero_for_current_workflow():
    code = main([])
    assert code == 0
