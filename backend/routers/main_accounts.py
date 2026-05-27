"""Legacy compatibility wrapper for backend.domains.collection.routers.main_accounts."""
# Do not add runtime logic here.

import sys
import backend.domains.collection.routers.main_accounts as domain_module

sys.modules[__name__] = domain_module
