import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import engine
from modules.core.db import InventoryLayer, InventoryLayerConsumption


def main() -> None:
    with engine.begin() as connection:
        InventoryLayer.__table__.create(
            bind=connection,
            checkfirst=True,
        )
        InventoryLayerConsumption.__table__.create(
            bind=connection,
            checkfirst=True,
        )

    print("Created or verified finance.inventory_layers")
    print("Created or verified finance.inventory_layer_consumptions")


if __name__ == "__main__":
    main()
