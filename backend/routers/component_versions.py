"""Legacy compatibility wrapper for backend.domains.collection.routers.component_versions."""
# Do not add runtime logic here.

import sys
import backend.domains.collection.routers.component_versions as domain_module

sys.modules[__name__] = domain_module
