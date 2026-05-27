"""Legacy compatibility wrapper for backend.domains.collection.routers.shop_account_aliases."""
# Do not add runtime logic here.

import sys
import backend.domains.collection.routers.shop_account_aliases as domain_module

sys.modules[__name__] = domain_module
