"""Legacy compatibility wrapper for backend.domains.collection.routers.collection_tasks."""
# Do not add runtime logic here.

import sys
import backend.domains.collection.routers.collection_tasks as domain_module

sys.modules[__name__] = domain_module
