"""Legacy compatibility wrapper for backend.domains.data_platform.routers.field_mapping_status."""
# Do not add runtime logic here.

import sys
import backend.domains.data_platform.routers.field_mapping_status as domain_module

sys.modules[__name__] = domain_module
