from pathlib import Path


APP_PATH = Path(__file__).resolve().parents[2] / "modules" / "apps" / "collection_center" / "app.py"


def test_collection_center_app_has_no_active_temp_outputs_hardcode():
    source = APP_PATH.read_text(encoding="utf-8")

    forbidden_snippets = [
        "root='temp/outputs'",
        'output_root=Path(\'temp/outputs\')',
        'output_root=Path("temp/outputs")',
        'base_dir = Path("temp/outputs")',
        'downloads_dir = Path("temp/outputs")',
    ]

    for snippet in forbidden_snippets:
        assert snippet not in source
