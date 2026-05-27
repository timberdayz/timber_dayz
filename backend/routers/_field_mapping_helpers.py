"""Legacy compatibility wrapper for backend.domains.data_platform.routers._field_mapping_helpers."""
# Do not add runtime logic here.

import sys
import backend.domains.data_platform.routers._field_mapping_helpers as domain_module

sys.modules[__name__] = domain_module
