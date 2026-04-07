from pathlib import Path

import pytest

from modules.apps.collection_center.component_loader import ComponentLoader


def test_component_loader_allows_components_directory(tmp_path: Path):
    loader = ComponentLoader()
    component_file = tmp_path / "modules" / "platforms" / "miaoshou" / "components" / "login_v1_0_3.py"
    component_file.parent.mkdir(parents=True, exist_ok=True)
    component_file.write_text("class Dummy:\n    pass\n", encoding="utf-8")

    loader._validate_component_file_path(
        abs_path=str(component_file),
        project_root=str(tmp_path),
        file_path="modules/platforms/miaoshou/components/login_v1_0_3.py",
        version_id=1,
    )


def test_component_loader_rejects_archive_directory_in_default_runtime(tmp_path: Path):
    loader = ComponentLoader()
    archive_file = tmp_path / "modules" / "platforms" / "miaoshou" / "archive" / "login.py"
    archive_file.parent.mkdir(parents=True, exist_ok=True)
    archive_file.write_text("class Dummy:\n    pass\n", encoding="utf-8")

    with pytest.raises(ValueError, match="archive component paths are not allowed"):
        loader._validate_component_file_path(
            abs_path=str(archive_file),
            project_root=str(tmp_path),
            file_path="modules/platforms/miaoshou/archive/login.py",
            version_id=1,
        )
