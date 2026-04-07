import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import engine
from modules.core.db import InventoryAdjustmentHeader, InventoryAdjustmentLine


def main() -> None:
    with engine.begin() as connection:
        InventoryAdjustmentHeader.__table__.create(
            bind=connection,
            checkfirst=True,
        )
        InventoryAdjustmentLine.__table__.create(
            bind=connection,
            checkfirst=True,
        )

    print("Created or verified finance.inventory_adjustment_headers")
    print("Created or verified finance.inventory_adjustment_lines")


if __name__ == "__main__":
    main()
