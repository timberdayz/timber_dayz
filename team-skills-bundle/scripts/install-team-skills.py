from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


SKILLS = [
    "sea-metrics-language",
    "sea-business-review",
    "sea-product-selection",
    "sea-funnel-action-playbook",
]


def default_target_dir() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home) / "skills"
    return Path.home() / ".codex" / "skills"


def install(bundle_root: Path, target_dir: Path, force: bool) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for skill in SKILLS:
        source = bundle_root / skill
        destination = target_dir / skill

        if destination.exists() and not force:
            print(f"[SKIP] {skill} already exists at {destination} (use --force to overwrite)")
            continue

        if destination.exists():
            shutil.rmtree(destination)

        shutil.copytree(source, destination)
        print(f"[OK] Installed {skill} -> {destination}")

    print("")
    print("Install complete.")
    print(f"Target: {target_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Install team skills bundle into an agent skills directory.")
    parser.add_argument("--target-dir", type=Path, default=None, help="Target skills directory")
    parser.add_argument("--force", action="store_true", help="Overwrite existing skills")
    args = parser.parse_args()

    bundle_root = Path(__file__).resolve().parent.parent
    target_dir = args.target_dir or default_target_dir()
    install(bundle_root, target_dir, args.force)


if __name__ == "__main__":
    main()
