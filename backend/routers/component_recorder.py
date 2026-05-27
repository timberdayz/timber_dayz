"""Legacy compatibility wrapper for backend.domains.collection.routers.component_recorder."""
# Do not add runtime logic here.

import sys
import backend.domains.collection.routers.component_recorder as domain_module

sys.modules[__name__] = domain_module
