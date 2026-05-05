from backend.routers.collection_tasks import *  # noqa: F403

# The collection aggregator (`backend.domains.collection.routers.collection`) imports
# this symbol for backward-compatibility exposure via `backend.routers.collection`.
# It must remain importable from this domain module.
from backend.routers.collection_tasks import (  # noqa: F401
    _execute_collection_task_background,
)
