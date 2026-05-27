"""Legacy compatibility wrapper for backend.domains.platform.routers.users_admin."""
# Do not add runtime logic here.

import sys
import backend.domains.platform.routers.users_admin as domain_module

sys.modules[__name__] = domain_module
