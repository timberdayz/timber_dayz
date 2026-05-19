#!/usr/bin/env python3
"""
CI gate for Safety JSON reports.

Goal: keep CI actionable without being blocked forever by historical backlog.

Policy:
- For pull requests, compare base vs head Safety reports and FAIL only when
  *new* vulnerabilities are introduced (by vulnerability_id + package_name).
- For push builds (no base report), this script can be run in report-only mode.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FindingKey:
    vulnerability_id: str
    package_name: str


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Failed to parse JSON: {path}: {exc}") from exc


def _extract_findings(payload: dict) -> dict[FindingKey, dict]:
    findings: dict[FindingKey, dict] = {}
    for item in payload.get("vulnerabilities") or []:
        vid = str(item.get("vulnerability_id", "")).strip()
        pkg = str(item.get("package_name", "")).strip()
        if not vid or not pkg:
            continue
        findings[FindingKey(vid, pkg)] = item
    return findings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gate CI based on Safety JSON diff")
    parser.add_argument("head_report", help="Path to head safety-report.json")
    parser.add_argument(
        "--base-report",
        default=None,
        help="Optional path to base safety-report.json (for PR diff gating).",
    )
    parser.add_argument(
        "--fail-on-new",
        action="store_true",
        help="Fail when new vulnerabilities are introduced (requires --base-report).",
    )
    parser.add_argument(
        "--max-print",
        type=int,
        default=30,
        help="Max findings to print in the summary (default: 30).",
    )
    return parser.parse_args()


def _print_item(prefix: str, item: dict) -> None:
    vid = item.get("vulnerability_id", "")
    pkg = item.get("package_name", "")
    cve = item.get("CVE") or ""
    spec = item.get("vulnerable_spec") or item.get("all_vulnerable_specs") or []
    spec_s = ",".join(str(x) for x in (spec if isinstance(spec, list) else [spec]))[
        :120
    ]
    analyzed = item.get("analyzed_version") or ""
    print(f"- {prefix} {pkg} {analyzed} vid={vid} {cve} spec={spec_s}".strip())


def main() -> int:
    args = parse_args()
    head_path = Path(args.head_report)
    if not head_path.exists():
        print(f"[ERROR] Head Safety report not found: {head_path}")
        return 2

    head_payload = _load_json(head_path)
    head_findings = _extract_findings(head_payload)

    base_findings: dict[FindingKey, dict] = {}
    if args.base_report:
        base_path = Path(args.base_report)
        if not base_path.exists():
            print(f"[ERROR] Base Safety report not found: {base_path}")
            return 2
        base_payload = _load_json(base_path)
        base_findings = _extract_findings(base_payload)

    new_keys = sorted(
        set(head_findings.keys()) - set(base_findings.keys()),
        key=lambda k: (k.package_name, k.vulnerability_id),
    )

    print(
        "[INFO] Safety findings:"
        f" head={len(head_findings)} base={len(base_findings)} new={len(new_keys)}"
    )

    if new_keys:
        print("[INFO] New vulnerabilities introduced (showing up to max-print):")
        for key in new_keys[: max(args.max_print, 0)]:
            _print_item("NEW", head_findings[key])

    if args.fail_on_new:
        if not args.base_report:
            print("[ERROR] --fail-on-new requires --base-report")
            return 2
        if new_keys:
            print("[ERROR] Safety gate failed: new vulnerabilities introduced.")
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
