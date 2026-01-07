from __future__ import annotations

from typing import Any
from pathlib import Path
from datetime import datetime
import json

from modules.components.base import ExecutionContext
from modules.components.export.base import ExportComponent, ExportResult, ExportMode, build_standard_output_root
from modules.core.config import get_config_value
from modules.utils.path_sanitizer import build_output_path, build_filename


class AmazonExporterComponent(ExportComponent):
    """Skeleton exporter that writes a placeholder file and manifest.
    Used to make generic batch flow truly executable for Amazon.
    """

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    def run(self, page: Any, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:  # type: ignore[override]
        try:
            account = self.ctx.account or {}
            cfg = self.ctx.config or {}
            account_label = account.get("label") or account.get("store_name") or account.get("username", "unknown")
            shop_name = account.get("selected_shop_name") or account.get("store_name") or "default_shop"
            shop_id = cfg.get("shop_id") or account.get("shop_id") or account.get("account_id")
            data_type = (cfg.get("data_type") or "products").lower()
            gran = cfg.get("granularity") or "manual"

            out_root = build_standard_output_root(self.ctx, data_type=data_type, granularity=gran)
            out_root.mkdir(parents=True, exist_ok=True)

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = build_filename(
                ts=ts,
                account_label=account_label,
                shop_name=shop_name,
                data_type=data_type,
                granularity=gran,
                start_date=cfg.get("start_date"),
                end_date=cfg.get("end_date"),
                suffix=".placeholder",
            )
            target = out_root / filename
            target.write_text("placeholder", encoding="utf-8")

            # manifest
            manifest = {
                "platform": self.ctx.platform,
                "account_label": account_label,
                "shop_name": shop_name,
                "shop_id": shop_id,
                "data_type": data_type,
                "granularity": gran,
                "start_date": cfg.get("start_date"),
                "end_date": cfg.get("end_date"),
                "exported_at": datetime.now().isoformat(),
                "file_path": str(target),
                "note": "skeleton export",
            }
            (Path(str(target) + ".json")).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

            if self.logger:
                self.logger.info(f"[AmazonExporterComponent] wrote placeholder: {target}")
            return ExportResult(success=True, file_path=str(target), message="skeleton")
        except Exception as e:
            if self.logger:
                self.logger.error(f"[AmazonExporterComponent] failed: {e}")
            return ExportResult(success=False, message=str(e))

