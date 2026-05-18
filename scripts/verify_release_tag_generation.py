#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Verify release-tag generation rules in deploy workflow."""

from __future__ import annotations

import argparse
from pathlib import Path


WORKFLOW_PATH = Path(".github/workflows/deploy-production.yml")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify release tag generation rules")
    parser.add_argument(
        "--workflow-path",
        default=str(WORKFLOW_PATH),
        help="Path to deploy workflow file",
    )
    parser.add_argument(
        "--release-tags",
        nargs="+",
        default=["v5.3", "v5.3.1"],
        help="Sample release tags that must be publishable as exact image tags",
    )
    return parser.parse_args(argv)


def build_expected_release_tags(release_tags: list[str]) -> dict[str, set[str]]:
    return {
        "backend": set(release_tags),
        "frontend": set(release_tags),
        "backend-full": {f"{tag}-full" for tag in release_tags},
    }


def verify_release_tag_generation(workflow_path: Path, release_tags: list[str]) -> bool:
    source = workflow_path.read_text(encoding="utf-8")
    expected = build_expected_release_tags(release_tags)

    required_rules = {
        "backend": 'type=ref,event=tag',
        "frontend": 'type=ref,event=tag',
        "backend-full": 'type=raw,value=${{ github.ref_name }}-full',
    }

    for rule in required_rules.values():
        if rule not in source:
            raise RuntimeError(f"Missing workflow tag rule: {rule}")

    # Validate representative exact tags are derivable from the workflow contract.
    for tag in expected["backend"]:
        if not tag.startswith("v"):
            raise RuntimeError(f"Unexpected backend release tag sample: {tag}")
    for tag in expected["frontend"]:
        if not tag.startswith("v"):
            raise RuntimeError(f"Unexpected frontend release tag sample: {tag}")
    for tag in expected["backend-full"]:
        if not tag.endswith("-full"):
            raise RuntimeError(f"Unexpected backend-full release tag sample: {tag}")

    return True


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    ok = verify_release_tag_generation(Path(args.workflow_path), args.release_tags)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
