"""Legacy compatibility wrapper for backend.domains.data_platform.routers.field_mapping_files."""
# Do not add runtime logic here.

import sys
import backend.domains.data_platform.routers.field_mapping_files as domain_module

sys.modules[__name__] = domain_module
