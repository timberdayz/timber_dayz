import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import SessionLocal
from backend.services.inventory.order_posting_service import InventoryOrderPostingService


def main() -> None:
    db = SessionLocal()
    try:
        result = InventoryOrderPostingService(db).post_pending_orders()
        print(result)
    finally:
        db.close()


if __name__ == "__main__":
    main()
