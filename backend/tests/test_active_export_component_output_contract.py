from pathlib import Path

from backend.services.active_collection_components import list_active_component_names


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_active_export_components_use_work_download_roots_not_data_raw_literals():
    export_components = [
        name for name in list_active_component_names() if name.endswith("_export")
    ]

    assert export_components

    for component_name in export_components:
        platform, file_name = component_name.split("/", 1)
        component_file = PROJECT_ROOT / "modules" / "platforms" / platform / "components" / f"{file_name}.py"
        text = component_file.read_text(encoding="utf-8", errors="ignore")

        assert "data/raw" not in text, f"{component_file} should not write directly to data/raw"

        helper_present = (
            "build_standard_output_root(" in text
            or "save_download_to_target(" in text
        )

        if helper_present:
            continue

        sibling_base_files = sorted(component_file.parent.glob("*_base.py"))
        assert sibling_base_files, f"{component_file} should have a local base file carrying download-path helpers"

        assert any(
            (
                "build_standard_output_root(" in base_file.read_text(encoding="utf-8", errors="ignore")
                or "save_download_to_target(" in base_file.read_text(encoding="utf-8", errors="ignore")
            )
            for base_file in sibling_base_files
        ), f"{component_file} or its local base files should use unified working-download path helpers"
