from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

TARGET_FILES = [
    ROOT / "modules" / "collectors" / "base" / "base_collector.py",
    ROOT / "modules" / "collectors" / "shopee_collector.py",
    ROOT / "modules" / "collectors" / "shopee_workflow_manager.py",
    ROOT / "modules" / "services" / "shopee_exporter.py",
    ROOT / "modules" / "storage" / "data_organizer.py",
    ROOT / "modules" / "utils" / "flow_orchestrator.py",
]


def test_selected_legacy_tools_have_no_temp_outputs_default_root():
    forbidden = [
        'Path("temp/outputs',
        "Path('temp/outputs",
        'base_output_dir: str = "temp/outputs"',
        'output_dir = Path("temp/outputs")',
        'self.downloads_path = Path(f"temp/outputs/',
    ]

    for path in TARGET_FILES:
        source = path.read_text(encoding="utf-8")
        for snippet in forbidden:
            assert snippet not in source, f"{path.name} still contains legacy root snippet: {snippet}"
