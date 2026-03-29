from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SNAPSHOT_RE = re.compile(r"^(?P<step>\d+)-(?P<name>.+)-(?P<phase>before|after)\.(md|txt)$", re.IGNORECASE)
NOTE_RE = re.compile(r"^(?P<step>\d+)-note\.(md|txt)$", re.IGNORECASE)
SCREENSHOT_RE = re.compile(r"^(?P<step>\d+)-(?P<name>.+)\.(png|jpg|jpeg)$", re.IGNORECASE)


def sanitize_token(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "").strip().lower())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return cleaned or "unknown"


def normalize_step_id(step: str | int) -> str:
    if isinstance(step, int):
        return f"{step:02d}"
    raw = str(step or "").strip()
    if raw.isdigit():
        return raw.zfill(2)
    return raw


def normalize_step_name(name: str) -> str:
    return sanitize_token(name)


def build_work_dir(repo_root: Path, platform: str, work_tag: str) -> Path:
    return repo_root / "output" / "playwright" / "work" / sanitize_token(platform) / sanitize_token(work_tag)


def build_session_name(platform: str, work_tag: str) -> str:
    return f"{sanitize_token(platform)}-{sanitize_token(work_tag)}"


def build_step_snapshot_path(work_dir: Path, step: str | int, name: str, phase: str) -> Path:
    norm_phase = str(phase or "").strip().lower()
    if norm_phase not in {"before", "after"}:
        raise ValueError(f"Unsupported phase: {phase}")
    return work_dir / f"{normalize_step_id(step)}-{normalize_step_name(name)}-{norm_phase}.md"


def build_note_path(work_dir: Path, step: str | int) -> Path:
    return work_dir / f"{normalize_step_id(step)}-note.md"


def build_screenshot_path(work_dir: Path, step: str | int, name: str, ext: str = "png") -> Path:
    suffix = str(ext or "png").lstrip(".").lower()
    return work_dir / f"{normalize_step_id(step)}-{normalize_step_name(name)}.{suffix}"


def scan_work_dir(work_dir: Path) -> dict[str, Any]:
    steps: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []

    for path in sorted(work_dir.iterdir()):
        if not path.is_file():
            continue
        if path.name == "evidence-pack.json":
            continue

        snapshot_match = SNAPSHOT_RE.match(path.name)
        if snapshot_match:
            step = snapshot_match.group("step")
            info = steps.setdefault(
                step,
                {
                    "step": step,
                    "name": snapshot_match.group("name"),
                    "before_path": None,
                    "after_path": None,
                    "note_path": None,
                    "screenshots": [],
                },
            )
            if not info.get("name"):
                info["name"] = snapshot_match.group("name")
            info[f"{snapshot_match.group('phase')}_path"] = str(path)
            continue

        note_match = NOTE_RE.match(path.name)
        if note_match:
            step = note_match.group("step")
            info = steps.setdefault(
                step,
                {
                    "step": step,
                    "name": None,
                    "before_path": None,
                    "after_path": None,
                    "note_path": None,
                    "screenshots": [],
                },
            )
            info["note_path"] = str(path)
            continue

        screenshot_match = SCREENSHOT_RE.match(path.name)
        if screenshot_match:
            step = screenshot_match.group("step")
            info = steps.setdefault(
                step,
                {
                    "step": step,
                    "name": screenshot_match.group("name"),
                    "before_path": None,
                    "after_path": None,
                    "note_path": None,
                    "screenshots": [],
                },
            )
            if not info.get("name"):
                info["name"] = screenshot_match.group("name")
            info["screenshots"].append(str(path))
            continue

        warnings.append(f"Unrecognized evidence file: {path.name}")

    ordered_steps = sorted(steps.values(), key=lambda item: (int(item["step"]), item.get("name") or ""))
    return {
        "work_dir": str(work_dir),
        "steps": ordered_steps,
        "warnings": warnings,
    }


def validate_work_package(work_dir: Path) -> dict[str, Any]:
    scanned = scan_work_dir(work_dir)
    errors: list[str] = []
    warnings = list(scanned["warnings"])

    for step in scanned["steps"]:
        step_id = step["step"]
        if step["before_path"] and not step["after_path"]:
            errors.append(f"Step {step_id} missing after snapshot")
        if step["after_path"] and not step["before_path"]:
            errors.append(f"Step {step_id} missing before snapshot")
        if not step["name"] and (step["before_path"] or step["after_path"]):
            warnings.append(f"Step {step_id} has snapshots but missing inferred step name")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "steps": scanned["steps"],
    }


def build_pack_manifest(work_dir: Path, *, platform: str | None = None, work_tag: str | None = None) -> dict[str, Any]:
    validation = validate_work_package(work_dir)
    return {
        "platform": platform,
        "work_tag": work_tag,
        "work_dir": str(work_dir),
        "ok": validation["ok"],
        "errors": validation["errors"],
        "warnings": validation["warnings"],
        "steps": validation["steps"],
    }


def write_pack_manifest(work_dir: Path, *, platform: str | None = None, work_tag: str | None = None) -> Path:
    manifest = build_pack_manifest(work_dir, platform=platform, work_tag=work_tag)
    output = work_dir / "evidence-pack.json"
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="pwcli workflow helper")
    sub = parser.add_subparsers(dest="command", required=True)

    work_dir = sub.add_parser("work-dir", help="print normalized work dir")
    work_dir.add_argument("--repo-root", required=True)
    work_dir.add_argument("--platform", required=True)
    work_dir.add_argument("--work-tag", required=True)

    session = sub.add_parser("session-name", help="print normalized session name")
    session.add_argument("--platform", required=True)
    session.add_argument("--work-tag", required=True)

    snapshot = sub.add_parser("snapshot-path", help="print normalized snapshot path")
    snapshot.add_argument("--work-dir", required=True)
    snapshot.add_argument("--step", required=True)
    snapshot.add_argument("--name", required=True)
    snapshot.add_argument("--phase", required=True)

    note = sub.add_parser("note-path", help="print normalized note path")
    note.add_argument("--work-dir", required=True)
    note.add_argument("--step", required=True)

    shot = sub.add_parser("screenshot-path", help="print normalized screenshot path")
    shot.add_argument("--work-dir", required=True)
    shot.add_argument("--step", required=True)
    shot.add_argument("--name", required=True)
    shot.add_argument("--ext", default="png")

    pack = sub.add_parser("pack", help="validate a work dir and write evidence-pack.json")
    pack.add_argument("--work-dir", required=True)
    pack.add_argument("--platform")
    pack.add_argument("--work-tag")

    return parser


def main() -> int:
    parser = _build_cli()
    args = parser.parse_args()

    if args.command == "work-dir":
        print(build_work_dir(Path(args.repo_root), args.platform, args.work_tag))
        return 0

    if args.command == "session-name":
        print(build_session_name(args.platform, args.work_tag))
        return 0

    if args.command == "snapshot-path":
        print(build_step_snapshot_path(Path(args.work_dir), args.step, args.name, args.phase))
        return 0

    if args.command == "note-path":
        print(build_note_path(Path(args.work_dir), args.step))
        return 0

    if args.command == "screenshot-path":
        print(build_screenshot_path(Path(args.work_dir), args.step, args.name, args.ext))
        return 0

    if args.command == "pack":
        work_dir = Path(args.work_dir)
        output = write_pack_manifest(
            work_dir,
            platform=args.platform,
            work_tag=args.work_tag,
        )
        manifest = json.loads(output.read_text(encoding="utf-8"))
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0 if manifest["ok"] else 1

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
